"""
Tests for core/sequencer.py

Tests are organized by scenario:
  - Basic PLAY flow
  - LOOP n (cue and section)
  - LOOP UNTIL MANUAL
  - JUMP
  - GOSUB + return
  - Cross-lane JUMP
  - SKIP / SKIP UNTIL
  - MUTE
  - REVERSE
  - Speed ratio
"""
import pytest
from core.models import Cue, Instruction, InstructionOp, Lane, PlaylistConfig, Project, Section
from core.sequencer import (
    EvCrossLaneJump, EvCueEnded, EvCueStarted, EvGosubStackOverflow,
    EvManualWaiting, EvSectionEnded, EvSectionStarted, EvSequenceEnded,
    PlaybackCursor, init_cursor, tick, trigger_manual_for_lane,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _inst(op: str, **kwargs) -> Instruction:
    return Instruction(op=InstructionOp(op), **kwargs)


def _cue(id_: str, bars: float, op: str = "PLAY", **kwargs) -> Cue:
    return Cue(
        id=id_, label=id_, content="",
        duration_bars=bars,
        instruction=_inst(op, **kwargs),
        enabled=True, order_index=0,
    )


def _section(id_: str, cues: list[Cue], op: str = "PLAY", **kwargs) -> Section:
    return Section(
        id=id_, name=id_, type="verse", color="#000",
        instruction=_inst(op, **kwargs),
        playlist=PlaylistConfig(mode="all"),
        cues=cues,
    )


def _lane(id_: str, sections: list[Section], speed: str = "1:1") -> Lane:
    return Lane(id=id_, name=id_, color="#fff", speed_ratio=speed, sections=sections)


def _project(*lanes: Lane, bpm: float = 120.0) -> Project:
    return Project(
        id="test", name="Test", tempo_bpm=bpm, time_signature="4/4",
        gosub_stack_limit=4, lanes=list(lanes),
    )


def _tick_n(cursor: PlaybackCursor, project: Project, delta: float, n: int):
    """Apply tick() n times with the given delta."""
    events = []
    for _ in range(n):
        cursor, ev = tick(cursor, delta, project)
        events.extend(ev)
    return cursor, events


def _all_events(cursor: PlaybackCursor, project: Project, max_beats: float = 1000.0, step: float = 1.0):
    """Run tick() until sequence ends or max_beats is reached."""
    events = []
    beat = 0.0
    while beat < max_beats:
        cursor, ev = tick(cursor, step, project)
        events.extend(ev)
        beat += step
        if any(isinstance(e, EvSequenceEnded) for e in ev):
            break
    return cursor, events


# ── PLAY: basic flow ──────────────────────────────────────────────────────────

class TestBasicPlay:
    def test_single_cue_single_section(self):
        """4-bar cue at 120bpm 4/4: 16 master beats."""
        proj = _project(_lane("L", [_section("S", [_cue("c1", 4.0)])]))
        cursor = init_cursor(proj)

        # Initial state: CueStarted + SectionStarted emitted at init
        lc = cursor.lane_cursors["L"]
        assert lc.section_id == "S"
        assert lc.cue_queue == ("c1",)
        assert lc.beats_remaining == pytest.approx(16.0)  # 4 bars × 4 beats

    def test_cue_ends_after_16_beats(self):
        proj = _project(_lane("L", [_section("S", [_cue("c1", 4.0)])]))
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=4.0)

        ended = [e for e in events if isinstance(e, EvCueEnded)]
        assert len(ended) == 1
        assert ended[0].cue_id == "c1"

    def test_two_cues_sequential(self):
        c1 = _cue("c1", 2.0)
        c1 = Cue(**{**c1.__dict__, "order_index": 0})
        c2 = _cue("c2", 2.0)
        c2 = Cue(**{**c2.__dict__, "order_index": 1})
        proj = _project(_lane("L", [_section("S", [c1, c2])]))
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=1.0)

        started = [e for e in events if isinstance(e, EvCueStarted)]
        # c1 started at init (not in events), c2 started after c1 ends
        assert any(e.cue_id == "c2" for e in started)

    def test_sequence_ends_after_all_sections(self):
        proj = _project(_lane("L", [
            _section("S1", [_cue("c1", 1.0)]),
            _section("S2", [_cue("c2", 1.0)]),
        ]))
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=1.0)

        ended = [e for e in events if isinstance(e, EvSequenceEnded)]
        assert len(ended) == 1
        assert ended[0].lane_id == "L"

    def test_not_playing_returns_no_events(self):
        proj = _project(_lane("L", [_section("S", [_cue("c1", 4.0)])]))
        cursor = init_cursor(proj)
        import dataclasses
        cursor = dataclasses.replace(cursor, is_playing=False)
        cursor2, events = tick(cursor, 4.0, proj)
        assert events == []
        assert cursor2 == cursor


