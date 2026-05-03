"""
D.I.M — cli.py
Command-line runner for testing the sequencer.

Usage:
    ./dim cli play formats/example_project.json           ← recommended
    ./dim cli play formats/example_project.json --beats 64 --step 4
    ./dim cli validate formats/example_project.json

    # or manually:
    PYTHONPATH=. .venv/bin/python cli.py play formats/example_project.json
"""
from __future__ import annotations

import argparse
import sys
import time

from core.serializer import load_project
from core.sequencer import (
    EvCrossLaneJump, EvCueEnded, EvCueStarted, EvGosubStackOverflow,
    EvManualWaiting, EvSectionEnded, EvSectionStarted, EvSequenceEnded,
    PlaybackCursor, init_cursor, tick,
)
from core.timing import format_duration_sec, format_position, sec_per_beat
from core.validator import validate


# ── ANSI colors ───────────────────────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    GRAY    = "\033[90m"


def _c(color: str, text: str) -> str:
    return f"{color}{text}{C.RESET}"


# ── Event display ─────────────────────────────────────────────────────────────

def _format_event(ev, time_sig: str) -> str | None:
    if isinstance(ev, EvSectionStarted):
        return _c(C.CYAN, f"  ▶ section  [{ev.lane_id}] {ev.section_id}  (pass {ev.pass_index})")
    if isinstance(ev, EvSectionEnded):
        return _c(C.GRAY, f"  ◼ /section [{ev.lane_id}] {ev.section_id}")
    if isinstance(ev, EvCueStarted):
        return _c(C.GREEN, f"    ▸ cue    [{ev.lane_id}] {ev.cue_id}")
    if isinstance(ev, EvCueEnded):
        return _c(C.GRAY, f"    ◂ /cue   [{ev.lane_id}] {ev.cue_id}")
    if isinstance(ev, EvSequenceEnded):
        return _c(C.YELLOW, f"  ■ END      [{ev.lane_id}]")
    if isinstance(ev, EvCrossLaneJump):
        return _c(C.YELLOW, f"  ⇢ jump    [{ev.source_lane_id}] → [{ev.target_lane_id}] {ev.target_section_id}")
    if isinstance(ev, EvGosubStackOverflow):
        return _c(C.RED, f"  ⚠ overflow [{ev.lane_id}] {ev.section_id}")
    if isinstance(ev, EvManualWaiting):
        return _c(C.YELLOW, f"  ⊙ MANUAL  [{ev.lane_id}] waiting…")
    return None


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_play(args: argparse.Namespace) -> int:
    try:
        project = load_project(args.file)
    except Exception as e:
        print(_c(C.RED, f"Error loading project: {e}"), file=sys.stderr)
        return 1

    print(_c(C.BOLD, f"\n  D.I.M — {project.name}"))
    print(_c(C.GRAY, f"  {project.tempo_bpm} BPM  {project.time_signature}  "
             f"| {len(project.lanes)} lane(s)"))
    print()

    cursor = init_cursor(project)
    max_beats: float = args.beats
    step: float = args.step
    beat = 0.0
    all_ended = False

    spb = sec_per_beat(project.tempo_bpm)

    while beat <= max_beats and not all_ended:
        cursor, events = tick(cursor, step, project)
        beat += step

        pos = format_position(beat, project.time_signature)
        sec = beat * spb
        ts = format_duration_sec(sec)

        if events:
            print(_c(C.DIM, f"  {ts}  {pos:>6}  beat={beat:.1f}"))
            for ev in events:
                line = _format_event(ev, project.time_signature)
                if line:
                    print(line)

        if args.realtime:
            time.sleep(step * spb)

        all_ended = all(
            cursor.lane_cursors[ln.id].section_id is None
            for ln in project.lanes
            if ln.id in cursor.lane_cursors
        )

    if all_ended:
        print(_c(C.GREEN, "\n  ✓ Sequence complete.\n"))
    else:
        print(_c(C.YELLOW, f"\n  (stopped at {max_beats} beats)\n"))

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        project = load_project(args.file)
    except Exception as e:
        print(_c(C.RED, f"Error loading project: {e}"), file=sys.stderr)
        return 1

    errors = validate(project)
    if not errors:
        print(_c(C.GREEN, f"✓ {args.file}: valid"))
        return 0

    for err in errors:
        color = C.RED if err.level == "error" else C.YELLOW
        print(_c(color, str(err)))

    errs = sum(1 for e in errors if e.level == "error")
    warns = sum(1 for e in errors if e.level == "warning")
    print(f"\n  {errs} error(s), {warns} warning(s)")
    return 1 if errs else 0


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="dim",
        description="D.I.M — Dawless Is More — CLI runner",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # play
    p_play = sub.add_parser("play", help="Run the sequencer on a project file")
    p_play.add_argument("file", help="Path to project JSON file")
    p_play.add_argument(
        "--beats", type=float, default=128.0,
        help="Maximum master beats to simulate (default: 128)",
    )
    p_play.add_argument(
        "--step", type=float, default=1.0,
        help="Tick step in master beats (default: 1.0)",
    )
    p_play.add_argument(
        "--realtime", action="store_true",
        help="Sleep between ticks to simulate real time",
    )

    # validate
    p_val = sub.add_parser("validate", help="Validate a project file")
    p_val.add_argument("file", help="Path to project JSON file")

    args = parser.parse_args()

    if args.command == "play":
        return cmd_play(args)
    if args.command == "validate":
        return cmd_validate(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
