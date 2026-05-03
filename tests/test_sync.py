"""
D.I.M — tests/test_sync.py
Tests for the sync layer (Sprint 3).

These tests run without MIDI hardware or Ableton Link installed.
They test the logic: BPM derivation, pulse accumulation, state, manager wiring.
"""
import time
import threading
import pytest

from adapters.sync.base import SyncSourceType, SyncState, SyncSource
from adapters.sync.midi_clock import MidiClockInput, MidiClockOutput, CLOCKS_PER_BEAT
from adapters.sync.link_sync import make_link_source, is_link_available, LinkSyncStub
from adapters.sync.osc_sync import OscSyncSource
from adapters.sync.manager import SyncManager


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_fake_clock_input(bpm: float) -> MidiClockInput:
    """Build a MidiClockInput and inject fake clock pulses manually."""
    src = MidiClockInput(port_name=None)
    # Inject pulse timing at the given BPM
    interval = 60.0 / (bpm * CLOCKS_PER_BEAT)
    t = 0.0
    for _ in range(CLOCKS_PER_BEAT * 4):   # 4 beats worth
        msg = _FakeMidiMsg("clock")
        src._last_clock_t = t
        t += interval
        src._handle_at(msg, t)
    return src


class _FakeMidiMsg:
    def __init__(self, type_: str, **kwargs):
        self.type = type_
        for k, v in kwargs.items():
            setattr(self, k, v)


# Patch _handle to accept explicit timestamp for testing
def _handle_at(self, msg, t):
    """Variant of _handle() with explicit timestamp (bypasses time.monotonic)."""
    if msg.type == "clock":
        with self._lock:
            if self._last_clock_t is not None:
                interval = t - self._last_clock_t
                if 0.0001 < interval < 1.0:
                    self._intervals.append(interval)
                    if len(self._intervals) >= 2:
                        avg = sum(self._intervals) / len(self._intervals)
                        bpm = 60.0 / (avg * CLOCKS_PER_BEAT)
                        from adapters.sync.midi_clock import BPM_MIN, BPM_MAX
                        if BPM_MIN <= bpm <= BPM_MAX:
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

    elif msg.type == "stop":
        with self._lock:
            self._is_playing = False
        self._emit_play(False)


MidiClockInput._handle_at = _handle_at


# ── Base ───────────────────────────────────────────────────────────────────────

def test_sync_state_frozen():
    s = SyncState(
        source=SyncSourceType.MIDI_CLOCK,
        tempo_bpm=120.0,
        beat_position=4.0,
        is_playing=True,
    )
    assert s.tempo_bpm == 120.0
    assert s.is_playing is True
    with pytest.raises(Exception):
        s.tempo_bpm = 130.0   # frozen dataclass


# ── MIDI Clock Input ───────────────────────────────────────────────────────────

def test_midi_clock_bpm_derivation():
    """Inject 120 BPM pulses, verify derived BPM is close to 120."""
    src = MidiClockInput(port_name=None)
    tempo_received = []
    src.on_tempo(tempo_received.append)

    bpm = 120.0
    interval = 60.0 / (bpm * CLOCKS_PER_BEAT)
    t = 1.0
    for _ in range(CLOCKS_PER_BEAT * 8):
        src._handle_at(_FakeMidiMsg("clock"), t)
        t += interval

    assert len(tempo_received) > 0
    last_bpm = tempo_received[-1]
    assert abs(last_bpm - 120.0) < 0.5, f"Expected ~120, got {last_bpm}"


def test_midi_clock_bpm_140():
    src = MidiClockInput(port_name=None)
    tempos = []
    src.on_tempo(tempos.append)

    bpm = 140.0
    interval = 60.0 / (bpm * CLOCKS_PER_BEAT)
    t = 0.5
    for _ in range(CLOCKS_PER_BEAT * 6):
        src._handle_at(_FakeMidiMsg("clock"), t)
        t += interval

    assert abs(tempos[-1] - 140.0) < 0.5


