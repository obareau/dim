"""
D.I.M — network/orchestrator/master.py
Master orchestrator — one DIM instance controls all others on the LAN.

Responsibilities:
  - Announce itself as "master" via mDNS
  - Connect to all discovered slave instances via SocketIO
  - Broadcast transport commands to all slaves
  - Collect and aggregate slave states
  - Forward engine tempo changes to slaves

Architecture:
  Master engine  →  MasterOrchestrator  →  [DimClient × N]  →  Slave engines

The master keeps running its own engine normally.
Slaves simply follow transport/tempo commands from the master.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional, Callable

log = logging.getLogger("dim.orchestrator")

from network.discovery.mdns import MdnsAnnouncer, DimPeer, get_announcer
from network.websocket.client import DimClient

StateCallback = Callable[[str, dict], None]   # (peer_name, state)


class MasterOrchestrator:
    """
    Manages all slave DIM instances discovered via mDNS.
    Auto-connects to new peers, disconnects on departure.
    """

    def __init__(
        self,
        port:         int  = 5001,
        project_name: str  = "",
        auto_connect: bool = True,
    ) -> None:
        self._port         = port
        self._project_name = project_name
        self._auto_connect = auto_connect
        self._lock         = threading.Lock()

        self._announcer: Optional[MdnsAnnouncer]  = None
        self._clients:   dict[str, DimClient]     = {}   # name → client
        self._slave_states: dict[str, dict]        = {}   # name → last state

        self._state_cbs:  list[StateCallback]  = []
        self._peer_cbs:   list[Callable]       = []

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_slave_state(self, cb: StateCallback) -> None:
        """Called when a slave broadcasts a state update."""
        self._state_cbs.append(cb)

    def on_peers_changed(self, cb: Callable) -> None:
        """Called when peer list changes."""
        self._peer_cbs.append(cb)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._announcer = MdnsAnnouncer(
            port         = self._port,
            role         = "master",
            project_name = self._project_name,
        )
        self._announcer.on_peer_added(self._on_peer_added)
        self._announcer.on_peer_removed(self._on_peer_removed)
        self._announcer.start()
        log.info("Orchestrator started — listening for DIM peers")

    def stop(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
        for c in clients:
            c.disconnect()
        if self._announcer:
            self._announcer.stop()
        log.info("Orchestrator stopped")

    def update_project(self, name: str) -> None:
        self._project_name = name
        if self._announcer:
            self._announcer.update_project(name)

    # ── Broadcast commands ────────────────────────────────────────────────────

    def broadcast_play(self)   -> None: self._broadcast(lambda c: c.send_play())
    def broadcast_stop(self)   -> None: self._broadcast(lambda c: c.send_stop())
    def broadcast_rewind(self) -> None: self._broadcast(lambda c: c.send_rewind())

    def broadcast_tempo(self, bpm: float) -> None:
        self._broadcast(lambda c: c.send_tempo(bpm))

    def _broadcast(self, fn: Callable[[DimClient], None]) -> None:
        with self._lock:
            clients = [c for c in self._clients.values() if c.is_connected]
        for c in clients:
            try:
                fn(c)
            except Exception as e:
                log.warning("broadcast error to %s: %s", c.name, e)

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        with self._lock:
            peers = []
            for name, client in self._clients.items():
                state = self._slave_states.get(name, {})
                peers.append({
                    "name":      name,
                    "url":       client.url,
                    "connected": client.is_connected,
                    "playing":   state.get("playing", False),
                    "tempo_bpm": state.get("tempo_bpm"),
                    "bar":       state.get("bar"),
                    "project":   state.get("project_name", ""),
                })
            return {
                "role":       "master",
                "port":       self._port,
                "peer_count": len(self._clients),
                "peers":      peers,
            }

    def get_slave_states(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._slave_states)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_peer_added(self, peer: DimPeer) -> None:
        with self._lock:
            if peer.name in self._clients:
                return   # already tracked

        log.info("New DIM peer: %s → %s", peer.name, peer.url)
        client = DimClient(url=peer.ws_url, name=peer.name)
        client.on_state(lambda s, name=peer.name: self._on_slave_state(name, s))
        client.on_connect(lambda name=peer.name: log.info("Slave connected: %s", name))
        client.on_disconnect(lambda name=peer.name: log.warning("Slave lost: %s", name))

        with self._lock:
            self._clients[peer.name] = client

        if self._auto_connect:
            # Connect in background thread
            t = threading.Thread(
                target=self._connect_client,
                args=(client,),
                daemon=True,
                name=f"dim-ws-{peer.name}",
            )
            t.start()

        self._notify_peers()

    def _on_peer_removed(self, peer: DimPeer) -> None:
        with self._lock:
            client = self._clients.pop(peer.name, None)
            self._slave_states.pop(peer.name, None)
        if client:
            client.disconnect()
            log.info("Slave removed: %s", peer.name)
        self._notify_peers()

    def _connect_client(self, client: DimClient) -> None:
        ok = client.connect(timeout=5.0)
        if not ok:
            log.warning("Could not connect to slave: %s", client.url)

    def _on_slave_state(self, name: str, state: dict) -> None:
        with self._lock:
            self._slave_states[name] = state
        for cb in self._state_cbs:
            try:
                cb(name, state)
            except Exception:
                pass

    def _notify_peers(self) -> None:
        for cb in self._peer_cbs:
            try:
                cb()
            except Exception:
                pass


# ── Module-level singleton ─────────────────────────────────────────────────────

_orchestrator: Optional[MasterOrchestrator] = None


def get_orchestrator() -> MasterOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MasterOrchestrator()
    return _orchestrator