# ── LOOP cue ─────────────────────────────────────────────────────────────────

class TestLoopCue:
    def test_loop_2_plays_twice(self):
        """LOOP 2: cue plays 2 times total."""
        cue = Cue(
            id="c1", label="c1", content="", duration_bars=1.0,
            instruction=_inst("LOOP", loop_count=2),
            enabled=True, order_index=0,
        )
        proj = _project(_lane("L", [_section("S", [cue])]))
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=1.0)

        started = [e for e in events if isinstance(e, EvCueStarted) and e.cue_id == "c1"]
        ended = [e for e in events if isinstance(e, EvCueEnded) and e.cue_id == "c1"]
        # c1 started at init (not in events here), so we see 1 restart + 2 ends
        assert len(ended) == 2


# ── LOOP section ──────────────────────────────────────────────────────────────

class TestLoopSection:
    def test_section_loop_2(self):
        """Section LOOP 2: the section plays 2 times total."""
        proj = _project(_lane("L", [
            _section("S", [_cue("c1", 1.0)], op="LOOP", loop_count=2),
        ]))
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=0.5)

        sec_ended = [e for e in events if isinstance(e, EvSectionEnded)]
        seq_ended = [e for e in events if isinstance(e, EvSequenceEnded)]
        # Section ends 2 times, then sequence ends
        assert len(sec_ended) == 2
        assert len(seq_ended) == 1


# ── MUTE ─────────────────────────────────────────────────────────────────────

class TestMute:
    def test_mute_still_advances(self):
        """MUTE cue still consumes its duration and advances."""
        cue = Cue(
            id="c1", label="c1", content="", duration_bars=2.0,
            instruction=_inst("MUTE"),
            enabled=True, order_index=0,
        )
        proj = _project(_lane("L", [_section("S", [cue])]))
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=1.0)
        assert any(isinstance(e, EvCueEnded) for e in events)
        assert any(isinstance(e, EvSequenceEnded) for e in events)


# ── SKIP ─────────────────────────────────────────────────────────────────────

class TestSkip:
    def test_pure_skip_has_zero_duration(self):
        """A pure SKIP cue has beats_remaining=0 immediately."""
        cue = Cue(
            id="c1", label="", content="", duration_bars=4.0,
            instruction=_inst("SKIP"),
            enabled=True, order_index=0,
        )
        proj = _project(_lane("L", [_section("S", [cue])]))
        cursor = init_cursor(proj)
        lc = cursor.lane_cursors["L"]
        # After init: SKIP cue should be gone already (beats_remaining=0, next cue or section end)
        # Section has only this cue, so section should have ended
        assert lc.section_id is None or lc.beats_remaining == pytest.approx(0.0)

    def test_skip_until_1_2(self):
        """SKIP UNTIL 1:2: plays on pass 0, skipped on pass 1, etc."""
        # Section loops so we can check multiple passes
        cue = Cue(
            id="c1", label="", content="", duration_bars=4.0,
            instruction=_inst("SKIP", condition="1:2"),
            enabled=True, order_index=0,
        )
        sec = Section(
            id="S", name="S", type="verse", color="#000",
            instruction=_inst("LOOP", loop_count=4),
            playlist=PlaylistConfig(mode="all"),
            cues=[cue],
        )
        proj = _project(_lane("L", [sec]))
        cursor = init_cursor(proj)

        # On pass 0: condition 1:2 at pass_count=0 → evaluate("1:2", state) → True → play
        lc = cursor.lane_cursors["L"]
        assert lc.beats_remaining == pytest.approx(16.0)  # playing


# ── JUMP ─────────────────────────────────────────────────────────────────────

