"""
D.I.M — core/serializer.py
JSON ↔ models (versioned canonical format).
Pure functions: from_dict() and to_dict(). No I/O here.
"""
from __future__ import annotations

import json
from typing import Any

from core.models import (
    Cue, Instruction, InstructionOp, Lane, PlaylistConfig,
    Project, Section,
)

DIM_VERSION = "1.0"


# ── Instruction ───────────────────────────────────────────────────────────────

def instruction_from_dict(d: dict[str, Any]) -> Instruction:
    op = InstructionOp(d["op"])
    return Instruction(
        op=op,
        loop_count=d.get("loop_count"),
        loop_until=bool(d.get("loop_until", False)),
        target=d.get("target"),
        jump_lane=d.get("jump_lane"),
        condition=d.get("condition"),
        then_inst=instruction_from_dict(d["then_inst"]) if "then_inst" in d else None,
        else_inst=instruction_from_dict(d["else_inst"]) if "else_inst" in d else None,
    )


def instruction_to_dict(inst: Instruction) -> dict[str, Any]:
    d: dict[str, Any] = {"op": inst.op.value}
    if inst.loop_count is not None:
        d["loop_count"] = inst.loop_count
    if inst.loop_until:
        d["loop_until"] = True
    if inst.target is not None:
        d["target"] = inst.target
    if inst.jump_lane is not None:
        d["jump_lane"] = inst.jump_lane
    if inst.condition is not None:
        d["condition"] = inst.condition
    if inst.then_inst is not None:
        d["then_inst"] = instruction_to_dict(inst.then_inst)
    if inst.else_inst is not None:
        d["else_inst"] = instruction_to_dict(inst.else_inst)
    return d


# ── PlaylistConfig ────────────────────────────────────────────────────────────

def playlist_from_dict(d: dict[str, Any]) -> PlaylistConfig:
    return PlaylistConfig(
        mode=d.get("mode", "all"),
        nth=d.get("nth"),
        ratio=d.get("ratio"),
        custom_order=d.get("custom_order"),
    )


def playlist_to_dict(p: PlaylistConfig) -> dict[str, Any]:
    d: dict[str, Any] = {"mode": p.mode}
    if p.nth is not None:
        d["nth"] = p.nth
    if p.ratio is not None:
        d["ratio"] = p.ratio
    if p.custom_order is not None:
        d["custom_order"] = p.custom_order
    return d


# ── Cue ──────────────────────────────────────────────────────────────────────

def cue_from_dict(d: dict[str, Any]) -> Cue:
    return Cue(
        id=d["id"],
        label=d.get("label", ""),
        content=d.get("content", ""),
        duration_bars=float(d.get("duration_bars", 0.0)),
        repeat=int(d.get("repeat", 1)),
        instruction=instruction_from_dict(d.get("instruction", {"op": "PLAY"})),
        enabled=bool(d.get("enabled", True)),
        order_index=int(d.get("order_index", 0)),
    )


def cue_to_dict(c: Cue) -> dict[str, Any]:
    return {
        "id": c.id,
        "label": c.label,
        "content": c.content,
        "duration_bars": c.duration_bars,
        "repeat": c.repeat,
        "instruction": instruction_to_dict(c.instruction),
        "enabled": c.enabled,
        "order_index": c.order_index,
    }


# ── Section ───────────────────────────────────────────────────────────────────

def section_from_dict(d: dict[str, Any]) -> Section:
    return Section(
        id=d["id"],
        name=d.get("name", ""),
        type=d.get("type", "custom"),
        color=d.get("color", "#222222"),
        instruction=instruction_from_dict(d.get("instruction", {"op": "PLAY"})),
        playlist=playlist_from_dict(d.get("playlist", {"mode": "all"})),
        cues=[cue_from_dict(c) for c in d.get("cues", [])],
    )


def section_to_dict(s: Section) -> dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "type": s.type,
        "color": s.color,
        "instruction": instruction_to_dict(s.instruction),
        "playlist": playlist_to_dict(s.playlist),
        "cues": [cue_to_dict(c) for c in s.cues],
    }


# ── Lane ──────────────────────────────────────────────────────────────────────

def lane_from_dict(d: dict[str, Any]) -> Lane:
    return Lane(
        id=d["id"],
        name=d.get("name", ""),
        color=d.get("color", "#888888"),
        speed_ratio=d.get("speed_ratio", "1:1"),
        is_conductor=bool(d.get("is_conductor", False)),
        sections=[section_from_dict(s) for s in d.get("sections", [])],
    )


def lane_to_dict(ln: Lane) -> dict[str, Any]:
    return {
        "id": ln.id,
        "name": ln.name,
        "color": ln.color,
        "speed_ratio": ln.speed_ratio,
        "is_conductor": ln.is_conductor,
        "sections": [section_to_dict(s) for s in ln.sections],
    }


# ── Project ───────────────────────────────────────────────────────────────────

def project_from_dict(d: dict[str, Any]) -> Project:
    """
    Deserialize a project from a dict (canonical JSON format).
    Accepts both the full wrapper {"dim_version": ..., "project": {...}}
    and a bare project dict.
    """
    if "project" in d:
        _version = d.get("dim_version", DIM_VERSION)
        d = d["project"]

    return Project(
        id=d.get("id", ""),
        name=d.get("name", ""),
        tempo_bpm=float(d.get("tempo_bpm", 120.0)),
        time_signature=d.get("time_signature", "4/4"),
        gosub_stack_limit=int(d.get("gosub_stack_limit", 4)),
        lanes=[lane_from_dict(ln) for ln in d.get("lanes", [])],
        arrangement=list(d.get("arrangement", [])),
    )


def project_to_dict(project: Project, include_wrapper: bool = True) -> dict[str, Any]:
    """Serialize a project to a dict."""
    proj_dict: dict[str, Any] = {
        "id": project.id,
        "name": project.name,
        "tempo_bpm": project.tempo_bpm,
        "time_signature": project.time_signature,
        "gosub_stack_limit": project.gosub_stack_limit,
        "lanes": [lane_to_dict(ln) for ln in project.lanes],
        "arrangement": list(project.arrangement),
    }
    if include_wrapper:
        return {"dim_version": DIM_VERSION, "project": proj_dict}
    return proj_dict


# ── File I/O convenience ──────────────────────────────────────────────────────

def load_project(path: str) -> Project:
    """Load a project from a JSON file. Strips _comment / _note fields."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    raw = _strip_comments(raw)
    return project_from_dict(raw)


def save_project(project: Project, path: str) -> None:
    """Save a project to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project_to_dict(project), f, indent=2, ensure_ascii=False)


def _strip_comments(obj: Any) -> Any:
    """Recursively remove keys starting with '_' (used for JSON comments)."""
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_comments(i) for i in obj]
    return obj
