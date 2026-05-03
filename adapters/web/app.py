"""
D.I.M — adapters/web/app.py
Flask application factory + SocketIO + REST API + HTML routes.

Usage:
    python run_web.py [project.json]
    python run_web.py formats/example_project.json
"""
from __future__ import annotations

import json
import os
import sys

from flask import Flask, jsonify, render_template, request, abort
from flask_socketio import SocketIO, emit

# Ensure project root is on path
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from adapters.web import engine
from core.serializer import project_to_dict, project_from_dict, save_project
from core.validator import validate


def orch_engine_hook(orch, eng, sio) -> None:
    """
    Wire engine play/tempo changes → broadcast to all slaves.
    Called once when this instance becomes master.
    """
    original_play  = eng.play
    original_stop  = eng.stop
    original_rewind = eng.rewind
    original_tempo = eng.set_tempo

    def _play():
        original_play()
        orch.broadcast_play()

    def _stop():
        original_stop()
        orch.broadcast_stop()

    def _rewind():
        original_rewind()
        orch.broadcast_rewind()

    def _tempo(bpm):
        original_tempo(bpm)
        orch.broadcast_tempo(bpm)

    eng.play      = _play
    eng.stop      = _stop
    eng.rewind    = _rewind
    eng.set_tempo = _tempo


