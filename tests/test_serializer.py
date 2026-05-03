"""Tests for core/serializer.py"""
import json
import os
import pytest

from core.models import InstructionOp
from core.serializer import (
    instruction_from_dict, instruction_to_dict,
    project_from_dict, project_to_dict,
    load_project, _strip_comments,
)


class TestInstructionRoundtrip:
    def test_play(self):
        d = {"op": "PLAY"}
        inst = instruction_from_dict(d)
        assert inst.op == InstructionOp.PLAY
        assert instruction_to_dict(inst) == d

    def test_loop_count(self):
        d = {"op": "LOOP", "loop_count": 4}
        inst = instruction_from_dict(d)
        assert inst.loop_count == 4
        assert instruction_to_dict(inst) == d

    def test_loop_until(self):
        d = {"op": "LOOP", "loop_until": True, "condition": "MANUAL"}
        inst = instruction_from_dict(d)
        assert inst.loop_until is True
        assert inst.condition == "MANUAL"
        assert instruction_to_dict(inst) == d

    def test_jump(self):
        d = {"op": "JUMP", "target": "sec-chorus"}
        inst = instruction_from_dict(d)
        assert inst.target == "sec-chorus"
        assert instruction_to_dict(inst) == d

    def test_jump_conditional(self):
        d = {"op": "JUMP", "target": "sec-chorus", "condition": "1:2"}
        inst = instruction_from_dict(d)
        assert inst.condition == "1:2"
        rt = instruction_to_dict(inst)
        assert rt == d

    def test_cross_lane_jump(self):
        d = {"op": "JUMP", "target": "sec-chorus", "jump_lane": "lane-bass"}
        inst = instruction_from_dict(d)
        assert inst.jump_lane == "lane-bass"
        assert instruction_to_dict(inst) == d

    def test_gosub(self):
        d = {"op": "GOSUB", "target": "sec-fill", "condition": "1:2"}
        inst = instruction_from_dict(d)
        assert inst.op == InstructionOp.GOSUB
        assert instruction_to_dict(inst) == d

    def test_if_branch(self):
        d = {
            "op": "IF",
            "condition": "50%",
            "then_inst": {"op": "PLAY"},
            "else_inst": {"op": "MUTE"},
        }
        inst = instruction_from_dict(d)
        assert inst.op == InstructionOp.IF
        assert inst.then_inst is not None
        assert inst.then_inst.op == InstructionOp.PLAY
        assert inst.else_inst is not None
        assert inst.else_inst.op == InstructionOp.MUTE
        rt = instruction_to_dict(inst)
        assert rt == d

    def test_skip_with_condition(self):
        d = {"op": "SKIP", "condition": "2:4"}
        inst = instruction_from_dict(d)
        assert inst.condition == "2:4"
        assert instruction_to_dict(inst) == d


class TestProjectRoundtrip:
    def test_minimal_project(self):
        d = {
            "dim_version": "1.0",
            "project": {
                "id": "p1",
                "name": "Test",
                "tempo_bpm": 120.0,
                "time_signature": "4/4",
                "gosub_stack_limit": 4,
                "lanes": [],
                "arrangement": [],
            }
        }
        proj = project_from_dict(d)
        assert proj.id == "p1"
        assert proj.tempo_bpm == 120.0
        rt = project_to_dict(proj)
        assert rt["project"]["id"] == "p1"
        assert rt["dim_version"] == "1.0"

    def test_project_without_wrapper(self):
        d = {"id": "bare", "name": "Bare", "tempo_bpm": 90.0, "lanes": []}
        proj = project_from_dict(d)
        assert proj.id == "bare"


class TestStripComments:
    def test_strips_underscore_keys(self):
        d = {"id": "x", "_comment": "ignore me", "name": "real"}
        result = _strip_comments(d)
        assert "_comment" not in result
        assert result["name"] == "real"

    def test_nested(self):
        d = {"sections": [{"id": "s1", "_note": "drop this"}]}
        result = _strip_comments(d)
        assert "_note" not in result["sections"][0]


class TestLoadExampleProject:
    def test_example_project_parses(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "formats", "example_project.json"
        )
        proj = load_project(path)
        assert proj.id == "proj-example-001"
        assert proj.tempo_bpm == pytest.approx(118.0)
        assert proj.time_signature == "4/4"
        assert len(proj.lanes) == 3

    def test_example_project_has_conductor_lane(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "formats", "example_project.json"
        )
        proj = load_project(path)
        conductor = next((ln for ln in proj.lanes if ln.is_conductor), None)
        assert conductor is not None
        assert conductor.id == "lane-conductor"
