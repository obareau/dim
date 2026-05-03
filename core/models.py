"""
D.I.M — core/models.py
Dataclasses: Project, Lane, Section, Cue, Instruction, PlaylistConfig.
Zero framework dependency. Python 3.11+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Instruction ──────────────────────────────────────────────────────────────

class InstructionOp(str, Enum):
    PLAY    = "PLAY"
    MUTE    = "MUTE"
    LOOP    = "LOOP"
    JUMP    = "JUMP"
    GOSUB   = "GOSUB"
    SKIP    = "SKIP"
    REVERSE = "REVERSE"
    IF      = "IF"


@dataclass
class Instruction:
    """
    One instruction carried by a Cue or Section.

    Examples:
        PLAY                    → Instruction(op=PLAY)
        LOOP 4                  → Instruction(op=LOOP, loop_count=4)
        LOOP UNTIL MANUAL       → Instruction(op=LOOP, loop_until=True, condition="MANUAL")
        JUMP sec-chorus         → Instruction(op=JUMP, target="sec-chorus")
        JUMP sec-chorus IF 1:2  → Instruction(op=JUMP, target="sec-chorus", condition="1:2")
        GOSUB sec-fill IF 1:2   → Instruction(op=GOSUB, target="sec-fill", condition="1:2")
        SKIP UNTIL 2:4          → Instruction(op=SKIP, condition="2:4")
        REVERSE                 → Instruction(op=REVERSE)
        REVERSE UNTIL 1:2       → Instruction(op=REVERSE, condition="1:2")
        IF 50% THEN PLAY ELSE MUTE → Instruction(op=IF, condition="50%",
                                        then_inst=Instruction(op=PLAY),
                                        else_inst=Instruction(op=MUTE))
        Cross-lane JUMP         → Instruction(op=JUMP, target="sec-id", jump_lane="lane-id")
    """
    op: InstructionOp

    # LOOP
    loop_count: Optional[int]           = None  # LOOP n: total plays
    loop_until: bool                    = False  # LOOP UNTIL <condition>

    # JUMP / GOSUB
    target: Optional[str]               = None  # section_id or cue_id
    jump_lane: Optional[str]            = None  # cross-lane target lane_id

    # Condition (LOOP UNTIL, JUMP IF, GOSUB IF, SKIP UNTIL, REVERSE UNTIL/IF)
    condition: Optional[str]            = None

    # IF branch
    then_inst: Optional[Instruction]    = None
    else_inst: Optional[Instruction]    = None


# ── Playlist ─────────────────────────────────────────────────────────────────

@dataclass
class PlaylistConfig:
    """
    Controls which cues are played and in what order within a section.

    mode:
        "all"    — all enabled cues in order (default)
        "nth"    — 1 out of nth cues per pass (nth=2 → every other cue)
        "ratio"  — M out of N cues  (ratio="3:4")
        "custom" — manual selection (custom_order = list of cue order_index values)
    """
    mode: str                               = "all"
    nth: Optional[int]                      = None
    ratio: Optional[str]                    = None  # "3:4"
    custom_order: Optional[list[int]]       = None


# ── Cue ──────────────────────────────────────────────────────────────────────

@dataclass
class Cue:
    """Atomic unit of performance. One action to perform."""
    id: str
    label: str
    content: str
    duration_bars: float
    repeat: int                 = 1
    instruction: Instruction    = field(
        default_factory=lambda: Instruction(op=InstructionOp.PLAY)
    )
    enabled: bool               = True
    order_index: int            = 0


# ── Section ───────────────────────────────────────────────────────────────────

SECTION_TYPES = {
    "intro", "verse", "chorus", "bridge", "alternative",
    "fill", "break", "outro", "end", "custom",
}


@dataclass
class Section:
    """Structural block: a named group of cues with its own instruction."""
    id: str
    name: str
    type: str                   = "custom"
    color: str                  = "#222222"
    instruction: Instruction    = field(
        default_factory=lambda: Instruction(op=InstructionOp.PLAY)
    )
    playlist: PlaylistConfig    = field(default_factory=PlaylistConfig)
    cues: list[Cue]             = field(default_factory=list)


# ── Lane ──────────────────────────────────────────────────────────────────────

@dataclass
class Lane:
    """
    One performer / one instrument. Horizontal row in the performance view.

    speed_ratio examples: "1:1" (master tempo), "2:1" (twice as fast), "1:2" (half speed).
    A Lane at 2:1 has bars half as long as master bars.
    """
    id: str
    name: str
    color: str                  = "#888888"
    speed_ratio: str            = "1:1"
    is_conductor: bool          = False
    sections: list[Section]     = field(default_factory=list)


# ── Project ───────────────────────────────────────────────────────────────────

@dataclass
class Project:
    """Root object. Contains all lanes and global settings."""
    id: str
    name: str
    tempo_bpm: float
    time_signature: str         = "4/4"
    gosub_stack_limit: int      = 4
    lanes: list[Lane]           = field(default_factory=list)
    arrangement: list[str]      = field(default_factory=list)  # section IDs (optional)