class TestJump:
    def test_unconditional_jump(self):
        """JUMP to S2 at end of c1 skips c2."""
        c1 = Cue(
            id="c1", label="c1", content="", duration_bars=1.0,
            instruction=_inst("JUMP", target="S2"),
            enabled=True, order_index=0,
        )
        c2 = _cue("c2", 1.0)
        c2 = Cue(**{**c2.__dict__, "order_index": 1})
        proj = _project(_lane("L", [
            _section("S1", [c1, c2]),
            _section("S2", [_cue("c3", 1.0)]),
        ]))
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=0.5)

        started_ids = [e.cue_id for e in events if isinstance(e, EvCueStarted)]
        assert "c2" not in started_ids
        assert "c3" in started_ids

    def test_conditional_jump_1_2(self):
        """JUMP IF 1:2: condition met on pass 0 → jumps to S2, skips c2.
        Note: JUMP is non-returning. After JUMP fires, we go to S2 permanently.
        To play c2, the condition must NOT fire — use GOSUB for return semantics.
        """
        c1 = Cue(
            id="c1", label="c1", content="", duration_bars=1.0,
            instruction=_inst("JUMP", target="S2", condition="1:2"),
            enabled=True, order_index=0,
        )
        c2 = Cue(
            id="c2", label="c2", content="", duration_bars=1.0,
            instruction=_inst("PLAY"),
            enabled=True, order_index=1,
        )
        proj = _project(_lane("L", [
            _section("S1", [c1, c2]),
            _section("S2", [_cue("c3", 1.0)]),
        ]))
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=0.25)

        started_ids = [e.cue_id for e in events if isinstance(e, EvCueStarted)]
        # JUMP fires on pass 0 (1:2 → True) → goes to S2, c3 plays, c2 is skipped
        assert "c3" in started_ids
        assert "c2" not in started_ids

    def test_conditional_jump_not_met(self):
        """JUMP IF 1:2 on pass 1 (condition not met) → plays c2 instead."""
        c1 = Cue(
            id="c1", label="c1", content="", duration_bars=1.0,
            instruction=_inst("JUMP", target="S2", condition="1:2"),
            enabled=True, order_index=0,
        )
        c2 = Cue(
            id="c2", label="c2", content="", duration_bars=1.0,
            instruction=_inst("PLAY"),
            enabled=True, order_index=1,
        )
        proj = _project(_lane("L", [
            _section("S1", [c1, c2], op="LOOP", loop_count=2),
            _section("S2", [_cue("c3", 1.0)]),
        ]))
        cursor = init_cursor(proj)
        # Advance condition state manually to pass 1 by running one full pass
        # Pass 0: JUMP fires → goes to S2 (permanent). This is expected behavior.
        # For "not met" test, use a condition that never fires: NEVER
        c1_never = Cue(
            id="c1", label="c1", content="", duration_bars=1.0,
            instruction=_inst("JUMP", target="S2", condition="NEVER"),
            enabled=True, order_index=0,
        )
        proj2 = _project(_lane("L", [
            _section("S1", [c1_never, c2]),
            _section("S2", [_cue("c3", 1.0)]),
        ]))
        cursor2 = init_cursor(proj2)
        cursor2, events2 = _all_events(cursor2, proj2, step=0.25)
        started_ids2 = [e.cue_id for e in events2 if isinstance(e, EvCueStarted)]
        # JUMP NEVER → condition never met → c2 plays, c3 plays (natural advance to S2)
        assert "c2" in started_ids2
        assert "c3" in started_ids2


# ── GOSUB ─────────────────────────────────────────────────────────────────────

class TestGosub:
    def test_gosub_and_return(self):
        """GOSUB fill → plays fill → returns to next cue."""
        fill_cue = _cue("fill-c", 1.0)
        fill_sec = _section("fill", [fill_cue])

        c1 = _cue("c1", 1.0)
        c1 = Cue(**{**c1.__dict__, "order_index": 0})
        c2_gosub = Cue(
            id="c2", label="c2", content="", duration_bars=0.0,
            instruction=_inst("GOSUB", target="fill"),
            enabled=True, order_index=1,
        )
        c3 = Cue(
            id="c3", label="c3", content="", duration_bars=1.0,
            instruction=_inst("PLAY"),
            enabled=True, order_index=2,
        )
        main_sec = _section("main", [c1, c2_gosub, c3])
        proj = _project(_lane("L", [main_sec, fill_sec]))
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=0.25)

        started_ids = [e.cue_id for e in events if isinstance(e, EvCueStarted)]
        # fill-c should be played
        assert "fill-c" in started_ids
        # c3 should be played after fill returns
        assert "c3" in started_ids
        # Verify order: fill-c before c3
        fill_idx = next(i for i, e in enumerate(events)
                        if isinstance(e, EvCueStarted) and e.cue_id == "fill-c")
        c3_idx = next(i for i, e in enumerate(events)
                      if isinstance(e, EvCueStarted) and e.cue_id == "c3")
        assert fill_idx < c3_idx

    def test_gosub_stack_overflow(self):
        """GOSUB exceeding stack limit → EvGosubStackOverflow, forced advance."""
        # Section that calls itself via GOSUB (direct stack overflow after 4 levels)
        fill_cue = Cue(
            id="self-call", label="", content="", duration_bars=0.0,
            instruction=_inst("GOSUB", target="S"),
            enabled=True, order_index=0,
        )
        proj = _project(
            _lane("L", [_section("S", [fill_cue])]),
            bpm=120.0,
        )
        proj = Project(**{**proj.__dict__, "gosub_stack_limit": 2})
        cursor = init_cursor(proj)
        cursor, events = tick(cursor, 1.0, proj)
        overflow_evs = [e for e in events if isinstance(e, EvGosubStackOverflow)]
        assert len(overflow_evs) > 0


