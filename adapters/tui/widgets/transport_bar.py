"""
D.I.M — adapters/tui/widgets/transport_bar.py
Top transport bar: play state, BPM, position, beat pips, sync indicator.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label
from textual.containers import Horizontal


class TransportBar(Widget):
    """
    Single-row transport bar displayed at the top of the performance screen.

    Reacts to state dicts from the engine (same format as SocketIO state_update).
    """

    DEFAULT_CSS = """
    TransportBar {
        height: 3;
        background: $surface;
        border-bottom: solid $primary;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }
    TransportBar .play-icon {
        width: 3;
        color: $success;
        text-style: bold;
    }
    TransportBar .play-icon.stopped {
        color: $text-muted;
    }
    TransportBar .bpm {
        width: 11;
        color: $primary;
        text-style: bold;
        padding: 0 1;
    }
    TransportBar .pos {
        width: 10;
        color: $text;
        padding: 0 1;
    }
    TransportBar .elapsed {
        width: 8;
        color: $text-muted;
        padding: 0 1;
    }
    TransportBar .pips {
        width: 12;
        color: $warning;
        padding: 0 1;
    }
    TransportBar .sync {
        dock: right;
        width: 18;
        color: $success;
        text-style: dim;
        padding: 0 1;
    }
    TransportBar .sync.inactive {
        color: $text-muted;
    }
    """

    _state: reactive[dict] = reactive({})

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._playing     = False
        self._bpm         = 120.0
        self._position    = "1:1"
        self._elapsed     = "0:00"
        self._pips        = "○○○○"
        self._sync_text   = ""
        self._sync_active = False

    def compose(self) -> ComposeResult:
        yield Label("▶", classes="play-icon stopped", id="play-icon")
        yield Label("120.0 BPM", classes="bpm", id="bpm")
        yield Label("1 : 1", classes="pos", id="pos")
        yield Label("0:00", classes="elapsed", id="elapsed")
        yield Label("○○○○", classes="pips", id="pips")
        yield Label("", classes="sync inactive", id="sync")

    def update_state(self, state: dict) -> None:
        if not state.get("loaded"):
            return

        playing      = state.get("playing", False)
        bpm          = state.get("tempo_bpm", 120.0)
        bar          = state.get("bar", 1)
        beat_in_bar  = state.get("beat_in_bar", 1)
        elapsed      = state.get("elapsed_fmt", "0:00")
        beat_progress = state.get("beat_progress", 0.0)
        time_sig     = state.get("time_signature", "4/4")

        # Beat pips
        try:
            beats_per_bar = int(time_sig.split("/")[0])
        except Exception:
            beats_per_bar = 4
        beats_per_bar = min(beats_per_bar, 8)

        filled = beat_in_bar - 1
        pips = "●" * filled + "◉" + "○" * (beats_per_bar - filled - 1)

        # Play icon
        play_icon = self.query_one("#play-icon", Label)
        play_icon.update("▶" if playing else "⏸")
        play_icon.remove_class("stopped")
        if not playing:
            play_icon.add_class("stopped")

        self.query_one("#bpm", Label).update(f"{bpm:.1f} BPM")
        self.query_one("#pos", Label).update(f"{bar} : {beat_in_bar}")
        self.query_one("#elapsed", Label).update(elapsed)
        self.query_one("#pips", Label).update(pips)

    def update_sync(self, sync_status: dict | None) -> None:
        """Update sync indicator from /api/sync/status response."""
        sync_label = self.query_one("#sync", Label)

        if not sync_status:
            sync_label.update("")
            sync_label.add_class("inactive")
            return

        # Link
        link = sync_status.get("link")
        if link and link.get("available"):
            peers = link.get("peers", 0)
            bpm   = link.get("tempo_bpm", 0)
            sync_label.update(f"LINK ● {peers}p  {bpm:.0f}")
            sync_label.remove_class("inactive")
            return

        # MIDI
        midi = sync_status.get("midi_in")
        if midi and midi.get("available"):
            bpm = midi.get("tempo_bpm", 0)
            sync_label.update(f"MIDI ●  {bpm:.0f}")
            sync_label.remove_class("inactive")
            return

        # OSC
        osc = sync_status.get("osc")
        if osc and osc.get("available"):
            sync_label.update("OSC  ●")
            sync_label.remove_class("inactive")
            return

        sync_label.update("INT")
        sync_label.add_class("inactive")
