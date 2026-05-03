"""Tests for core/playlist.py"""
import pytest
from core.models import Cue, Instruction, InstructionOp, PlaylistConfig, Section


def _make_cue(id_: str, order: int, enabled: bool = True) -> Cue:
    return Cue(
        id=id_,
        label=id_,
        content="",
        duration_bars=4.0,
        instruction=Instruction(op=InstructionOp.PLAY),
        enabled=enabled,
        order_index=order,
    )


def _make_section(cues: list[Cue], playlist: PlaylistConfig) -> Section:
    return Section(
        id="sec-test",
        name="Test",
        type="verse",
        color="#000",
        instruction=Instruction(op=InstructionOp.PLAY),
        playlist=playlist,
        cues=cues,
    )


from core.playlist import build_cue_queue


class TestBuildCueQueueAll:
    def test_all_enabled(self):
        cues = [_make_cue(f"c{i}", i) for i in range(3)]
        sec = _make_section(cues, PlaylistConfig(mode="all"))
        result = build_cue_queue(sec)
        assert [c.id for c in result] == ["c0", "c1", "c2"]

    def test_some_disabled(self):
        cues = [
            _make_cue("c0", 0, enabled=True),
            _make_cue("c1", 1, enabled=False),
            _make_cue("c2", 2, enabled=True),
        ]
        sec = _make_section(cues, PlaylistConfig(mode="all"))
        result = build_cue_queue(sec)
        assert [c.id for c in result] == ["c0", "c2"]

    def test_empty(self):
        sec = _make_section([], PlaylistConfig(mode="all"))
        assert build_cue_queue(sec) == []

    def test_order_by_order_index(self):
        # Cues added in wrong order, should be sorted by order_index
        cues = [_make_cue("c2", 2), _make_cue("c0", 0), _make_cue("c1", 1)]
        sec = _make_section(cues, PlaylistConfig(mode="all"))
        result = build_cue_queue(sec)
        assert [c.id for c in result] == ["c0", "c1", "c2"]


class TestBuildCueQueueNth:
    def test_nth_2_pass_0(self):
        """nth=2, pass 0 → cues at even indices: c0, c2"""
        cues = [_make_cue(f"c{i}", i) for i in range(4)]
        sec = _make_section(cues, PlaylistConfig(mode="nth", nth=2))
        result = build_cue_queue(sec, pass_index=0)
        assert [c.id for c in result] == ["c0", "c2"]

    def test_nth_2_pass_1(self):
        """nth=2, pass 1 → cues at odd indices: c1, c3"""
        cues = [_make_cue(f"c{i}", i) for i in range(4)]
        sec = _make_section(cues, PlaylistConfig(mode="nth", nth=2))
        result = build_cue_queue(sec, pass_index=1)
        assert [c.id for c in result] == ["c1", "c3"]

    def test_nth_2_pass_2_wraps(self):
        """pass 2 → same as pass 0 (2 % 2 == 0)"""
        cues = [_make_cue(f"c{i}", i) for i in range(4)]
        sec = _make_section(cues, PlaylistConfig(mode="nth", nth=2))
        r0 = build_cue_queue(sec, pass_index=0)
        r2 = build_cue_queue(sec, pass_index=2)
        assert [c.id for c in r0] == [c.id for c in r2]


class TestBuildCueQueueRatio:
    def test_ratio_3_4(self):
        """3:4 → first 3 out of every 4 cues"""
        cues = [_make_cue(f"c{i}", i) for i in range(8)]
        sec = _make_section(cues, PlaylistConfig(mode="ratio", ratio="3:4"))
        result = build_cue_queue(sec)
        # indices 0,1,2 → play; 3 → skip; 4,5,6 → play; 7 → skip
        assert [c.id for c in result] == ["c0", "c1", "c2", "c4", "c5", "c6"]

    def test_ratio_1_2(self):
        """1:2 → every other cue"""
        cues = [_make_cue(f"c{i}", i) for i in range(4)]
        sec = _make_section(cues, PlaylistConfig(mode="ratio", ratio="1:2"))
        result = build_cue_queue(sec)
        assert [c.id for c in result] == ["c0", "c2"]


class TestBuildCueQueueCustom:
    def test_custom_order(self):
        """custom_order=[2,0,1] → reorder cues"""
        cues = [_make_cue(f"c{i}", i) for i in range(3)]
        sec = _make_section(cues, PlaylistConfig(mode="custom", custom_order=[2, 0, 1]))
        result = build_cue_queue(sec)
        assert [c.id for c in result] == ["c2", "c0", "c1"]

    def test_custom_order_out_of_bounds(self):
        """Out-of-bound indices should be silently ignored"""
        cues = [_make_cue(f"c{i}", i) for i in range(2)]
        sec = _make_section(cues, PlaylistConfig(mode="custom", custom_order=[0, 5, 1]))
        result = build_cue_queue(sec)
        assert [c.id for c in result] == ["c0", "c1"]