def create_app(project_path: str | None = None) -> tuple[Flask, SocketIO]:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = os.environ.get("DIM_SECRET", "dim-dev-secret")
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    engine.init(socketio)
    engine.start_thread()

    if project_path:
        try:
            engine.load(project_path)
            print(f"  Loaded: {project_path}")
        except Exception as e:
            print(f"  Warning: could not load {project_path}: {e}")

    # ── HTML routes ───────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        proj = engine.get_project_dict()
        return render_template("index.html", project=proj)

    @app.route("/editor")
    def editor():
        proj_dict = engine.get_project_dict()
        if proj_dict is None:
            return render_template("index.html", project=None, message="No project loaded.")
        # Build editor context with badge helper
        lanes = []
        for ln in proj_dict["project"]["lanes"]:
            from core.serializer import lane_from_dict
            lane_obj = lane_from_dict(ln)
            sections = []
            for sec_obj in lane_obj.sections:
                cues = []
                for cue_obj in sec_obj.cues:
                    cues.append({
                        "id": cue_obj.id,
                        "label": cue_obj.label,
                        "content": cue_obj.content,
                        "duration_bars": cue_obj.duration_bars,
                        "badge": engine.instruction_badge(cue_obj.instruction),
                        "enabled": cue_obj.enabled,
                        "order_index": cue_obj.order_index,
                    })
                sections.append({
                    "id": sec_obj.id,
                    "name": sec_obj.name,
                    "type": sec_obj.type,
                    "color": sec_obj.color,
                    "badge": engine.instruction_badge(sec_obj.instruction),
                    "playlist_mode": sec_obj.playlist.mode,
                    "cues": cues,
                })
            lanes.append({
                "id": lane_obj.id,
                "name": lane_obj.name,
                "color": lane_obj.color,
                "speed_ratio": lane_obj.speed_ratio,
                "is_conductor": lane_obj.is_conductor,
                "sections": sections,
            })
        project_meta = {
            "id": proj_dict["project"]["id"],
            "name": proj_dict["project"]["name"],
            "tempo_bpm": proj_dict["project"]["tempo_bpm"],
            "time_signature": proj_dict["project"]["time_signature"],
            "gosub_stack_limit": proj_dict["project"]["gosub_stack_limit"],
        }
        return render_template("editor.html", meta=project_meta, lanes=lanes)

    @app.route("/performance")
    def performance():
        proj_dict = engine.get_project_dict()
        if proj_dict is None:
            return render_template("index.html", project=None, message="No project loaded.")
        lanes_meta = [
            {"id": ln["id"], "name": ln["name"], "color": ln["color"],
             "is_conductor": ln["is_conductor"], "speed_ratio": ln["speed_ratio"]}
            for ln in proj_dict["project"]["lanes"]
        ]
        import time as _time
        return render_template(
            "performance.html",
            project_name=proj_dict["project"]["name"],
            tempo_bpm=proj_dict["project"]["tempo_bpm"],
            time_signature=proj_dict["project"]["time_signature"],
            lanes_meta=lanes_meta,
            cache_bust=int(_time.time()),
        )

    # ── REST API ──────────────────────────────────────────────────────────────

    @app.route("/api/project", methods=["GET"])
    def api_get_project():
        proj = engine.get_project_dict()
        if proj is None:
            return jsonify({"error": "no project loaded"}), 404
        return jsonify(proj)

    @app.route("/api/section/<lane_id>/<section_id>/cues", methods=["GET"])
    def api_section_cues(lane_id, section_id):
        """Return the ordered cue queue for a section (for performance view full list)."""
        state = engine.get_state()
        proj  = engine._project
        if proj is None:
            return jsonify([])
        # Find lane → section → cue queue order from cursor
        from adapters.web.engine import _cursor, _lock, instruction_badge, _find_section
        with _lock:
            cur = _cursor
        lane_cursor = cur.lane_cursors.get(lane_id) if cur else None
        sec = _find_section(proj, lane_id, section_id)
        if sec is None:
            return jsonify([])
        # Use the cue_queue from the cursor if available, else natural order
        queue_ids = lane_cursor.cue_queue if (lane_cursor and lane_cursor.section_id == section_id) else [c.id for c in sec.cues]
        cues = []
        cue_map = {c.id: c for c in sec.cues}
        for i, cid in enumerate(queue_ids):
            c = cue_map.get(cid)
            if c:
                cues.append({
                    "id":    c.id,
                    "index": i,
                    "label": c.label,
                    "badge": instruction_badge(c.instruction),
                    "duration_bars": c.duration_bars,
                })
        return jsonify(cues)

    @app.route("/api/project", methods=["POST"])
    def api_load_project():
        data = request.get_json(force=True)
        if data is None:
            abort(400, "Invalid JSON")
        try:
            proj = engine.load_from_dict(data)
            return jsonify({"ok": True, "name": proj.name, "lanes": len(proj.lanes)})
        except Exception as e:
            return jsonify({"error": str(e)}), 422

    @app.route("/api/state", methods=["GET"])
    def api_state():
        return jsonify(engine.get_state())

    @app.route("/api/transport/play", methods=["POST"])
    def api_play():
        engine.play()
        socketio.emit("transport_state", {"playing": True})
        return jsonify({"ok": True})

    @app.route("/api/transport/stop", methods=["POST"])
    def api_stop():
        engine.stop()
        socketio.emit("transport_state", {"playing": False})
        return jsonify({"ok": True})

    @app.route("/api/transport/rewind", methods=["POST"])
    def api_rewind():
        engine.rewind()
        socketio.emit("state_update", engine.get_state())
        return jsonify({"ok": True})

    @app.route("/api/transport/tempo", methods=["POST"])
    def api_tempo():
        data = request.get_json(force=True) or {}
        bpm = float(data.get("bpm", 0))
        if bpm <= 0:
            return jsonify({"error": "bpm must be > 0"}), 422
        engine.set_tempo(bpm)
        return jsonify({"ok": True, "tempo_bpm": bpm})

    @app.route("/api/transport/time-signature", methods=["POST"])
    def api_time_signature():
        data = request.get_json(force=True) or {}
        ts   = data.get("time_signature", "")
        if not ts:
            return jsonify({"error": "time_signature required"}), 422
        engine.set_time_signature(ts)
        socketio.emit("state_update", engine.get_state())
        return jsonify({"ok": True, "time_signature": ts})

    @app.route("/esp32")
    def esp32_preview():
        """Emulated ESP32 LCD/OLED display preview."""
        return render_template("esp32_preview.html")

    @app.route("/api/validate", methods=["POST"])
    def api_validate():
        data = request.get_json(force=True)
        try:
            proj = project_from_dict(data)
        except Exception as e:
            return jsonify({"valid": False, "errors": [str(e)]}), 422
        errors = validate(proj)
        return jsonify({
            "valid": not any(e.level == "error" for e in errors),
            "errors": [{"level": e.level, "code": e.code, "message": e.message} for e in errors],
        })

    # ── Sync API ──────────────────────────────────────────────────────────────

    @app.route("/api/sync/status", methods=["GET"])
    def api_sync_status():
        try:
            from adapters.sync.manager import get_manager
            return jsonify(get_manager().get_status())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/sync/midi/ports", methods=["GET"])
    def api_sync_midi_ports():
        try:
            import mido
            return jsonify({
                "inputs":  mido.get_input_names(),
                "outputs": mido.get_output_names(),
            })
        except Exception:
            return jsonify({"inputs": [], "outputs": [], "error": "mido not available"})

    @app.route("/api/sync/midi/start", methods=["POST"])
    def api_sync_midi_start():
        data = request.get_json(force=True) or {}
        in_port  = data.get("input_port")
        out_port = data.get("output_port")
        try:
            from adapters.sync.manager import get_manager
            from adapters.sync.midi_clock import MidiClockInput, MidiClockOutput
            mgr = get_manager()
            mgr.set_engine_callbacks(engine.set_tempo, engine.set_playing)
            if in_port is not None and mgr._midi_in is None:
                midi_in = MidiClockInput(in_port)
                mgr.add_midi_input(midi_in)
                midi_in.start()
            if out_port is not None and mgr._midi_out is None:
                midi_out = MidiClockOutput(out_port)
                mgr.add_midi_output(midi_out)
            return jsonify({"ok": True, "status": mgr.get_status()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/sync/osc/start", methods=["POST"])
    def api_sync_osc_start():
        data = request.get_json(force=True) or {}
        rx_port = int(data.get("rx_port", 57120))
        tx_port = int(data.get("tx_port", 57121))
        tx_host = data.get("tx_host", "255.255.255.255")
        try:
            from adapters.sync.manager import get_manager
            from adapters.sync.osc_sync import OscSyncSource
            mgr = get_manager()
            mgr.set_engine_callbacks(engine.set_tempo, engine.set_playing)
            osc = OscSyncSource(rx_port=rx_port, tx_host=tx_host, tx_port=tx_port)
            mgr.add_osc(osc)
            osc.start()
            return jsonify({"ok": True, "status": mgr.get_status()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/sync/link/start", methods=["POST"])
    def api_sync_link_start():
        data = request.get_json(force=True) or {}
        quantum = float(data.get("quantum", 4.0))
        try:
            from adapters.sync.manager import get_manager
            from adapters.sync.link_sync import make_link_source, is_link_available
            mgr = get_manager()
            mgr.set_engine_callbacks(engine.set_tempo, engine.set_playing)
            link = make_link_source(quantum)
            mgr.add_link(link)
            link.start()
            return jsonify({
                "ok": True,
                "link_available": is_link_available(),
                "status": mgr.get_status(),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Network / orchestrator API ────────────────────────────────────────────

    @app.route("/api/network/status", methods=["GET"])
    def api_network_status():
        result = {"mdns": False, "orchestrator": None, "peers": []}
        try:
            from network.discovery.mdns import get_announcer, is_available
            result["mdns"] = is_available()
            ann = get_announcer()
            result["peers"] = [
                {"name": p.name, "host": p.host, "port": p.port,
                 "role": p.role, "project": p.project_name}
                for p in ann.get_peers()
            ]
        except Exception as e:
            result["mdns_error"] = str(e)
        try:
            from network.orchestrator.master import get_orchestrator
            result["orchestrator"] = get_orchestrator().get_status()
        except Exception:
            pass
        return jsonify(result)

    @app.route("/api/network/announce", methods=["POST"])
    def api_network_announce():
        data = request.get_json(force=True) or {}
        role = data.get("role", "slave")
        try:
            from network.discovery.mdns import get_announcer
            ann = get_announcer()
            ann._port         = data.get("port", 5001)
            ann._role         = role
            ann._project_name = data.get("project", "")
            ann.start()
            return jsonify({"ok": True, "role": role})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/network/orchestrate", methods=["POST"])
    def api_network_orchestrate():
        """Become master — connect to all discovered slaves."""
        try:
            from network.orchestrator.master import get_orchestrator
            from network.discovery.mdns import get_announcer
            proj_dict = engine.get_project_dict()
            name = proj_dict["project"]["name"] if proj_dict else ""
            orch = get_orchestrator()
            orch._port         = int(request.get_json(force=True).get("port", 5001))
            orch._project_name = name
            orch.start()
            # Wire engine callbacks so master broadcasts to slaves
            orch_engine_hook(orch, engine, socketio)
            return jsonify({"ok": True, "status": orch.get_status()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/network/peers", methods=["GET"])
    def api_network_peers():
        try:
            from network.discovery.mdns import get_announcer
            return jsonify([
                {"name": p.name, "url": p.url, "role": p.role,
                 "project": p.project_name, "version": p.version}
                for p in get_announcer().get_peers()
            ])
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── ESP32 minimal state endpoint ──────────────────────────────────────────

    @app.route("/api/esp32/state", methods=["GET"])
    def api_esp32_state():
        """Minimal JSON for ESP32 TFT clients — small payload, fast parse."""
        state = engine.get_state()
        if not state.get("loaded"):
            return jsonify({"loaded": 0})

        lanes = []
        for lane_id, ln in state.get("lanes", {}).items():
            cue = ln.get("cue") or {}
            lanes.append({
                "id":  lane_id,
                "nm":  (ln.get("name") or "")[:12],
                "cue": (cue.get("label") or "")[:16],
                "bdg": (cue.get("badge") or "")[:8],
                "br":  round(ln.get("bars_remaining", 0.0), 1),
                "end": int(ln.get("ended", False)),
            })

        return jsonify({
            "p":    int(state.get("playing", False)),
            "bpm":  round(state.get("tempo_bpm", 120.0), 1),
            "bar":  state.get("bar", 1),
            "beat": state.get("beat_in_bar", 1),
            "sig":  state.get("time_signature", "4/4"),
            "t":    state.get("elapsed_fmt", "0:00"),
            "lanes": lanes,
        })

    # ── SocketIO events ───────────────────────────────────────────────────────

    @socketio.on("connect")
    def on_connect():
        emit("state_update", engine.get_state())

    @socketio.on("transport")
    def on_transport(data):
        action = data.get("action")
        if action == "play":
            engine.play()
        elif action == "stop":
            engine.stop()
        elif action == "rewind":
            engine.rewind()
            emit("state_update", engine.get_state(), broadcast=True)
        elif action == "toggle":
            state = engine.get_state()
            engine.set_playing(not state.get("playing", False))
        socketio.emit("transport_state", {"playing": engine.get_state().get("playing", False)})

    @socketio.on("manual_advance")
    def on_manual_advance(data):
        """Trigger a manual advance on a lane (releases LOOP UNTIL MANUAL wait)."""
        lane_id = (data or {}).get("lane_id", "")
        fired = engine.trigger_manual(lane_id)
        if fired:
            emit("state_update", engine.get_state(), broadcast=True)

    @socketio.on("veto_jump")
    def on_veto_jump(data):
        """Flag a lane to skip its next JUMP instruction."""
        lane_id = (data or {}).get("lane_id", "")
        fired = engine.veto_jump(lane_id)
        if fired:
            emit("state_update", engine.get_state(), broadcast=True)

    @socketio.on("set_tempo")
    def on_set_tempo(data):
        bpm = float(data.get("bpm", 0))
        if bpm > 0:
            engine.set_tempo(bpm)

    return app, socketio
