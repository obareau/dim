"""
D.I.M — tests/test_network.py
Tests for Sprint 5 — network layer (mDNS, WS client, orchestrator, ESP32 endpoint).

All tests run offline (no actual network required for the unit tests).
mDNS live test is skipped if zeroconf is not available.
"""
from __future__ import annotations

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── mDNS ──────────────────────────────────────────────────────────────────────

def test_mdns_available_flag():
    from network.discovery.mdns import is_available
    # Just check it returns a bool (True if zeroconf installed)
    assert isinstance(is_available(), bool)


def test_mdns_peer_dataclass():
    from network.discovery.mdns import DimPeer
    p = DimPeer(name="DIM-test-5001", host="192.168.1.10", port=5001,
                role="slave", project_name="Test")
    assert p.url == "http://192.168.1.10:5001"
    assert p.ws_url == "http://192.168.1.10:5001"
    assert "5001" in str(p)


def test_mdns_announcer_creates():
    from network.discovery.mdns import MdnsAnnouncer
    ann = MdnsAnnouncer(port=5099, role="master", project_name="Test")
    assert ann._port == 5099
    assert ann._role == "master"
    assert ann.get_peers() == []


def test_mdns_announcer_callbacks():
    from network.discovery.mdns import MdnsAnnouncer, DimPeer
    ann = MdnsAnnouncer(port=5099)
    added = []
    removed = []
    ann.on_peer_added(added.append)
    ann.on_peer_removed(removed.append)

    # Simulate peer add/remove
    peer = DimPeer(name="DIM-other-5002", host="192.168.1.20", port=5002)
    ann._peer_added(peer)
    assert len(added) == 1
    assert added[0].host == "192.168.1.20"
    assert len(ann.get_peers()) == 1

    ann._peer_removed(DimPeer(name="DIM-other-5002", host="", port=0))
    assert len(removed) == 1
    assert len(ann.get_peers()) == 0


def test_mdns_get_peer():
    from network.discovery.mdns import MdnsAnnouncer, DimPeer
    ann = MdnsAnnouncer(port=5099)
    peer = DimPeer(name="DIM-host-5001", host="10.0.0.1", port=5001, role="master")
    ann._peer_added(peer)
    found = ann.get_peer("DIM-host-5001")
    assert found is not None
    assert found.role == "master"
    assert ann.get_peer("nonexistent") is None


# ── WebSocket client ──────────────────────────────────────────────────────────

def test_ws_client_creates():
    from network.websocket.client import DimClient
    c = DimClient(url="http://192.168.1.10:5001", name="test-peer")
    assert c.url == "http://192.168.1.10:5001"
    assert c.name == "test-peer"
    assert c.is_connected is False


def test_ws_client_callbacks_register():
    from network.websocket.client import DimClient
    c = DimClient(url="http://localhost:5099")
    states = []
    c.on_state(states.append)
    assert len(c._state_cbs) == 1


def test_ws_client_emit_no_crash_when_disconnected():
    """Emitting when disconnected should silently do nothing."""
    from network.websocket.client import DimClient
    c = DimClient(url="http://localhost:5099")
    c.send_play()
    c.send_stop()
    c.send_tempo(120.0)
    # No exception


# ── Orchestrator ──────────────────────────────────────────────────────────────

def test_orchestrator_creates():
    from network.orchestrator.master import MasterOrchestrator
    orch = MasterOrchestrator(port=5099, project_name="TestProject")
    assert orch._port == 5099
    assert orch._project_name == "TestProject"
    status = orch.get_status()
    assert status["role"] == "master"
    assert status["peer_count"] == 0


def test_orchestrator_peer_add_creates_client():
    from network.orchestrator.master import MasterOrchestrator
    from network.discovery.mdns import DimPeer

    orch = MasterOrchestrator(port=5099, auto_connect=False)  # no auto-connect
    peer_events = []
    orch.on_peers_changed(lambda: peer_events.append(1))

    peer = DimPeer(name="DIM-slave-5002", host="192.168.1.20", port=5002, role="slave")
    orch._on_peer_added(peer)

    assert "DIM-slave-5002" in orch._clients
    assert len(peer_events) == 1