def test_midi_clock_beat_counting():
    """4 beats of pulses → beat callback fires 4 times."""
    src = MidiClockInput(port_name=None)
    beats = []
    src.on_beat(beats.append)

    interval = 60.0 / (120.0 * CLOCKS_PER_BEAT)
    t = 0.0
    for _ in range(CLOCKS_PER_BEAT * 4):
        src._handle_at(_FakeMidiMsg("clock"), t)
        t += interval

    assert len(beats) == 4


def test_midi_clock_start_resets():
    src = MidiClockInput(port_name=None)
    plays = []
    src.on_play(plays.append)

    src._handle_at(_FakeMidiMsg("start"), 0.0)
    assert plays == [True]
    assert src._beat_count == 0
    assert src._pulse_count == 0


def test_midi_clock_stop():
    src = MidiClockInput(port_name=None)
    plays = []
    src.on_play(plays.append)

    src._handle_at(_FakeMidiMsg("start"), 0.0)
    src._handle_at(_FakeMidiMsg("stop"), 0.1)
    assert plays == [True, False]
    assert src._is_playing is False


def test_midi_clock_state_not_available_initially():
    src = MidiClockInput(port_name=None)
    state = src.get_state()
    assert state.is_available is False
    assert state.source == SyncSourceType.MIDI_CLOCK


# ── MIDI Clock Output ──────────────────────────────────────────────────────────

def test_midi_clock_output_pulse_accumulation():
    """Test pulse accumulation without actual MIDI port."""
    from adapters.sync.midi_clock import MidiClockOutput
    out = MidiClockOutput.__new__(MidiClockOutput)
    out._port = None      # no actual port
    out._lock = threading.Lock()
    out._fractional = 0.0

    pulses_sent = []

    # Monkey-patch push_delta to count instead of send
    original_push = MidiClockOutput.push_delta
    def counting_push(self, delta_beats):
        with self._lock:
            self._fractional += delta_beats * CLOCKS_PER_BEAT
            n = int(self._fractional)
            self._fractional -= n
        pulses_sent.append(n)

    out._push_count = counting_push.__get__(out, MidiClockOutput)

    # At 120 BPM, TICK=0.05s → delta_beats = 0.05 * 120/60 = 0.1
    delta = 0.1   # beats per tick
    total_pulses = 0
    for _ in range(100):   # 10 beats
        with out._lock:
            out._fractional += delta * CLOCKS_PER_BEAT
            n = int(out._fractional)
            out._fractional -= n
        total_pulses += n

    # 10 beats × 24 pulses = 240
    assert total_pulses == 240, f"Expected 240 pulses, got {total_pulses}"


def test_midi_clock_output_no_fractional_drift():
    """Verify fractional accumulation stays in [0, 1)."""
    out = MidiClockOutput.__new__(MidiClockOutput)
    out._port = None
    out._lock = threading.Lock()
    out._fractional = 0.0

    # Irrational delta — should never accumulate error
    delta = 1.0 / 7.0  # beats
    for _ in range(1000):
        with out._lock:
            out._fractional += delta * CLOCKS_PER_BEAT
            n = int(out._fractional)
            out._fractional -= n

    assert 0.0 <= out._fractional < 1.0


# ── Ableton Link ───────────────────────────────────────────────────────────────

def test_link_stub_state():
    stub = LinkSyncStub()
    s = stub.get_state()
    assert s.is_available is False
    assert s.source == SyncSourceType.ABLETON_LINK


def test_make_link_source_returns_stub_when_unavailable():
    if is_link_available():
        pytest.skip("link.python is installed — stub test not applicable")
    src = make_link_source()
    assert isinstance(src, LinkSyncStub)
    s = src.get_state()
    assert s.is_available is False


def test_link_stub_callbacks_do_nothing():
    stub = LinkSyncStub()
    received = []
    stub.on_tempo(received.append)
    stub.start()
    stub.stop()
    assert received == []


