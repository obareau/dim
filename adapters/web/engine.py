"""
D.I.M — adapters/web/engine.py
Sequencer engine: runs tick() in a background thread, broadcasts state via SocketIO.
Thread-safe access via a Lock. All public functions are safe to call from Flask routes.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from core.models import Project
from core.serializer import load_project as _load_project, project_to_dict
from core.sequencer import (
    PlaybackCursor, init_cursor, tick, trigger_manual_for_lane,
    EvCueStarted, EvCueEnded, EvSectionStarted, EvSectionEnded,
    EvSequenceEnded, EvCrossLaneJump, EvGosubStackOverflow, EvManualWaiting,
)
from core.timing import beats_per_bar, sec_per_beat, format_position, format_duration_sec

# ── Global state ──────────────────────────────────────────────────────────────

_lock = threading.Lock()
_project: Optional[Project] = None
_cursor: Optional[PlaybackCursor] = None
_elapsed_sec: float = 0.0
_running = False
_thread: Optional[threading.Thread] = None

# SocketIO instance — injected at startup
_socketio = None

TICK_INTERVAL = 0.05  # seconds (20 ticks/sec)


# ── Engine init ───────────────────────────────────────────────────────────────

def init(socketio_instance) -> None:
    """Call once at app startup with the SocketIO instance."""
    global _socketio
    _socketio = socketio_instance


def load(path: str) -> Project:
    """Load a project from a JSON file path. Resets playback."""
    global _project, _cursor, _elapsed_sec
    proj = _load_project(path)
    with _lock:
        _project = proj
        _cursor = init_cursor(proj)
        _elapsed_sec = 0.0
    return proj


def load_from_dict(data: dict) -> Project:
    """Load a project from a dict (parsed JSON). Resets playback."""
    global _project, _cursor, _elapsed_sec
    from core.serializer import project_from_dict
    from core.validator import validate
    proj = project_from_dict(data)
    errors = [e for e in validate(proj) if e.level == "error"]
    if errors:
        raise ValueError("; ".join(str(e) for e in errors))
    with _lock:
        _project = proj
        _cursor = init_cursor(proj)
        _elapsed_sec = 0.0
    return proj


# ── Transport ─────────────────────────────────────────────────────────────────

def play() -> None:
    global _cursor
    with _lock:
        if _cursor is not None:
            import dataclasses
            _cursor = dataclasses.replace(_cursor, is_playing=True)


def stop() -> None:
    global _cursor
    with _lock:
        if _cursor is not None:
            import dataclasses
            _cursor = dataclasses.replace(_cursor, is_playing=False)


def rewind() -> None:
    """Reset to start and stop. User must explicitly press play afterwards."""
    global _cursor, _elapsed_sec
    import dataclasses
    with _lock:
        if _project is not None:
            _cursor = init_cursor(_project)
            _cursor = dataclasses.replace(_cursor, is_playing=False)
            _elapsed_sec = 0.0


def set_tempo(bpm: float) -> None:
    global _cursor, _project
    if bpm <= 0:
        return
    import dataclasses
    with _lock:
        if _cursor is not None:
            _cursor = dataclasses.replace(_cursor, tempo_bpm=bpm)
        if _project is not None:
            _project = dataclasses.replace(_project, tempo_bpm=bpm)


def set_playing(state: bool) -> None:
    play() if state else stop()


def set_time_signature(ts: str) -> None:
    """Change the global time signature (e.g. '3/4', '6/8')."""
    global _cursor
    import dataclasses
    with _lock:
        if _cursor is not None:
            _cursor = dataclasses.replace(_cursor, time_signature=ts)


def trigger_manual(lane_id: str) -> bool:
    """Release a LOOP UNTIL MANUAL / SKIP UNTIL MANUAL wait on a lane.
    Returns True if the lane was indeed waiting, False otherwise."""
    global _cursor
    import dataclasses
    with _lock:
        if _cursor is None:
            return False
        lc = _cursor.lane_cursors.get(lane_id)
        if lc is None or not lc.waiting_for_manual:
            return False
        # Resolve current cue id from the queue
        cue_id = (lc.cue_queue[lc.cue_index]
                  if lc.cue_index < len(lc.cue_queue) else '')
        _cursor = trigger_manual_for_lane(_cursor, lane_id, cue_id)
        return True


def veto_jump(lane_id: str) -> bool:
    """Flag a lane to skip its next JUMP instruction (consumed on use).
    Returns True if the flag was set (lane exists), False otherwise."""
    global _cursor
    import dataclasses
    with _lock:
        if _cursor is None:
            return False
        lc = _cursor.lane_cursors.get(lane_id)
        if lc is None:
            return False
        new_lc = dataclasses.replace(lc, veto_jump=True)
        new_cursors = {**_cursor.lane_cursors, lane_id: new_lc}
        _cursor = dataclasses.replace(_cursor, lane_cursors=new_cursors)
        return True


# ── State snapshot ────────────────────────────────────────────────────────────

def get_project_dict() -> Optional[dict]:
    with _lock:
        return project_to_dict(_project) if _project else None


def get_state() -> dict:
    """Return a JSON-serializable snapshot of the current playback state."""
    with _lock:
        return _build_state(_cursor, _project, _elapsed_sec)


def _build_state(
    cursor: Optional[PlaybackCursor],
    project: Optional[Project],
    elapsed_sec: float,
) -> dict:
    if cursor is None or project is None:
        return {"loaded": False}

    bpb = beats_per_bar(cursor.time_signature)
    bar = int(cursor.beat_position // bpb) + 1
    beat_in_bar = int(cursor.beat_position % bpb) + 1
    beat_progress = (cursor.beat_position % bpb) / bpb if bpb else 0.0

    lanes_state = {}
    for lane in project.lanes:
        lc = cursor.lane_cursors.get(lane.id)
        if lc is None:
            continue

        # Current section/cue
        sec = _find_section(project, lane.id, lc.section_id)
        cue = None
        next_cue = None
        prev_cue = None

        if sec and lc.cue_index < len(lc.cue_queue):
            cue = _find_cue(sec, lc.cue_queue[lc.cue_index])
        if sec and lc.cue_index + 1 < len(lc.cue_queue):
            next_cue = _find_cue(sec, lc.cue_queue[lc.cue_index + 1])
        if sec and lc.cue_index > 0:
            prev_cue = _find_cue(sec, lc.cue_queue[lc.cue_index - 1])

        # beats_remaining as bars
        spb = sec_per_beat(cursor.tempo_bpm)
        from core.timing import parse_speed_ratio
        ratio = parse_speed_ratio(lane.speed_ratio)
        beats_rem = lc.beats_remaining
        bars_rem = beats_rem / (bpb / ratio) if bpb and ratio else 0.0

        # Section-level instruction badge (what fires when this section ends)
        sec_badge = instruction_badge(sec.instruction) if sec and sec.instruction else ""

        lanes_state[lane.id] = {
            "id": lane.id,
            "name": lane.name,
            "color": lane.color,
            "speed_ratio": lane.speed_ratio,
            "is_conductor": lane.is_conductor,
            "ended": lc.section_id is None,
            "waiting_manual": lc.waiting_for_manual,
            "veto_jump": lc.veto_jump,
            "section_id": lc.section_id,
            "section_name": sec.name if sec else None,
            "section_type": sec.type if sec else None,
            "section_pass": lc.section_pass,
            "section_next": sec_badge,        # badge for what happens at section end
            "cue": _cue_state(cue) if cue else None,
            "next_cue": _cue_state(next_cue) if next_cue else None,
            "prev_cue": _cue_state(prev_cue) if prev_cue else None,
            "beats_remaining": round(beats_rem, 3),
            "bars_remaining": round(bars_rem, 3),
            "cue_loop_remaining": lc.cue_loop_remaining,
        }

    return {
        "loaded": True,
        "playing": cursor.is_playing,
        "beat_position": round(cursor.beat_position, 3),
        "tempo_bpm": cursor.tempo_bpm,
        "time_signature": cursor.time_signature,
        "bar": bar,
        "beat_in_bar": beat_in_bar,
        "beat_progress": round(beat_progress, 4),
        "elapsed_sec": round(elapsed_sec, 2),
        "elapsed_fmt": format_duration_sec(elapsed_sec),
        "position_fmt": format_position(cursor.beat_position, cursor.time_signature),
        "lanes": lanes_state,
    }


def _cue_state(cue) -> dict:
    return {
        "id": cue.id,
        "label": cue.label,
        "content": cue.content,
        "duration_bars": cue.duration_bars,
        "badge": instruction_badge(cue.instruction),
    }


def instruction_badge(inst) -> str:
    """Return compact Elektron-style badge for an instruction."""
    from core.models import InstructionOp
    op = inst.op
    if op == InstructionOp.PLAY:
        return ""
    if op == InstructionOp.MUTE:
        return "░ MUTE"
    if op == InstructionOp.LOOP:
        if inst.loop_until:
            cond = inst.condition or ""
            return f"↺ {cond}" if cond != "MANUAL" else "↺ ⊙"
        return f"↺ {inst.loop_count or 1}"
    if op == InstructionOp.JUMP:
        target = (inst.target or "?").split("-")[-1]
        cond = f"  {inst.condition}" if inst.condition else ""
        return f"↗ {target}{cond}"
    if op == InstructionOp.GOSUB:
        target = (inst.target or "?").split("-")[-1]
        cond = f"  {inst.condition}" if inst.condition else ""
        return f"⤵ {target}{cond}"
    if op == InstructionOp.SKIP:
        return f"⇥ {inst.condition}" if inst.condition else "⇥"
    if op == InstructionOp.REVERSE:
        return f"⇐ REV  {inst.condition}" if inst.condition else "⇐ REV"
    if op == InstructionOp.IF:
        cond = inst.condition or "?"
        then_b = instruction_badge(inst.then_inst) if inst.then_inst else "▶"
        else_b = instruction_badge(inst.else_inst) if inst.else_inst else "░"
        return f"? {cond} {then_b}/{else_b}"
    return op.value


def _find_section(project: Project, lane_id: str, section_id: Optional[str]):
    if not section_id:
        return None
    for lane in project.lanes:
        if lane.id == lane_id:
            for sec in lane.sections:
                if sec.id == section_id:
                    return sec
    return None


def _find_cue(section, cue_id: str):
    if not section or not cue_id:
        return None
    for cue in section.cues:
        if cue.id == cue_id:
            return cue
    return None


# ── Background tick thread ────────────────────────────────────────────────────

def start_thread() -> None:
    global _running, _thread
    if _running:
        return
    _running = True
    _thread = threading.Thread(target=_tick_loop, daemon=True, name="dim-sequencer")
    _thread.start()


def stop_thread() -> None:
    global _running
    _running = False


def _tick_loop() -> None:
    global _cursor, _elapsed_sec
    while _running:
        time.sleep(TICK_INTERVAL)

        with _lock:
            if _cursor is None or _project is None or not _cursor.is_playing:
                # Still notify sync manager even when stopped (for MIDI stop msg)
                try:
                    from adapters.sync.manager import get_manager
                    get_manager().on_engine_tick(0.0, _cursor.tempo_bpm if _cursor else 120.0, False)
                except Exception:
                    pass
                continue
            delta_beats = TICK_INTERVAL * _cursor.tempo_bpm / 60.0
            _cursor, events = tick(_cursor, delta_beats, _project)
            _elapsed_sec += TICK_INTERVAL
            state = _build_state(_cursor, _project, _elapsed_sec)
            _snap_delta  = delta_beats
            _snap_tempo  = _cursor.tempo_bpm
            _snap_playing = _cursor.is_playing

        # Notify sync manager (MIDI clock out, OSC broadcast) — outside lock
        try:
            from adapters.sync.manager import get_manager
            get_manager().on_engine_tick(_snap_delta, _snap_tempo, _snap_playing)
        except Exception:
            pass

        if _socketio is not None:
            _socketio.emit("state_update", state)
