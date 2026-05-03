"""
D.I.M — adapters/sync/base.py
Base types for all sync sources.

A SyncSource is any external clock provider: MIDI Clock, Ableton Link, OSC.
The SyncManager polls registered sources and drives the engine accordingly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


# ── Sync state ─────────────────────────────────────────────────────────────────

class SyncSourceType(str, Enum):
    MIDI_CLOCK  = "midi_clock"
    ABLETON_LINK = "ableton_link"
    OSC          = "osc"
    INTERNAL     = "internal"


@dataclass(frozen=True)
class SyncState:
    """Snapshot from a sync source."""
    source:       SyncSourceType
    tempo_bpm:    float               # beats per minute
    beat_position: float              # master beat position (0-based), if available
    is_playing:   bool
    is_available: bool = True         # False = source connected but no signal


# ── Callbacks ──────────────────────────────────────────────────────────────────

TempoCallback  = Callable[[float], None]           # bpm
BeatCallback   = Callable[[float], None]           # beat_position
PlayCallback   = Callable[[bool], None]            # is_playing


# ── Abstract base ──────────────────────────────────────────────────────────────

class SyncSource(ABC):
    """Abstract sync source. Start/stop a background thread, emit callbacks."""

    def __init__(self) -> None:
        self._on_tempo:  list[TempoCallback]  = []
        self._on_beat:   list[BeatCallback]   = []
        self._on_play:   list[PlayCallback]   = []

    # ── Registration ──────────────────────────────────────────────────────────

    def on_tempo(self, cb: TempoCallback) -> None:
        self._on_tempo.append(cb)

    def on_beat(self, cb: BeatCallback) -> None:
        self._on_beat.append(cb)

    def on_play(self, cb: PlayCallback) -> None:
        self._on_play.append(cb)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _emit_tempo(self, bpm: float) -> None:
        for cb in self._on_tempo:
            try:
                cb(bpm)
            except Exception:
                pass

    def _emit_beat(self, beat: float) -> None:
        for cb in self._on_beat:
            try:
                cb(beat)
            except Exception:
                pass

    def _emit_play(self, playing: bool) -> None:
        for cb in self._on_play:
            try:
                cb(playing)
            except Exception:
                pass

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    def start(self) -> None:
        """Start the background thread / listener."""

    @abstractmethod
    def stop(self) -> None:
        """Stop cleanly."""

    @abstractmethod
    def get_state(self) -> SyncState:
        """Current snapshot (non-blocking)."""

    @property
    @abstractmethod
    def source_type(self) -> SyncSourceType:
        ...