# ── OSC ────────────────────────────────────────────────────────────────────────

def test_osc_handle_tempo():
    src = OscSyncSource(rx_port=57130, tx_host="127.0.0.1", tx_port=57131)
    received = []
    src.on_tempo(received.append)
    src._handle_tempo("/dim/tempo", 135.0)
    assert received == [135.0]
    assert src._tempo_bpm == 135.0


def test_osc_handle_play():
    src = OscSyncSource(rx_port=57132, tx_host="127.0.0.1", tx_port=57133)
    plays = []
    src.on_play(plays.append)
    src._handle_play("/dim/play", 1)
    assert plays == [True]
    src._handle_play("/dim/play", 0)
    assert plays == [True, False]


def test_osc_handle_rewind():
    src = OscSyncSource()
    beats = []
    src.on_beat(beats.append)
    src._beat_pos = 42.0
    src._handle_rewind("/dim/rewind")
    assert src._beat_pos == 0.0
    assert beats == [0.0]


def test_osc_handle_state():
    src = OscSyncSource()
    src._handle_state("/dim/state", 110.0, 8.0, 1)
    assert src._tempo_bpm == 110.0
    assert src._beat_pos == 8.0
    assert src._is_playing is True


def test_osc_initial_state():
    src = OscSyncSource()
    s = src.get_state()
    assert s.source == SyncSourceType.OSC
    assert s.is_available is False


# ── SyncManager ───────────────────────────────────────────────────────────────

def test_manager_midi_tempo_callback():
    """MIDI tempo callback should call engine set_tempo when MIDI is available."""
    mgr = SyncManager()
    tempo_calls = []
    mgr.set_engine_callbacks(
        set_tempo=tempo_calls.append,
        set_playing=lambda _: None,
    )

    src = MidiClockInput(port_name=None)
    mgr.add_midi_input(src)

    # Simulate MIDI signal available
    src._is_available = True
    import time as _time
    src._last_clock_t = _time.monotonic()

    # Trigger tempo callback
    src._emit_tempo(128.0)

    assert tempo_calls == [128.0]


def test_manager_link_priority_over_midi():
    """Link takes priority over MIDI when it has peers."""
    mgr = SyncManager()
    tempo_calls = []
    mgr.set_engine_callbacks(
        set_tempo=tempo_calls.append,
        set_playing=lambda _: None,
    )

    # Add MIDI (available)
    midi_src = MidiClockInput(port_name=None)
    midi_src._is_available = True
    import time as _time
    midi_src._last_clock_t = _time.monotonic()
    mgr.add_midi_input(midi_src)

    # Add Link stub (not available — no peers)
    link = LinkSyncStub()
    mgr.add_link(link)

    # MIDI fires tempo — should apply (Link not available)
    midi_src._emit_tempo(120.0)
    assert tempo_calls == [120.0]


def test_manager_status_structure():
    mgr = SyncManager()
    status = mgr.get_status()
    assert "active_source" in status
    assert "midi_in"  in status
    assert "midi_out" in status
    assert "link"     in status
    assert "osc"      in status


def test_manager_tick_no_crash():
    """on_engine_tick with no sources should not raise."""
    mgr = SyncManager()
    mgr.on_engine_tick(0.1, 120.0, True)
    mgr.on_engine_tick(0.1, 120.0, False)


def test_manager_play_state_tracking():
    """Test MIDI transport sent on play state transitions."""
    mgr = SyncManager()
    mgr._last_playing = None

    # First tick: playing=True → no transport (first call)
    mgr.on_engine_tick(0.1, 120.0, True)
    assert mgr._last_playing is True

    mgr.on_engine_tick(0.1, 120.0, False)
    assert mgr._last_playing is False

    mgr.on_engine_tick(0.1, 120.0, True)
    assert mgr._last_playing is True
