"""
D.I.M — core/validator.py
Project validation: detect invalid jumps, cycles, stack depth issues.
Returns a list of ValidationError. Empty list = project is valid.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.models import Cue, Instruction, InstructionOp, Lane, Project, Section


# ── Validation result ─────────────────────────────────────────────────────────

@dataclass
class ValidationError:
    level: str          # "error" | "warning"
    code: str           # short identifier
    message: str
    lane_id: Optional[str]      = None
    section_id: Optional[str]   = None
    cue_id: Optional[str]       = None

    def __str__(self) -> str:
        loc_parts = []
        if self.lane_id:
            loc_parts.append(f"lane={self.lane_id!r}")
        if self.section_id:
            loc_parts.append(f"section={self.section_id!r}")
        if self.cue_id:
            loc_parts.append(f"cue={self.cue_id!r}")
        loc = " | ".join(loc_parts)
        prefix = f"[{self.level.upper()}] [{self.code}]"
        return f"{prefix} {self.message}" + (f"  ({loc})" if loc else "")


# ── Validation rules ──────────────────────────────────────────────────────────

def validate(project: Project) -> list[ValidationError]:
    """
    Validate a project. Returns a list of ValidationError (may be empty).
    Does not raise. Callers decide how to handle errors vs warnings.
    """
    errors: list[ValidationError] = []

    _check_project_fields(project, errors)

    # Build lookup maps
    section_ids: set[str] = set()
    lane_ids: set[str] = set()
    for lane in project.lanes:
        lane_ids.add(lane.id)
        for sec in lane.sections:
            section_ids.add(sec.id)

    for lane in project.lanes:
        _check_lane(lane, section_ids, lane_ids, project, errors)

    _check_arrangement(project, section_ids, errors)

    return errors


def is_valid(project: Project) -> bool:
    """Return True if the project has no errors (warnings are ignored)."""
    return all(e.level != "error" for e in validate(project))


# ── Internal checks ───────────────────────────────────────────────────────────

def _check_project_fields(project: Project, errors: list[ValidationError]) -> None:
    if not project.id:
        errors.append(ValidationError("error", "MISSING_ID", "Project has no id"))
    if not project.name:
        errors.append(ValidationError("warning", "MISSING_NAME", "Project has no name"))
    if project.tempo_bpm <= 0:
        errors.append(ValidationError(
            "error", "INVALID_TEMPO",
            f"tempo_bpm must be > 0, got {project.tempo_bpm}",
        ))
    if "/" not in project.time_signature:
        errors.append(ValidationError(
            "error", "INVALID_TIME_SIG",
            f"Invalid time_signature: {project.time_signature!r}",
        ))
    if project.gosub_stack_limit < 1:
        errors.append(ValidationError(
            "warning", "LOW_GOSUB_LIMIT",
            f"gosub_stack_limit={project.gosub_stack_limit} is very low (min recommended: 2)",
        ))
    if not project.lanes:
        errors.append(ValidationError("warning", "NO_LANES", "Project has no lanes"))


def _check_lane(
    lane: Lane,
    all_section_ids: set[str],
    all_lane_ids: set[str],
    project: Project,
    errors: list[ValidationError],
) -> None:
    if not lane.id:
        errors.append(ValidationError("error", "MISSING_ID", "Lane has no id"))
        return

    # speed_ratio format
    try:
        parts = lane.speed_ratio.split(":")
        if len(parts) != 2 or int(parts[1]) == 0:
            raise ValueError
    except (ValueError, AttributeError):
        errors.append(ValidationError(
            "error", "INVALID_SPEED_RATIO",
            f"Invalid speed_ratio: {lane.speed_ratio!r}",
            lane_id=lane.id,
        ))

    # Section IDs unique within lane
    seen: set[str] = set()
    for sec in lane.sections:
        if sec.id in seen:
            errors.append(ValidationError(
                "error", "DUPLICATE_SECTION_ID",
                f"Duplicate section id {sec.id!r}",
                lane_id=lane.id, section_id=sec.id,
            ))
        seen.add(sec.id)
        _check_section(sec, lane, all_section_ids, all_lane_ids, project, errors)


def _check_section(
    sec: Section,
    lane: Lane,
    all_section_ids: set[str],
    all_lane_ids: set[str],
    project: Project,
    errors: list[ValidationError],
) -> None:
    if not sec.id:
        errors.append(ValidationError(
            "error", "MISSING_ID", "Section has no id", lane_id=lane.id,
        ))

    _check_instruction(
        sec.instruction, lane, sec, None,
        all_section_ids, all_lane_ids, project, errors,
    )

    seen_cue_ids: set[str] = set()
    for cue in sec.cues:
        if cue.id in seen_cue_ids:
            errors.append(ValidationError(
                "error", "DUPLICATE_CUE_ID",
                f"Duplicate cue id {cue.id!r}",
                lane_id=lane.id, section_id=sec.id, cue_id=cue.id,
            ))
        seen_cue_ids.add(cue.id)
        _check_cue(cue, lane, sec, all_section_ids, all_lane_ids, project, errors)


def _check_cue(
    cue: Cue,
    lane: Lane,
    sec: Section,
    all_section_ids: set[str],
    all_lane_ids: set[str],
    project: Project,
    errors: list[ValidationError],
) -> None:
    if cue.duration_bars < 0:
        errors.append(ValidationError(
            "error", "NEGATIVE_DURATION",
            f"Cue {cue.id!r} has negative duration_bars={cue.duration_bars}",
            lane_id=lane.id, section_id=sec.id, cue_id=cue.id,
        ))

    _check_instruction(
        cue.instruction, lane, sec, cue,
        all_section_ids, all_lane_ids, project, errors,
    )


def _check_instruction(
    inst: Instruction,
    lane: Lane,
    sec: Section,
    cue: Optional[Cue],
    all_section_ids: set[str],
    all_lane_ids: set[str],
    project: Project,
    errors: list[ValidationError],
) -> None:
    cue_id = cue.id if cue else None
    ctx = dict(lane_id=lane.id, section_id=sec.id, cue_id=cue_id)

    op = inst.op

    # LOOP: loop_count must be >= 1
    if op == InstructionOp.LOOP and not inst.loop_until:
        if inst.loop_count is not None and inst.loop_count < 1:
            errors.append(ValidationError(
                "error", "INVALID_LOOP_COUNT",
                f"loop_count must be >= 1, got {inst.loop_count}", **ctx,
            ))

    # JUMP / GOSUB: target required
    if op in (InstructionOp.JUMP, InstructionOp.GOSUB):
        if not inst.target:
            errors.append(ValidationError(
                "error", "MISSING_JUMP_TARGET",
                f"{op.value} instruction has no target", **ctx,
            ))
        elif inst.jump_lane:
            # Cross-lane: validate lane and section exist
            if inst.jump_lane not in all_lane_ids:
                errors.append(ValidationError(
                    "error", "UNKNOWN_LANE",
                    f"Cross-lane {op.value} references unknown lane {inst.jump_lane!r}", **ctx,
                ))
            elif inst.target not in all_section_ids:
                errors.append(ValidationError(
                    "warning", "UNKNOWN_SECTION",
                    f"Cross-lane {op.value} references unknown section {inst.target!r}", **ctx,
                ))
        else:
            # Same-lane: validate section exists in this lane
            lane_section_ids = {s.id for s in lane.sections}
            if inst.target not in lane_section_ids:
                errors.append(ValidationError(
                    "warning", "UNKNOWN_SECTION",
                    f"{op.value} references section {inst.target!r} not found in lane {lane.id!r}",
                    **ctx,
                ))

    # IF: both branches should be present
    if op == InstructionOp.IF:
        if inst.condition is None:
            errors.append(ValidationError(
                "error", "MISSING_IF_CONDITION",
                "IF instruction has no condition", **ctx,
            ))
        if inst.then_inst is None:
            errors.append(ValidationError(
                "error", "MISSING_IF_THEN",
                "IF instruction has no then_inst", **ctx,
            ))
        # Recursively check nested instructions
        if inst.then_inst:
            _check_instruction(
                inst.then_inst, lane, sec, cue,
                all_section_ids, all_lane_ids, project, errors,
            )
        if inst.else_inst:
            _check_instruction(
                inst.else_inst, lane, sec, cue,
                all_section_ids, all_lane_ids, project, errors,
            )


def _check_arrangement(
    project: Project,
    all_section_ids: set[str],
    errors: list[ValidationError],
) -> None:
    for sec_id in project.arrangement:
        if sec_id not in all_section_ids:
            errors.append(ValidationError(
                "warning", "UNKNOWN_ARRANGEMENT_SECTION",
                f"Arrangement references unknown section {sec_id!r}",
            ))
