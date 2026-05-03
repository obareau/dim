"""
D.I.M — adapters/sync/osc_sync.py
OSC inter-instance sync.

OSC address map
───────────────
  Broadcast (this instance → network):
    /dim/tempo     f   bpm
    /dim/beat      f   beat_position
    /dim/play      i   1=play 0=stop
    /dim/state     fff  bpm, beat, is_playing

  Receive (network → this instance):
    /dim/tempo     f   set tempo
    /dim/play      i   set play/stop
    /dim/rewind    —   rewind

Default ports:
  TX: 57121  (send to this port on all peers)
  RX: 57120  (listen on this port)
  Multicast: 224.0.0.1 (LAN broadcast)
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from .base import SyncSource, SyncSourceType, SyncState

try:
    from pythonosc import udp_client, dispatcher
    from pythonosc.osc_server import BlockingOSCUDPServer
    _OSC_AVAILABLE = True
except ImportError:
    _OSC_AVAILABLE = False


# ── Defaults ───────────────────────────────────────────────────────────────────

DEFAULT_RX_PORT   = 57120
DEFAULT_TX_PORT   = 57121
DEFAULT_BROADCAST = "255.255.255.255"


# ── OSC Sync Source ────────────────────────────────────────────────────────────

class OscSyncSource(SyncSource):
    """
    Listens for OSC messages on rx_port.
    Broadcasts state on tx_port.

    Handles:
      /dim/tempo f  → emit tempo callback
      /dim/play  i  → emit play callback
      /dim/rewind   → emit beat(0) callback
    """

    def __init__(
        self,
        rx_port:   int = DEFAULT_RX_PORT,
        tx_host:   str = DEFAULT_BROADCAST,
        tx_port:   int = DEFAULT_TX_PORT,
    ) -> None:
        super().__init__()
        self._rx_port  = rx_port
        self._tx_host  = tx_host
        self._tx_port  = tx_port

        self._client   = None
        self._server   = None
        self._thread: Optional[threading.Thread] = None
        self._running  = False
        self._lock     = threading.Lock()

        # state
        self._tempo_bpm   = 120.0
        self._beat_pos    = 0.0
        self._is_playing  = False
        self._is_available = False

    @property
    def source_type(self) -> SyncSourceType:
        return SyncSourceType.OSC

    def start(self) -> None:
        if not _OSC_AVAILABLE:
            return
        # TX client
        try:
            self._client = udp_client.SimpleUDPClient(self._tx_host, self._tx_port)
        except Exception:
            self._client = None

        # RX server
        try:
            disp = dispatcher.Dispatcher()
            disp.map("/dim/tempo",  self._handle_tempo)
            disp.map("/dim/play",   self._handle_play)
            disp.map("/dim/rewind", self._handle_rewind)
            disp.map("/dim/state",  self._handle_state)
            disp.set_default_handler(lambda *_: None)

            self._server = BlockingOSCUDPServer(("0.0.0.0", self._rx_port), disp)
            self._running = True
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="dim-osc-rx",
            )
            self._thread.start()
            with self._lock:
                self._is_available = True
        except Exception:
            self._server = None

    def stop(self) -> None:
        self._running = False
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None

    def get_state(self) -> SyncState:
        with self._lock:
            return SyncState(
                source=SyncSourceType.OSC,
                tempo_bpm=self._tempo_bpm,
                beat_position=self._beat_pos,
                is_playing=self._is_playing,
                is_available=self._is_available,
            )

    # ── Broadcast ─────────────────────────────────────────────────────────────

    def broadcast_state(self, bpm: float, beat: float, playing: bool) -> None:
        """Send /dim/state to the network."""
        if self._client is None:
            return
        try:
            self._client.send_message("/dim/state", [float(bpm), float(beat), int(playing)])
        except Exception:
            pass

    def broadcast_tempo(self, bpm: float) -> None:
        if self._client is None:
            return
        try:
            self._client.send_message("/dim/tempo", float(bpm))
        except Exception:
            pass

    def broadcast_play(self, playing: bool) -> None:
        if self._client is None:
            return
        try:
            self._client.send_message("/dim/play", int(playing))
        except Exception:
            pass

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_tempo(self, address: str, bpm: float) -> None:
        with self._lock:
            self._tempo_bpm = float(bpm)
        self._emit_tempo(float(bpm))

    def _handle_play(self, address: str, value: int) -> None:
        playing = bool(value)
        with self._lock:
            self._is_playing = playing
        self._emit_play(playing)

    def _handle_rewind(self, address: str, *args) -> None:
        with self._lock:
            self._beat_pos = 0.0
        self._emit_beat(0.0)

    def _handle_state(self, address: str, bpm: float, beat: float, playing: int) -> None:
        with self._lock:
            self._tempo_bpm   = float(bpm)
            self._beat_pos    = float(beat)
            self._is_playing  = bool(playing)