def test_orchestrator_peer_remove():
    from network.orchestrator.master import MasterOrchestrator
    from network.discovery.mdns import DimPeer
    from network.websocket.client import DimClient

    orch = MasterOrchestrator(port=5099, auto_connect=False)
    peer = DimPeer(name="DIM-slave-5003", host="192.168.1.21", port=5003)
    orch._on_peer_added(peer)
    assert len(orch._clients) == 1

    orch._on_peer_removed(DimPeer(name="DIM-slave-5003", host="", port=0))
    assert len(orch._clients) == 0


def test_orchestrator_status_structure():
    from network.orchestrator.master import MasterOrchestrator
    from network.discovery.mdns import DimPeer

    orch = MasterOrchestrator(port=5099, auto_connect=False)
    peer = DimPeer(name="DIM-peer-5004", host="192.168.1.22", port=5004)
    orch._on_peer_added(peer)

    # Inject a fake state
    orch._slave_states["DIM-peer-5004"] = {"playing": True, "tempo_bpm": 118.0, "bar": 3}
    status = orch.get_status()

    assert status["peer_count"] == 1
    assert status["peers"][0]["name"] == "DIM-peer-5004"
    assert status["peers"][0]["playing"] is True


def test_orchestrator_broadcast_no_crash_no_clients():
    from network.orchestrator.master import MasterOrchestrator
    orch = MasterOrchestrator(port=5099)
    orch.broadcast_play()
    orch.broadcast_stop()
    orch.broadcast_tempo(120.0)
    orch.broadcast_rewind()
    # No exception


def test_orchestrator_slave_state_callback():
    from network.orchestrator.master import MasterOrchestrator
    orch = MasterOrchestrator(port=5099)
    received = []
    orch.on_slave_state(lambda name, s: received.append((name, s)))

    orch._on_slave_state("peer-A", {"playing": True, "tempo_bpm": 120.0})
    assert received == [("peer-A", {"playing": True, "tempo_bpm": 120.0})]


# ── ESP32 endpoint (via Flask test client) ────────────────────────────────────

@pytest.fixture
def flask_app():
    """Create a minimal Flask app with the ESP32 endpoint."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from adapters.web.app import create_app
    app, socketio = create_app(project_path=None)
    app.config["TESTING"] = True
    return app


def test_esp32_state_no_project(flask_app):
    with flask_app.test_client() as c:
        resp = c.get("/api/esp32/state")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("loaded") == 0


def test_esp32_state_with_project(flask_app):
    """Load a project and check ESP32 payload structure."""
    from adapters.web import engine
    proj_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "formats", "example_project.json"
    )
    engine.load(proj_path)

    with flask_app.test_client() as c:
        resp = c.get("/api/esp32/state")
        assert resp.status_code == 200
        data = json.loads(resp.data)

    assert "p" in data
    assert "bpm" in data
    assert "bar" in data
    assert "beat" in data
    assert "sig" in data
    assert "t" in data
    assert "lanes" in data
    assert isinstance(data["lanes"], list)
    assert len(data["lanes"]) > 0

    lane = data["lanes"][0]
    assert "id"  in lane
    assert "nm"  in lane
    assert "cue" in lane
    assert "bdg" in lane
    assert "br"  in lane
    assert "end" in lane
    # Name truncated to 12
    assert len(lane["nm"]) <= 12


def test_esp32_state_bpm_is_float(flask_app):
    from adapters.web import engine
    engine.set_tempo(134.5)
    with flask_app.test_client() as c:
        data = json.loads(c.get("/api/esp32/state").data)
    if data.get("loaded") != 0:
        assert isinstance(data["bpm"], float)


def test_network_status_endpoint(flask_app):
    with flask_app.test_client() as c:
        resp = c.get("/api/network/status")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "mdns" in data
        assert "peers" in data


def test_network_peers_endpoint(flask_app):
    with flask_app.test_client() as c:
        resp = c.get("/api/network/peers")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)
