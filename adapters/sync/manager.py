"""
D.I.M — adapters/sync/manager.py
SyncManager — coordinates sync sources and drives the engine.

Priority order (highest wins):
  1. Ableton Link  (if available and has peers)
  2. MIDI Clock In (if receiving signal)
  3. OSC           (if receiving)
  4. Internal      (engine self-clocked — default)

When a higher-priority source takes over:
  - its tempo is pushed to the engine
  - if the source emits play/stop, the engine follows
  - MIDI Clock Out keeps sending regardless of source

The SyncManager also handles MIDI Clock Output:
  - On each engine tick, push_delta() sends the right number of F8 pulses.
  - FA/FC (start/stop) are sent when the engine play state changes.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from .base import SyncSource, SyncSourceType, SyncState

log = logging.getLogger("dim.sync")


class SyncManager:
    """
    Singleton-style sync coordinator.
    Inject it into the engine via set_engine_callbacks().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Sources (optional)
        self._midi_in:   Optional[object] = None   # MidiClockInput
        self._midi_out:  Optional[object] = None   # MidiClockOutput
        self._link:      Optional[object] = None   # LinkSyncSource / stub
        self._osc:       Optional[object] = None   # OscSyncSource

        # Engine callbacks (set by integrator)
        self._engine_set_tempo:   Optional[callable] = None
        self._engine_set_playing: Optional[callable] = None

        # Tracking
        self._active_source: SyncSourceType = SyncSourceType.INTERNAL
        self._last_playing:  Optional[bool]  = None

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_engine_callbacks(
        self,
        set_tempo:   callable,
        set_playing: callable,
    ) -> None:
        """Wire engine control functions."""
        self._engine_set_tempo   = set_tempo
        self._engine_set_playing = set_playing

    def add_midi_input(self, midi_in) -> None:
        self._midi_in = midi_in
        midi_in.on_tempo(self._on_midi_tempo)
        midi_in.on_play(self._on_midi_play)

    def add_midi_output(self, midi_out) -> None:
        self._midi_out = midi_out

    def add_link(self, link_src) -> None:
        self._link = link_src
        link_src.on_tempo(self._on_link_tempo)
        link_src.on_play(self._on_link_play)

    def add_osc(self, osc_src) -> None:
        self._osc = osc_src
        osc_src.on_tempo(self._on_osc_tempo)
        osc_src.on_play(self._on_osc_play)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start_all(self) -> None:
        for src in [self._midi_in, self._link, self._osc]:
            if src is not None:
                try:
                    src.start()
                    log.info("Started sync source: %s", src.source_type)
                except Exception as e:
                    log.warning("Failed to start %s: %s", src, e)

    def stop_all(self) -> None:
        for src in [self._midi_in, self._link, self._osc]:
            if src is not None:
                try:
                    src.stop()
                except Exception:
                    pass
        if self._midi_out is not None:
            try:
                self._midi_out.close()
            except Exception:
                pass

    # ── Engine tick hook ──────────────────────────────────────────────────────

    def on_engine_tick(self, delta_beats: float, tempo_bpm: float, is_playing: bool) -> None:
        """
        Call this from the engine tick loop (adapters/web/engine.py _tick_loop).
        Drives MIDI Clock Out and OSC broadcast.
        """
        # MIDI Clock Out — send pulses
        if self._midi_out is not None and is_playing:
            self._midi_out.push_delta(delta_beats)

        # OSC broadcast
        if self._osc is not None:
            # We don't have beat_pos here, skip for now
            # Full broadcast is triggered by state_update in web engine
            pass

        # Detect play state change for MIDI transport messages
        if self._midi_out is not None:
            if self._last_playing is None:
                pass
            elif not self._last_playing and is_playing:
                self._midi_out.send_start()
                log.debug("MIDI OUT: Start")
            elif self._last_playing and not is_playing:
                self._midi_out.send_stop()
                log.debug("MIDI OUT: Stop")
        self._last_playing = is_playing

    def on_engine_rewind(self) -> None:
        """Call when engine rewinds."""
        if self._midi_out is not None:
            # Send Song Position Pointer 0 then Continue
            try:
                import mido
                self._midi_out._port.send(mido.Message("songpos", pos=0))
            except Exception:
                pass

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """JSON-serializable status for the web UI."""
        status = {
            "active_source": self._active_source.value,
            "midi_in":  None,
            "midi_out": None,
            "link":     None,
            "osc":      None,
        }
        if self._midi_in is not None:
            s = self._midi_in.get_state()
            status["midi_in"] = {
                "available": s.is_available,
                "tempo_bpm": round(s.tempo_bpm, 1),
                "playing":   s.is_playing,
                "port":      getattr(self._midi_in, "_port_name", None),
            }
        if self._midi_out is not None:
            status["midi_out"] = {
                "open":  self._midi_out.is_open,
                "port":  getattr(self._midi_out, "_port_name", None),
            }
        if self._link is not None:
            s = self._link.get_state()
            status["link"] = {
                "available": s.is_available,
                "tempo_bpm": round(s.tempo_bpm, 1),
                "playing":   s.is_playing,
                "peers":     getattr(self._link, "peer_count", 0),
            }
        if self._osc is not None:
            s = self._osc.get_state()
            status["osc"] = {
                "available": s.is_available,
                "rx_port":   getattr(self._osc, "_rx_port", None),
                "tx_port":   getattr(self._osc, "_tx_port", None),
            }
        return status

    # ── Source priority logic ─────────────────────────────────────────────────

    def _active_external_source(self) -> Optional[SyncSourceType]:
        """Return the highest-priority active external source, or None."""
        if self._link is not None:
            s = self._link.get_state()
            # is_available = Link session running; peer_count > 0 or just connected
            if s.is_available:
                return SyncSourceType.ABLETON_LINK
        if self._midi_in is not None:
            s = self._midi_in.get_state()
            if s.is_available:
                return SyncSourceType.MIDI_CLOCK
        if self._osc is not None:
            s = self._osc.get_state()
            if s.is_available:
                return SyncSourceType.OSC
        return None

    # ── Callbacks from sources ────────────────────────────────────────────────

    def _on_midi_tempo(self, bpm: float) -> None:
        if self._active_external_source() == SyncSourceType.MIDI_CLOCK:
            self._active_source = SyncSourceType.MIDI_CLOCK
            if self._engine_set_tempo:
                self._engine_set_tempo(bpm)

    def _on_midi_play(self, playing: bool) -> None:
        if self._active_external_source() == SyncSourceType.MIDI_CLOCK:
            if self._engine_set_playing:
                self._engine_set_playing(playing)

    def _on_link_tempo(self, bpm: float) -> None:
        # Link has highest priority if peers > 0
        if self._active_external_source() == SyncSourceType.ABLETON_LINK:
            self._active_source = SyncSourceType.ABLETON_LINK
            if self._engine_set_tempo:
                self._engine_set_tempo(bpm)

    def _on_link_play(self, playing: bool) -> None:
        if self._active_external_source() == SyncSourceType.ABLETON_LINK:
            if self._engine_set_playing:
                self._engine_set_playing(playing)

    def _on_osc_tempo(self, bpm: float) -> None:
        if self._active_external_source() == SyncSourceType.OSC:
            self._active_source = SyncSourceType.OSC
            if self._engine_set_tempo:
                self._engine_set_tempo(bpm)

    def _on_osc_play(self, playing: bool) -> None:
        if self._active_external_source() == SyncSourceType.OSC:
            if self._engine_set_playing:
                self._engine_set_playing(playing)


# ── Module-level singleton ─────────────────────────────────────────────────────

_manager: Optional[SyncManager] = None


def get_manager() -> SyncManager:
    global _manager
    if _manager is None:
        _manager = SyncManager()
    return _manager