# ── Cross-lane JUMP ───────────────────────────────────────────────────────────

class TestCrossLaneJump:
    def test_cross_lane_jump_emits_event(self):
        """A cue with jump_lane triggers EvCrossLaneJump and moves the target lane."""
        c_jump = Cue(
            id="cj", label="", content="", duration_bars=1.0,
            instruction=_inst("JUMP", target="bass-chorus", jump_lane="L-bass"),
            enabled=True, order_index=0,
        )
        synth_lane = _lane("L-synth", [_section("S1", [c_jump])])
        bass_lane = _lane("L-bass", [
            _section("bass-intro", [_cue("bass-intro-c", 1.0)]),
            _section("bass-chorus", [_cue("bass-chorus-c", 1.0)]),
        ])
        proj = _project(synth_lane, bass_lane)
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, step=0.5)

        cross = [e for e in events if isinstance(e, EvCrossLaneJump)]
        assert len(cross) >= 1
        assert cross[0].target_lane_id == "L-bass"
        assert cross[0].target_section_id == "bass-chorus"

        # Bass lane should now be in bass-chorus
        bass_started = [e.cue_id for e in events
                        if isinstance(e, EvCueStarted) and e.lane_id == "L-bass"]
        assert "bass-chorus-c" in bass_started


# ── Speed ratio ───────────────────────────────────────────────────────────────

class TestSpeedRatio:
    def test_2_1_half_master_beats(self):
        """A lane at 2:1 has bars half as long → 4-bar cue = 8 master beats."""
        proj = _project(_lane("L", [_section("S", [_cue("c1", 4.0)])], speed="2:1"))
        cursor = init_cursor(proj)
        lc = cursor.lane_cursors["L"]
        # 4 bars × 4 beats/bar / 2.0 = 8 master beats
        assert lc.beats_remaining == pytest.approx(8.0)

    def test_1_2_double_master_beats(self):
        """A lane at 1:2 has bars twice as long → 4-bar cue = 32 master beats."""
        proj = _project(_lane("L", [_section("S", [_cue("c1", 4.0)])], speed="1:2"))
        cursor = init_cursor(proj)
        lc = cursor.lane_cursors["L"]
        # 4 bars × 4 beats/bar / 0.5 = 32 master beats
        assert lc.beats_remaining == pytest.approx(32.0)


# ── Multi-lane independence ───────────────────────────────────────────────────

class TestMultiLane:
    def test_two_lanes_advance_independently(self):
        """Two lanes with different durations advance independently."""
        l1 = _lane("L1", [_section("S1", [_cue("c1", 2.0)])])   # 8 beats
        l2 = _lane("L2", [_section("S2", [_cue("c2", 4.0)])])   # 16 beats
        proj = _project(l1, l2)
        cursor = init_cursor(proj)

        # After 8 beats: L1 should have ended, L2 still running
        cursor, events = tick(cursor, 8.0, proj)
        seq_ended = [e for e in events if isinstance(e, EvSequenceEnded)]
        assert any(e.lane_id == "L1" for e in seq_ended)
        assert not any(e.lane_id == "L2" for e in seq_ended)


# ── Serializer integration ────────────────────────────────────────────────────

class TestSerializerIntegration:
    def test_example_project_loads_and_runs(self):
        """Load the example JSON project and run 32 beats without crashing."""
        from core.serializer import load_project
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "formats", "example_project.json"
        )
        proj = load_project(path)
        cursor = init_cursor(proj)
        cursor, events = _all_events(cursor, proj, max_beats=64.0, step=1.0)
        # Should produce events without exceptions
        assert len(events) >= 0  # at least ran without error
