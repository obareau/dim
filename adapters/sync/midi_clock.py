"""
D.I.M — adapters/sync/midi_clock.py
MIDI Clock input and output.

MIDI Clock spec:
  - F8 = Clock pulse  (24 per quarter note / beat)
  - FA = Start
  - FB = Continue
  - FC = Stop
  - F2 = Song Position Pointer (14-bit, in MIDI beats = 1/16th notes)

Input:  measures time between F8 pulses → derives BPM, emits callbacks
Output: sends 24 F8 pulses per beat in sync with the engine tick loop
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

from .base import SyncSource, SyncSourceType, SyncState

try:
    import mido
    _MIDO_AVAILABLE = True
except ImportError:
    _MIDO_AVAILABLE = False


# ── Constants ─────────────────────────────────────────────────────────────────

CLOCKS_PER_BEAT   = 24
BPM_WINDOW        = 8       # how many clock intervals to average for BPM
BPM_MIN           = 20.0
BPM_MAX           = 300.0
TIMEOUT_SEC       = 2.0     # no clock for this long → not_available


# ── MIDI Clock Input ───────────────────────────────────────────────────────────

class MidiClockInput(SyncSource):
    """
    Listens to a MIDI port for Clock messages.
    Derives BPM from pulse timing, emits tempo/play callbacks.
    Thread-safe.
    """

    def __init__(self, port_name: Optional[str] = None) -> None:
        super().__init__()
        self._port_name   = port_name
        self._thread: Optional[threading.Thread] = None
        self._running     = False
        self._lock        = threading.Lock()

        # state
        self._tempo_bpm   = 120.0
        self._beat_pos    = 0.0
        self._is_playing  = False
        self._is_available = False
        self._last_clock_t: Optional[float] = None
        self._intervals: deque[float] = deque(maxlen=BPM_WINDOW)
        self._pulse_count = 0          # clocks since last beat
        self._beat_count  = 0          # total beats since start

    @property
    def source_type(self) -> SyncSourceType:
        return SyncSourceType.MIDI_CLOCK

    def list_ports(self) -> list[str]:
        if not _MIDO_AVAILABLE:
            return []
        return mido.get_input_names()

    def start(self) -> None:
        if not _MIDO_AVAILABLE:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="dim-midi-in"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def get_state(self) -> SyncState:
        with self._lock:
            # check timeout
            available = self._is_available
            if self._last_clock_t is not None:
                if time.monotonic() - self._last_clock_t > TIMEOUT_SEC:
                    available = False
            return SyncState(
                source=SyncSourceType.MIDI_CLOCK,
                tempo_bpm=self._tempo_bpm,
                beat_position=self._beat_pos,
                is_playing=self._is_playing,
                is_available=available,
            )

    def _run(self) -> None:
        port_name = self._port_name
        try:
            with mido.open_input(port_name) as port:
                while self._running:
                    for msg in port.iter_pending():
                        self._handle(msg)
                    # timeout check
                    if self._last_clock_t and time.monotonic() - self._last_clock_t > TIMEOUT_SEC:
                        with self._lock:
                            self._is_available = False
                    time.sleep(0.001)
        except Exception as e:
            with self._lock:
                self._is_available = False

    def _handle(self, msg) -> None:
        t = time.monotonic()

        if msg.type == "clock":
            with self._lock:
                if self._last_clock_t is not None:
                    interval = t - self._last_clock_t
                    if 0.0001 < interval < 1.0:   # sanity
                        self._intervals.append(interval)
                        if len(self._intervals) >= 2:
                            avg = sum(self._intervals) / len(self._intervals)
                            bpm = 60.0 / (avg * CLOCKS_PER_BEAT)
                            if BPM_MIN <= bpm <= BPM_MAX:
                                self._tempo_bpm = bpm
                                # emit outside lock
                                bpm_out = bpm
                            else:
                                bpm_out = None
                        else:
                            bpm_out = None
                    else:
                        bpm_out = None
                else:
                    bpm_out = None

                self._last_clock_t = t
                self._is_available = True
                self._pulse_count += 1

                if self._pulse_count >= CLOCKS_PER_BEAT:
                    self._pulse_count = 0
                    self._beat_count += 1
                    self._beat_pos = float(self._beat_count)
                    beat_out = float(self._beat_count)
                else:
                    beat_out = None

            if bpm_out is not None:
                self._emit_tempo(bpm_out)
            if beat_out is not None:
                self._emit_beat(beat_out)

        elif msg.type == "start":
            with self._lock:
                self._is_playing  = True
                self._beat_count  = 0
                self._pulse_count = 0
                self._beat_pos    = 0.0
                self._intervals.clear()
            self._emit_play(True)

        elif msg.type == "continue":
            with self._lock:
                self._is_playing = True
            self._emit_play(True)

        elif msg.type == "stop":
            with self._lock:
                self._is_playing = False
            self._emit_play(False)

        elif msg.type == "songpos":
            # Song Position Pointer: in 1/16th notes → convert to beats (quarter notes)
            sixteenths = msg.pos
            beats = sixteenths / 4.0
            with self._lock:
                self._beat_pos = beats
                self._beat_count = int(beats)
                self._pulse_count = int((beats % 1.0) * CLOCKS_PER_BEAT)
            self._emit_beat(beats)


# ── MIDI Clock Output ──────────────────────────────────────────────────────────

class MidiClockOutput:
    """
    Sends MIDI Clock to a port in sync with the engine.
    Call push_delta(delta_beats, tempo_bpm) from the engine tick loop.
    Accumulates fractional clock pulses and emits integer ones.

    Thread-safe.
    """

    def __init__(self, port_name: Optional[str] = None) -> None:
        self._port_name = port_name
        self._port      = None
        self._lock      = threading.Lock()
        self._fractional: float = 0.0
        self._open()

    def _open(self) -> None:
        if not _MIDO_AVAILABLE:
            return
        try:
            self._port = mido.open_output(self._port_name)
        except Exception:
            self._port = None

    def list_ports(self) -> list[str]:
        if not _MIDO_AVAILABLE:
            return []
        return mido.get_output_names()

    @property
    def is_open(self) -> bool:
        return self._port is not None

    def send_start(self) -> None:
        self._send_raw(0xFA)

    def send_stop(self) -> None:
        self._send_raw(0xFC)

    def send_continue(self) -> None:
        self._send_raw(0xFB)

    def push_delta(self, delta_beats: float) -> None:
        """
        Call once per engine tick.
        delta_beats = beats elapsed this tick.
        Emits the correct integer number of F8 clock pulses.
        """
        if self._port is None:
            return
        with self._lock:
            self._fractional += delta_beats * CLOCKS_PER_BEAT
            n = int(self._fractional)
            self._fractional -= n

        if n > 0:
            clock_msg = mido.Message("clock")
            for _ in range(n):
                try:
                    self._port.send(clock_msg)
                except Exception:
                    break

    def close(self) -> None:
        if self._port:
            try:
                self._port.close()
            except Exception:
                pass
            self._port = None

    def _send_raw(self, byte: int) -> None:
        if not _MIDO_AVAILABLE or self._port is None:
            return
        try:
            msg_map = {0xFA: "start", 0xFB: "continue", 0xFC: "stop"}
            self._port.send(mido.Message(msg_map[byte]))
        except Exception:
            pass
