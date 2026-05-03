"""
D.I.M — core/timing.py
Pure timing functions. All inputs/outputs are floats or ints.
Primary unit: master beats. Bars and seconds are derived.
"""
from __future__ import annotations


def parse_time_signature(ts: str) -> tuple[int, int]:
    """
    "4/4" → (4, 4)  |  "6/8" → (6, 8)  |  "7/8" → (7, 8)
    Supported: 4/4  3/4  6/8  7/8  5/4  12/8  and any valid "N/D" string.
    """
    parts = ts.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid time signature: {ts!r}")
    return int(parts[0]), int(parts[1])


def beats_per_bar(time_signature: str) -> int:
    """
    Number of beats per bar (using the numerator of the time signature).

    D.I.M uses the numerator directly as the beat count for all time signatures.
    This keeps the multi-lane beat grid consistent regardless of denominator.

    4/4 → 4  |  3/4 → 3  |  6/8 → 6  |  7/8 → 7  |  5/4 → 5
    """
    numerator, _ = parse_time_signature(time_signature)
    return numerator


def sec_per_beat(tempo_bpm: float) -> float:
    """Duration of one beat in seconds."""
    if tempo_bpm <= 0:
        raise ValueError(f"tempo_bpm must be > 0, got {tempo_bpm}")
    return 60.0 / tempo_bpm


def sec_per_bar(tempo_bpm: float, time_signature: str) -> float:
    """Duration of one master bar in seconds."""
    return sec_per_beat(tempo_bpm) * beats_per_bar(time_signature)


def bars_to_beats(bars: float, time_signature: str) -> float:
    """Convert bars to master beats."""
    return bars * beats_per_bar(time_signature)


def beats_to_bars(beats: float, time_signature: str) -> float:
    """Convert master beats to bars."""
    bpb = beats_per_bar(time_signature)
    return beats / bpb if bpb else 0.0


def bars_to_seconds(bars: float, tempo_bpm: float, time_signature: str) -> float:
    """Convert bars to seconds."""
    return bars * sec_per_bar(tempo_bpm, time_signature)


def seconds_to_bars(seconds: float, tempo_bpm: float, time_signature: str) -> float:
    """Convert seconds to bars."""
    spb = sec_per_bar(tempo_bpm, time_signature)
    return seconds / spb if spb else 0.0


def parse_speed_ratio(ratio: str) -> float:
    """
    "1:1" → 1.0  |  "2:1" → 2.0  |  "1:2" → 0.5  |  "4:1" → 4.0

    A lane at 2:1 plays twice as fast (its bars are half as long in real time).
    """
    parts = ratio.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid speed_ratio: {ratio!r}")
    num, denom = int(parts[0]), int(parts[1])
    if denom == 0:
        raise ValueError(f"speed_ratio denominator cannot be 0: {ratio!r}")
    return num / denom


def cue_duration_master_beats(
    duration_bars: float,
    speed_ratio: str,
    time_signature: str,
) -> float:
    """
    Convert a cue's duration (in lane bars) to master beats.

    A lane at 2:1 plays twice as fast, so its bars are half as long.
    4 lane bars at 2:1 = 2 master bars = 2 × beats_per_bar master beats.

    Formula:
        lane_beats     = duration_bars × beats_per_bar(time_signature)
        master_beats   = lane_beats / speed_ratio_factor
    """
    ratio = parse_speed_ratio(speed_ratio)
    lane_beats = bars_to_beats(duration_bars, time_signature)
    return lane_beats / ratio if ratio else 0.0


def format_position(beat_position: float, time_signature: str) -> str:
    """
    Format an absolute beat position as "bar:beat" string (1-indexed).
    Example: beat_position=6.0 with 4/4 → "2:3" (bar 2, beat 3)
    """
    bpb = beats_per_bar(time_signature)
    bar = int(beat_position // bpb) + 1
    beat = int(beat_position % bpb) + 1
    return f"{bar}:{beat}"


def format_duration_sec(seconds: float) -> str:
    """Format seconds as "MM:SS"."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"
