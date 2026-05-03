"""
D.I.M — core/sequencer.py
Pure tick() function + cursor types. Zero side effects.

Architecture:
    tick(cursor, delta_beats, project) → (new_cursor, list[Event])

The cursor carries all state. delta_beats is in master beats.
Events are consumed by adapters (display, OSC, alerts).

Overshoot handling: if delta_beats spans multiple cue boundaries,
tick() advances through all of them in one call.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Optional, Union

from core.condition import ConditionState, evaluate, next_state, trigger_manual
from core.models import (
    Cue, InstructionOp, Instruction, Lane, Project, Section,
)
from core.playlist import build_cue_queue
from core.timing import cue_duration_master_beats


# ── Events ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EvCueStarted:
    lane_id: str
    section_id: str
    cue_id: str

@dataclass(frozen=True)
class EvCueEnded:
    lane_id: str
    section_id: str
    cue_id: str

@dataclass(frozen=True)
class EvSectionStarted:
    lane_id: str
    section_id: str
    pass_index: int

@dataclass(frozen=True)
class EvSectionEnded:
    lane_id: str
    section_id: str

@dataclass(frozen=True)
class EvSequenceEnded:
    """A lane has run out of sections."""
    lane_id: str

@dataclass(frozen=True)
class EvCrossLaneJump:
    """A cue requested a jump in another lane."""
    source_lane_id: str
    target_lane_id: str
    target_section_id: str

@dataclass(frozen=True)
class EvGosubStackOverflow:
    """GOSUB stack depth exceeded — forced PLAY, no interrupt."""
    lane_id: str
    section_id: str

@dataclass(frozen=True)
class EvManualWaiting:
    """Playback paused, waiting for a manual trigger."""
    lane_id: str
    section_id: str
    cue_id: str

Event = Union[
    EvCueStarted, EvCueEnded, EvSectionStarted, EvSectionEnded,
    EvSequenceEnded, EvCrossLaneJump, EvGosubStackOverflow, EvManualWaiting,
]


# ── Cursor ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GosubFrame:
    """Return address pushed onto the GOSUB stack."""
    lane_id: str
    section_id: Optional[str]   # section to return to (None = advance to next section)
    section_index: int           # index of return section in lane.sections
    cue_index: int               # cue index to resume at on return (0 for section-level)


@dataclass(frozen=True)
class LaneCursor:
    """Complete playback state for one lane. Immutable."""
    lane_id: str
    section_id: Optional[str]       # None when sequence has ended
    section_index: int               # index in lane.sections
    cue_queue: tuple[str, ...]       # cue IDs for the current section pass
    cue_index: int                   # position in cue_queue
    beats_remaining: float           # master beats until the current cue ends
    section_pass: int                # how many times we have started this section
    cue_loop_remaining: int          # LOOP n: iterations still to run after this one
    gosub_stack: tuple[GosubFrame, ...]
    cond_states: dict[str, ConditionState]  # keyed by cue_id or section_id+"_loop"/"_rev"
    waiting_for_manual: bool
    veto_jump: bool = False              # operator flagged: skip next JUMP (consumed on use)


@dataclass(frozen=True)
class PlaybackCursor:
    """Global playback state. Immutable. Passed to and returned from tick()."""
    is_playing: bool
    beat_position: float        # absolute master beat count from the beginning
    tempo_bpm: float
    time_signature: str
    gosub_stack_limit: int
    lane_cursors: dict[str, LaneCursor]   # keyed by lane_id


# ── Lookup helpers ────────────────────────────────────────────────────────────

def _lane(project: Project, lane_id: str) -> Optional[Lane]:
    for ln in project.lanes:
        if ln.id == lane_id:
            return ln
    return None


def _section(lane: Lane, section_id: str) -> Optional[Section]:
    for s in lane.sections:
        if s.id == section_id:
            return s
    return None


def _section_at(lane: Lane, index: int) -> Optional[Section]:
    return lane.sections[index] if 0 <= index < len(lane.sections) else None


def _section_index_of(lane: Lane, section_id: str) -> int:
    for i, s in enumerate(lane.sections):
        if s.id == section_id:
            return i
    return -1


def _cue(section: Section, cue_id: str) -> Optional[Cue]:
    for c in section.cues:
        if c.id == cue_id:
            return c
    return None


# ── Instruction resolution ────────────────────────────────────────────────────

def _resolve_if(
    inst: Instruction,
    cond_states: dict[str, ConditionState],
    key: str,
) -> tuple[Instruction, dict[str, ConditionState]]:
    """
    Resolve an IF instruction to then_inst or else_inst.
    Returns the resolved instruction and updated cond_states.
    Non-IF instructions pass through unchanged.
    """
    if inst.op != InstructionOp.IF:
        return inst, cond_states

    state = cond_states.get(key, ConditionState())
    met = evaluate(inst.condition, state)
    new_states = {**cond_states, key: next_state(state)}

    resolved = inst.then_inst if met else inst.else_inst
    if resolved is None:
        resolved = Instruction(op=InstructionOp.PLAY)

    # Recursively resolve nested IF
    return _resolve_if(resolved, new_states, key)


# ── Section / cue start ───────────────────────────────────────────────────────

def _start_section(
    lc: LaneCursor,
    section: Section,
    lane: Lane,
    time_sig: str,
    events: list[Event],
) -> tuple[LaneCursor, list[Event]]:
    """
    Initialize the cursor at the start of a section pass.
    Builds the cue queue, applies REVERSE if needed, emits EvSectionStarted.
    """
    queue = build_cue_queue(section, lc.section_pass)

    # REVERSE: evaluate at section start
    inst = section.instruction
    if inst.op == InstructionOp.REVERSE:
        rev_key = section.id + "_rev"
        if inst.condition:
            state = lc.cond_states.get(rev_key, ConditionState())
            should_reverse = evaluate(inst.condition, state)
            new_cond = {**lc.cond_states, rev_key: next_state(state)}
            lc = dataclasses.replace(lc, cond_states=new_cond)
        else:
            should_reverse = True
        if should_reverse:
            queue = list(reversed(queue))

    cue_ids = tuple(c.id for c in queue)
    lc = dataclasses.replace(
        lc,
        section_id=section.id,
        section_index=_section_index_of(lane, section.id),
        cue_queue=cue_ids,
        cue_index=0,
        beats_remaining=0.0,
        cue_loop_remaining=0,
        waiting_for_manual=False,
    )

    events.append(EvSectionStarted(lane.id, section.id, lc.section_pass))

    if not cue_ids:
        # Empty section: will be handled as immediate section end in tick loop
        return lc, events

    lc, cue_ev = _start_cue_at_index(lc, section, lane, time_sig)
    events.extend(cue_ev)
    return lc, events


def _start_cue_at_index(
    lc: LaneCursor,
    section: Section,
    lane: Lane,
    time_sig: str,
) -> tuple[LaneCursor, list[Event]]:
    """
    Start the cue at lc.cue_index.
    Handles SKIP condition at start time (SKIP UNTIL semantics).
    Initializes beats_remaining and cue_loop_remaining.
    Emits EvCueStarted.
    """
    events: list[Event] = []

    if lc.cue_index >= len(lc.cue_queue):
        return lc, events

    cue_id = lc.cue_queue[lc.cue_index]
    c = _cue(section, cue_id)
    if c is None:
        return lc, events

    inst = c.instruction
    beats = cue_duration_master_beats(c.duration_bars, lane.speed_ratio, time_sig)

    # SKIP / SKIP UNTIL: evaluated at cue start
    if inst.op == InstructionOp.SKIP:
        if inst.condition:
            # SKIP UNTIL cond: skip while condition is False; play when True
            state = lc.cond_states.get(cue_id, ConditionState())
            should_play = evaluate(inst.condition, state)
            new_cond = {**lc.cond_states, cue_id: next_state(state)}
            lc = dataclasses.replace(lc, cond_states=new_cond)
            if should_play:
                # Condition met → play normally this pass
                lc = dataclasses.replace(lc, beats_remaining=beats, cue_loop_remaining=0)
            else:
                # Still skipping → 0 duration
                lc = dataclasses.replace(lc, beats_remaining=0.0, cue_loop_remaining=0)
        else:
            # Pure SKIP: always 0 duration
            lc = dataclasses.replace(lc, beats_remaining=0.0, cue_loop_remaining=0)

        events.append(EvCueStarted(lane.id, section.id, cue_id))
        return lc, events

    # LOOP n: initialize loop counter
    loop_remaining = 0
    if inst.op == InstructionOp.LOOP and not inst.loop_until:
        loop_remaining = max(0, (inst.loop_count or 1) - 1)

    lc = dataclasses.replace(lc, beats_remaining=beats, cue_loop_remaining=loop_remaining)
    events.append(EvCueStarted(lane.id, section.id, cue_id))
    return lc, events


# ── Advance: cue end logic ────────────────────────────────────────────────────

def _advance_cue(
    lc: LaneCursor,
    lane: Lane,
    project: Project,
    time_sig: str,
    gosub_limit: int,
    events: list[Event],
) -> tuple[LaneCursor, list[Event]]:
    """
    Called when the current cue's duration has expired.
    Evaluates the cue's instruction and advances the cursor accordingly.
    """
    sec = _section(lane, lc.section_id) if lc.section_id else None
    if sec is None:
        return lc, events

    current_cue_id = (
        lc.cue_queue[lc.cue_index]
        if lc.cue_index < len(lc.cue_queue)
        else None
    )
    c = _cue(sec, current_cue_id) if current_cue_id else None

    if c is None:
        # No current cue → advance section
        return _advance_section(lc, lane, project, time_sig, gosub_limit, events)

    events.append(EvCueEnded(lane.id, sec.id, c.id))

    inst = c.instruction

    # Resolve IF first
    if inst.op == InstructionOp.IF:
        inst, new_cond = _resolve_if(inst, lc.cond_states, c.id)
        lc = dataclasses.replace(lc, cond_states=new_cond)

    op = inst.op

    # ── SKIP: always advance (decision was made at start) ──
    if op == InstructionOp.SKIP:
        return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)

    # ── MUTE: consume time, advance like PLAY ──
    if op == InstructionOp.MUTE:
        return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)

    # ── LOOP ──
    if op == InstructionOp.LOOP:
        if inst.loop_until:
            # LOOP UNTIL cond: loop while condition is False, advance when True
            state = lc.cond_states.get(c.id, ConditionState())
            done = evaluate(inst.condition, state)
            new_cond = {**lc.cond_states, c.id: next_state(state)}
            lc = dataclasses.replace(lc, cond_states=new_cond)

            if inst.condition == "MANUAL" and not done:
                events.append(EvManualWaiting(lane.id, sec.id, c.id))
                return dataclasses.replace(lc, waiting_for_manual=True, beats_remaining=0.0), events

            if done:
                return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)
            else:
                return _restart_current_cue(lc, c, lane, time_sig, events)
        else:
            # LOOP n: check remaining iterations
            if lc.cue_loop_remaining > 0:
                lc = dataclasses.replace(lc, cue_loop_remaining=lc.cue_loop_remaining - 1)
                return _restart_current_cue(lc, c, lane, time_sig, events)
            else:
                return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)

    # ── JUMP ──
    if op == InstructionOp.JUMP:
        # Evaluate condition if any
        if inst.condition:
            state = lc.cond_states.get(c.id, ConditionState())
            do_jump = evaluate(inst.condition, state)
            new_cond = {**lc.cond_states, c.id: next_state(state)}
            lc = dataclasses.replace(lc, cond_states=new_cond)
            if not do_jump:
                return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)

        target = inst.target or ""
        jump_lane = inst.jump_lane

        if jump_lane and jump_lane != lane.id:
            # Cross-lane JUMP: emit event, continue this lane normally
            events.append(EvCrossLaneJump(lane.id, jump_lane, target))
            return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)

        # Same-lane JUMP to a section
        target_sec = _section(lane, target)
        if target_sec is None:
            # Unknown target → treat as PLAY
            return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)

        lc = dataclasses.replace(
            lc,
            section_id=target_sec.id,
            section_index=_section_index_of(lane, target_sec.id),
            section_pass=0,
            cue_loop_remaining=0,
        )
        return _start_section(lc, target_sec, lane, time_sig, events)

    # ── GOSUB ──
    if op == InstructionOp.GOSUB:
        if inst.condition:
            state = lc.cond_states.get(c.id, ConditionState())
            do_gosub = evaluate(inst.condition, state)
            new_cond = {**lc.cond_states, c.id: next_state(state)}
            lc = dataclasses.replace(lc, cond_states=new_cond)
            if not do_gosub:
                return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)

        if len(lc.gosub_stack) >= gosub_limit:
            events.append(EvGosubStackOverflow(lane.id, sec.id))
            return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)

        target = inst.target or ""
        target_sec = _section(lane, target)
        if target_sec is None:
            return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)

        # Push return address: return to next cue in the current section
        frame = GosubFrame(
            lane_id=lane.id,
            section_id=sec.id,
            section_index=lc.section_index,
            cue_index=lc.cue_index + 1,
        )
        lc = dataclasses.replace(
            lc,
            gosub_stack=lc.gosub_stack + (frame,),
            section_id=target_sec.id,
            section_index=_section_index_of(lane, target_sec.id),
            section_pass=0,
        )
        return _start_section(lc, target_sec, lane, time_sig, events)

    # ── PLAY (default) ──
    return _next_cue(lc, sec, lane, project, time_sig, gosub_limit, events)


def _restart_current_cue(
    lc: LaneCursor,
    c: Cue,
    lane: Lane,
    time_sig: str,
    events: list[Event],
) -> tuple[LaneCursor, list[Event]]:
    """Restart the current cue (for LOOP)."""
    beats = cue_duration_master_beats(c.duration_bars, lane.speed_ratio, time_sig)
    lc = dataclasses.replace(lc, beats_remaining=beats)
    events.append(EvCueStarted(lane.id, lc.section_id or "", c.id))
    return lc, events


def _next_cue(
    lc: LaneCursor,
    sec: Section,
    lane: Lane,
    project: Project,
    time_sig: str,
    gosub_limit: int,
    events: list[Event],
) -> tuple[LaneCursor, list[Event]]:
    """Advance to the next cue in the queue, or to section end if done."""
    next_index = lc.cue_index + 1
    if next_index < len(lc.cue_queue):
        lc = dataclasses.replace(lc, cue_index=next_index, cue_loop_remaining=0)
        lc, ev = _start_cue_at_index(lc, sec, lane, time_sig)
        events.extend(ev)
        return lc, events
    else:
        # All cues done → evaluate section instruction
        return _advance_section(lc, lane, project, time_sig, gosub_limit, events)


def _advance_section(
    lc: LaneCursor,
    lane: Lane,
    project: Project,
    time_sig: str,
    gosub_limit: int,
    events: list[Event],
) -> tuple[LaneCursor, list[Event]]:
    """
    Called when all cues in the current section pass are done.
    Evaluates the section's instruction: LOOP, JUMP, GOSUB, or advance to next section.
    """
    sec_id = lc.section_id
    if sec_id is None:
        return lc, events

    sec = _section(lane, sec_id)
    if sec is None:
        return _end_lane(lc, lane, events)

    events.append(EvSectionEnded(lane.id, sec_id))

    # Check GOSUB return first (GOSUB target section just ended)
    if lc.gosub_stack:
        return _gosub_return(lc, lane, project, time_sig, gosub_limit, events)

    # Evaluate section instruction (resolve IF)
    inst = sec.instruction
    if inst.op == InstructionOp.IF:
        inst, new_cond = _resolve_if(inst, lc.cond_states, sec.id)
        lc = dataclasses.replace(lc, cond_states=new_cond)

    op = inst.op

    # REVERSE is handled at section start, not here — treat as PLAY
    if op == InstructionOp.REVERSE:
        return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)

    # LOOP section
    if op == InstructionOp.LOOP:
        if inst.loop_until:
            loop_key = sec.id + "_loop"
            state = lc.cond_states.get(loop_key, ConditionState())
            done = evaluate(inst.condition, state)
            new_cond = {**lc.cond_states, loop_key: next_state(state)}
            lc = dataclasses.replace(lc, cond_states=new_cond)

            if inst.condition == "MANUAL" and not done:
                events.append(EvManualWaiting(lane.id, sec.id, ""))
                return dataclasses.replace(lc, waiting_for_manual=True), events

            if done:
                return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)
            else:
                lc = dataclasses.replace(lc, section_pass=lc.section_pass + 1)
                return _start_section(lc, sec, lane, time_sig, events)
        else:
            loop_count = inst.loop_count or 1
            if lc.section_pass < loop_count - 1:
                lc = dataclasses.replace(lc, section_pass=lc.section_pass + 1)
                return _start_section(lc, sec, lane, time_sig, events)
            else:
                return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)

    # JUMP section
    if op == InstructionOp.JUMP:
        # Operator veto: skip this jump once, consume the flag
        if lc.veto_jump:
            lc = dataclasses.replace(lc, veto_jump=False)
            return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)

        if inst.condition:
            state = lc.cond_states.get(sec.id + "_jump", ConditionState())
            do_jump = evaluate(inst.condition, state)
            new_cond = {**lc.cond_states, sec.id + "_jump": next_state(state)}
            lc = dataclasses.replace(lc, cond_states=new_cond)
            if not do_jump:
                return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)

        target = inst.target or ""
        jump_lane = inst.jump_lane
        if jump_lane and jump_lane != lane.id:
            events.append(EvCrossLaneJump(lane.id, jump_lane, target))
            return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)

        target_sec = _section(lane, target)
        if target_sec is None:
            return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)

        lc = dataclasses.replace(
            lc,
            section_id=target_sec.id,
            section_index=_section_index_of(lane, target_sec.id),
            section_pass=0,
        )
        return _start_section(lc, target_sec, lane, time_sig, events)

    # GOSUB section
    if op == InstructionOp.GOSUB:
        if inst.condition:
            state = lc.cond_states.get(sec.id + "_gosub", ConditionState())
            do_gosub = evaluate(inst.condition, state)
            new_cond = {**lc.cond_states, sec.id + "_gosub": next_state(state)}
            lc = dataclasses.replace(lc, cond_states=new_cond)
            if not do_gosub:
                return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)

        if len(lc.gosub_stack) >= gosub_limit:
            events.append(EvGosubStackOverflow(lane.id, sec.id))
            return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)

        target = inst.target or ""
        target_sec = _section(lane, target)
        if target_sec is None:
            return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)

        # Return address: next section after current
        next_idx = lc.section_index + 1
        frame = GosubFrame(
            lane_id=lane.id,
            section_id=None,        # "advance from section_index"
            section_index=next_idx,
            cue_index=0,
        )
        lc = dataclasses.replace(
            lc,
            gosub_stack=lc.gosub_stack + (frame,),
            section_id=target_sec.id,
            section_index=_section_index_of(lane, target_sec.id),
            section_pass=0,
        )
        return _start_section(lc, target_sec, lane, time_sig, events)

    # PLAY / MUTE / default → advance to next section
    return _next_section_in_lane(lc, lane, project, time_sig, gosub_limit, events)


def _gosub_return(
    lc: LaneCursor,
    lane: Lane,
    project: Project,
    time_sig: str,
    gosub_limit: int,
    events: list[Event],
) -> tuple[LaneCursor, list[Event]]:
    """Pop the GOSUB stack and return to the saved position."""
    frame = lc.gosub_stack[-1]
    new_stack = lc.gosub_stack[:-1]
    lc = dataclasses.replace(lc, gosub_stack=new_stack)

    if frame.section_id is not None:
        # Return to a specific section + cue_index
        ret_sec = _section(lane, frame.section_id)
        if ret_sec is None:
            return _end_lane(lc, lane, events)

        # Rebuild the cue queue for that section at the current pass
        from core.playlist import build_cue_queue as _bcq
        queue = _bcq(ret_sec, lc.section_pass)
        cue_ids = tuple(c.id for c in queue)

        lc = dataclasses.replace(
            lc,
            section_id=frame.section_id,
            section_index=frame.section_index,
            cue_queue=cue_ids,
            cue_index=frame.cue_index,
            beats_remaining=0.0,
            cue_loop_remaining=0,
            waiting_for_manual=False,
        )

        if frame.cue_index < len(cue_ids):
            lc, ev = _start_cue_at_index(lc, ret_sec, lane, time_sig)
            events.extend(ev)
            return lc, events
        else:
            # Returned past last cue → advance that section
            return _advance_section(lc, lane, project, time_sig, gosub_limit, events)
    else:
        # Section-level GOSUB return: advance to frame.section_index
        next_sec = _section_at(lane, frame.section_index)
        if next_sec is None:
            return _end_lane(lc, lane, events)

        lc = dataclasses.replace(
            lc,
            section_id=next_sec.id,
            section_index=frame.section_index,
            section_pass=0,
        )
        return _start_section(lc, next_sec, lane, time_sig, events)


def _next_section_in_lane(
    lc: LaneCursor,
    lane: Lane,
    project: Project,
    time_sig: str,
    gosub_limit: int,
    events: list[Event],
) -> tuple[LaneCursor, list[Event]]:
    """Advance to the next section in lane.sections."""
    next_idx = lc.section_index + 1
    next_sec = _section_at(lane, next_idx)
    if next_sec is None:
        return _end_lane(lc, lane, events)

    lc = dataclasses.replace(lc, section_pass=0)
    lc = dataclasses.replace(
        lc,
        section_id=next_sec.id,
        section_index=next_idx,
        section_pass=0,
    )
    return _start_section(lc, next_sec, lane, time_sig, events)


def _end_lane(
    lc: LaneCursor,
    lane: Lane,
    events: list[Event],
) -> tuple[LaneCursor, list[Event]]:
    """Mark the lane as finished."""
    events.append(EvSequenceEnded(lane.id))
    return dataclasses.replace(lc, section_id=None, beats_remaining=0.0), events


# ── Lane tick ─────────────────────────────────────────────────────────────────

_MAX_ITER = 2048  # safety guard against infinite loops


def _tick_lane(
    lc: LaneCursor,
    delta_beats: float,
    lane: Lane,
    project: Project,
    time_sig: str,
    gosub_limit: int,
) -> tuple[LaneCursor, list[Event]]:
    """
    Advance one lane cursor by delta_beats master beats.
    Handles overshoot: may process multiple cue transitions in one call.
    """
    events: list[Event] = []
    remaining = delta_beats
    iterations = 0

    while remaining > 0 and lc.section_id is not None and not lc.waiting_for_manual:
        iterations += 1
        if iterations > _MAX_ITER:
            break  # safety

        if lc.beats_remaining > remaining:
            lc = dataclasses.replace(lc, beats_remaining=lc.beats_remaining - remaining)
            remaining = 0
        else:
            remaining -= lc.beats_remaining
            lc = dataclasses.replace(lc, beats_remaining=0.0)
            lc, ev = _advance_cue(lc, lane, project, time_sig, gosub_limit, events)
            events.extend([e for e in ev if e not in events])

    return lc, events


# ── Public API ────────────────────────────────────────────────────────────────

def init_cursor(project: Project) -> PlaybackCursor:
    """Create the initial PlaybackCursor for a project (all lanes at section 0)."""
    lane_cursors: dict[str, LaneCursor] = {}
    for ln in project.lanes:
        lc = LaneCursor(
            lane_id=ln.id,
            section_id=None,
            section_index=0,
            cue_queue=(),
            cue_index=0,
            beats_remaining=0.0,
            section_pass=0,
            cue_loop_remaining=0,
            gosub_stack=(),
            cond_states={},
            waiting_for_manual=False,
        )
        if ln.sections:
            first_sec = ln.sections[0]
            lc = dataclasses.replace(lc, section_id=first_sec.id)
            events: list[Event] = []
            lc, _ = _start_section(lc, first_sec, ln, project.time_signature, events)
        lane_cursors[ln.id] = lc

    return PlaybackCursor(
        is_playing=True,
        beat_position=0.0,
        tempo_bpm=project.tempo_bpm,
        time_signature=project.time_signature,
        gosub_stack_limit=project.gosub_stack_limit,
        lane_cursors=lane_cursors,
    )


def tick(
    cursor: PlaybackCursor,
    delta_beats: float,
    project: Project,
) -> tuple[PlaybackCursor, list[Event]]:
    """
    Advance the playback cursor by delta_beats master beats.

    Pure function — no side effects. Fully deterministic.
    (Exception: probabilistic conditions use random.random().)

    Returns:
        (new_cursor, events)

    Events are processed by adapters (display update, OSC emit, alerts).
    Cross-lane jumps (EvCrossLaneJump) are applied after all lanes advance.
    """
    if not cursor.is_playing or delta_beats <= 0:
        return cursor, []

    all_events: list[Event] = []
    new_lane_cursors: dict[str, LaneCursor] = {}
    cross_lane_jumps: list[EvCrossLaneJump] = []

    # Pass 1: advance each lane independently
    for lane_id, lc in cursor.lane_cursors.items():
        ln = _lane(project, lane_id)
        if ln is None:
            new_lane_cursors[lane_id] = lc
            continue

        new_lc, ev = _tick_lane(
            lc, delta_beats, ln, project,
            cursor.time_signature, cursor.gosub_stack_limit,
        )
        new_lane_cursors[lane_id] = new_lc

        for e in ev:
            if isinstance(e, EvCrossLaneJump):
                cross_lane_jumps.append(e)
            else:
                all_events.append(e)

    # Pass 2: apply cross-lane jumps
    for jump in cross_lane_jumps:
        all_events.append(jump)
        target_ln = _lane(project, jump.target_lane_id)
        if target_ln is None:
            continue
        target_lc = new_lane_cursors.get(jump.target_lane_id)
        if target_lc is None:
            continue

        target_sec = _section(target_ln, jump.target_section_id)
        if target_sec is None:
            continue

        target_lc = dataclasses.replace(
            target_lc,
            section_id=target_sec.id,
            section_index=_section_index_of(target_ln, target_sec.id),
            section_pass=0,
            gosub_stack=(),
        )
        ev: list[Event] = []
        target_lc, ev = _start_section(
            target_lc, target_sec, target_ln, cursor.time_signature, ev
        )
        all_events.extend(ev)
        new_lane_cursors[jump.target_lane_id] = target_lc

    new_cursor = dataclasses.replace(
        cursor,
        beat_position=cursor.beat_position + delta_beats,
        lane_cursors=new_lane_cursors,
    )
    return new_cursor, all_events


def trigger_manual_for_lane(
    cursor: PlaybackCursor,
    lane_id: str,
    cue_id: str,
) -> PlaybackCursor:
    """
    Fire a manual trigger for a specific cue in a lane.
    Releases a LOOP UNTIL MANUAL or SKIP UNTIL MANUAL wait.
    """
    lc = cursor.lane_cursors.get(lane_id)
    if lc is None:
        return cursor

    new_cond = {
        **lc.cond_states,
        cue_id: trigger_manual(lc.cond_states.get(cue_id, ConditionState())),
    }
    new_lc = dataclasses.replace(lc, cond_states=new_cond, waiting_for_manual=False)
    return dataclasses.replace(cursor, lane_cursors={**cursor.lane_cursors, lane_id: new_lc})
