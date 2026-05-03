"""
D.I.M — adapters/tui/widgets/lane_panel.py
Per-lane panel: prev / current / next cue + progress bar.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, ProgressBar
from textual.containers import Vertical


# ── Cue row ────────────────────────────────────────────────────────────────────

class CueRow(Widget):
    """One cue slot: label, content snippet, instruction badge."""

    DEFAULT_CSS = """
    CueRow {
        height: 3;
        padding: 0 1;
        border: none;
    }
    CueRow.current {
        background: $primary 20%;
        border-left: thick $primary;
    }
    CueRow.prev {
        color: $text-muted;
        text-style: dim;
    }
    CueRow.next {
        color: $text-muted;
    }
    CueRow.empty {
        color: $text-disabled;
        text-style: dim;
    }
    CueRow .cue-label {
        text-style: bold;
        width: 1fr;
    }
    CueRow .cue-badge {
        text-align: right;
        color: $warning;
        width: 12;
    }
    CueRow .cue-content {
        color: $text-muted;
        text-style: italic;
        width: 1fr;
    }
    """

    def __init__(self, role: str = "current", **kwargs) -> None:
        # role: "prev" | "current" | "next" | "empty"
        super().__init__(classes=role, **kwargs)
        self._role = role

    def compose(self) -> ComposeResult:
        yield Label("—", classes="cue-label", id="lbl")
        yield Label("", classes="cue-content", id="content")
        yield Label("", classes="cue-badge", id="badge")

    def set_cue(self, cue: dict | None) -> None:
        if cue is None:
            self.query_one("#lbl", Label).update("—")
            self.query_one("#content", Label).update("")
            self.query_one("#badge", Label).update("")
            self.add_class("empty")
            return

        self.remove_class("empty")
        label   = cue.get("label") or cue.get("id", "?")
        content = (cue.get("content") or "")[:24]
        badge   = cue.get("badge", "")

        self.query_one("#lbl",     Label).update(label)
        self.query_one("#content", Label).update(content)
        self.query_one("#badge",   Label).update(badge)


# ── Progress bar ───────────────────────────────────────────────────────────────

class CueProgress(Widget):
    """Thin progress bar + remaining bars text."""

    DEFAULT_CSS = """
    CueProgress {
        height: 2;
        padding: 0 1;
    }
    CueProgress Label {
        text-align: right;
        color: $text-muted;
        width: 1fr;
        text-style: dim;
    }
    CueProgress ProgressBar {
        width: 1fr;
    }
    CueProgress ProgressBar > .bar--bar {
        color: $primary;
    }
    """

    def compose(self) -> ComposeResult:
        yield ProgressBar(total=100, show_eta=False, show_percentage=False, id="pbar")
        yield Label("", id="rem")

    def set_progress(self, bars_remaining: float, beats_remaining: float) -> None:
        # We don't know total easily, so show a pulse when playing
        # Use bars_remaining as a countdown — invert for a "fill from left" feel
        # Clamp to 0-100 using a 8-bar max window
        max_bars = max(8.0, bars_remaining)
        pct = max(0, min(100, int((1.0 - bars_remaining / max_bars) * 100)))
        self.query_one("#pbar", ProgressBar).progress = pct

        if bars_remaining > 0:
            self.query_one("#rem", Label).update(f"{bars_remaining:.1f} bars")
        else:
            self.query_one("#rem", Label).update("—")


# ── Lane panel ─────────────────────────────────────────────────────────────────

class LanePanel(Widget):
    """
    Full panel for one lane: header, prev/current/next cue rows, progress.
    """

    DEFAULT_CSS = """
    LanePanel {
        border: solid $surface-lighten-1;
        height: 1fr;
        min-width: 22;
        padding: 0;
    }
    LanePanel.conductor {
        border: solid $accent;
    }
    LanePanel.ended {
        border: solid $surface;
        opacity: 0.5;
    }
    LanePanel.waiting {
        border: solid $warning;
    }
    LanePanel .lane-header {
        background: $surface-lighten-1;
        color: $text;
        text-style: bold;
        padding: 0 1;
        height: 2;
    }
    LanePanel.conductor .lane-header {
        background: $accent 30%;
    }
    LanePanel .divider {
        height: 1;
        background: $surface-lighten-1;
        color: $text-muted;
        padding: 0 1;
    }
    LanePanel .section-name {
        color: $text-muted;
        text-style: dim;
        padding: 0 1;
        height: 1;
    }
    LanePanel .manual-hint {
        color: $warning;
        text-style: bold;
        text-align: center;
        height: 1;
    }
    """

    def __init__(self, lane_id: str, lane_name: str, color: str = "",
                 is_conductor: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.lane_id      = lane_id
        self.lane_name    = lane_name
        self.lane_color   = color
        self.is_conductor = is_conductor
        if is_conductor:
            self.add_class("conductor")

    def compose(self) -> ComposeResult:
        icon = "★" if self.is_conductor else "◈"
        yield Label(f" {icon}  {self.lane_name}", classes="lane-header", id="hdr")
        yield Label("", classes="section-name", id="section-name")
        yield Label("─" * 40, classes="divider")
        yield CueRow(role="prev",    id="prev-cue")
        yield Label("━" * 40, classes="divider")
        yield CueRow(role="current", id="curr-cue")
        yield Label("─" * 40, classes="divider")
        yield CueRow(role="next",    id="next-cue")
        yield Label("─" * 40, classes="divider")
        yield CueProgress(id="progress")
        yield Label("", classes="manual-hint", id="manual-hint")

    def update_lane(self, lane_state: dict) -> None:
        ended   = lane_state.get("ended", False)
        waiting = lane_state.get("waiting_manual", False)

        self.remove_class("ended")
        self.remove_class("waiting")
        if ended:
            self.add_class("ended")
        elif waiting:
            self.add_class("waiting")

        # Section name
        sec_name = lane_state.get("section_name") or ""
        sec_type = lane_state.get("section_type") or ""
        sec_pass = lane_state.get("section_pass", 0)
        sec_label = f"  {sec_name}"
        if sec_type and sec_type != "linear":
            sec_label += f"  [{sec_type}]"
        if sec_pass > 0:
            sec_label += f"  pass {sec_pass + 1}"
        self.query_one("#section-name", Label).update(sec_label)

        # Cues
        self.query_one("#prev-cue", CueRow).set_cue(lane_state.get("prev_cue"))
        self.query_one("#curr-cue", CueRow).set_cue(lane_state.get("cue"))
        self.query_one("#next-cue", CueRow).set_cue(lane_state.get("next_cue"))

        # Progress
        bars_rem  = lane_state.get("bars_remaining", 0.0)
        beats_rem = lane_state.get("beats_remaining", 0.0)
        self.query_one("#progress", CueProgress).set_progress(bars_rem, beats_rem)

        # Manual hint
        hint = self.query_one("#manual-hint", Label)
        hint.update("⊙  SPACE to advance" if waiting else "")
