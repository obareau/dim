"""
D.I.M — network/websocket/client.py
SocketIO client — connects to a remote DIM instance and receives state updates.

Used by the orchestrator to monitor slave instances and by the TUI to display
remote state without running a local engine.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

log = logging.getLogger("dim.ws_client")

try:
    import socketio as _sio
    _SIO_OK = True
except ImportError:
    _sio = None
    _SIO_OK = False

StateCallback   = Callable[[dict], None]
EventCallback   = Callable[[str, dict], None]


class DimClient:
    """
    SocketIO client for a single remote DIM instance.

    Receives:
        state_update  → engine state dict (same format as web UI)
        transport_state → {playing: bool}

    Emits:
        transport     → {action: "play"|"stop"|"rewind"|"toggle"}
        set_tempo     → {bpm: float}
    """

    def __init__(self, url: str, name: str = "") -> None:
        self.url   = url
        self.name  = name or url
        self._sio: Optional[object] = None
        self._connected = False
        self._lock      = threading.Lock()

        self._state_cbs:  list[StateCallback] = []
        self._event_cbs:  list[EventCallback] = []
        self._connect_cbs:    list[Callable] = []
        self._disconnect_cbs: list[Callable] = []

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_state(self,      cb: StateCallback)  -> None: self._state_cbs.append(cb)
    def on_event(self,      cb: EventCallback)  -> None: self._event_cbs.append(cb)
    def on_connect(self,    cb: Callable)        -> None: self._connect_cbs.append(cb)
    def on_disconnect(self, cb: Callable)        -> None: self._disconnect_cbs.append(cb)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def connect(self, timeout: float = 5.0) -> bool:
        if not _SIO_OK:
            log.error("python-socketio client not installed")
            return False

        sio = _sio.Client(reconnection=True, reconnection_attempts=5,
                          reconnection_delay=2, logger=False, engineio_logger=False)
        self._sio = sio

        @sio.event
        def connect():
            with self._lock:
                self._connected = True
            log.info("WS connected: %s", self.url)
            for cb in self._connect_cbs:
                try: cb()
                except Exception: pass

        @sio.event
        def disconnect():
            with self._lock:
                self._connected = False
            log.info("WS disconnected: %s", self.url)
            for cb in self._disconnect_cbs:
                try: cb()
                except Exception: pass

        @sio.on("state_update")
        def on_state(data: dict):
            for cb in self._state_cbs:
                try: cb(data)
                except Exception: pass

        @sio.on("transport_state")
        def on_transport(data: dict):
            for cb in self._event_cbs:
                try: cb("transport_state", data)
                except Exception: pass

        try:
            sio.connect(self.url, wait_timeout=timeout)
            return True
        except Exception as e:
            log.warning("WS connect failed %s: %s", self.url, e)
            return False

    def disconnect(self) -> None:
        if self._sio:
            try:
                self._sio.disconnect()
            except Exception:
                pass
            self._sio = None

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    # ── Transport commands (send to remote) ───────────────────────────────────

    def send_play(self)   -> None: self._emit("transport", {"action": "play"})
    def send_stop(self)   -> None: self._emit("transport", {"action": "stop"})
    def send_rewind(self) -> None: self._emit("transport", {"action": "rewind"})
    def send_toggle(self) -> None: self._emit("transport", {"action": "toggle"})

    def send_tempo(self, bpm: float) -> None:
        self._emit("set_tempo", {"bpm": bpm})

    def _emit(self, event: str, data: dict) -> None:
        if self._sio and self._connected:
            try:
                self._sio.emit(event, data)
            except Exception as e:
                log.warning("emit %s failed: %s", event, e)
