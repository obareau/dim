"""
D.I.M — adapters/tui/screens/performance.py
Full-screen TUI performance view.

Driven by the engine directly (same process) via a periodic poll.
Keyboard: Space=play/pause  R=rewind  S=stop  Q=quit  L=link toggle
"""
from __future__ import annotations

import asyncio
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Label, Static
from textual.timer import Timer

from adapters.tui.widgets.transport_bar import TransportBar
from adapters.tui.widgets.lane_panel import LanePanel


TICK_HZ = 20   # UI refresh rate


class PerformanceScreen(Screen):
    """
    Main performance view.
    Polls the engine at TICK_HZ and updates all widgets reactively.
    """

    BINDINGS = [
        Binding("space",       "toggle_play",  "Play / Pause",  priority=True),
        Binding("r",           "rewind",        "Rewind"),
        Binding("s",           "stop",          "Stop"),
        Binding("q",           "quit_app",      "Quit"),
        Binding("l",           "toggle_link",   "Link"),
        Binding("up",          "tempo_up",      "BPM +1"),
        Binding("down",        "tempo_down",    "BPM -1"),
        Binding("shift+up",    "tempo_up10",    "BPM +10"),
        Binding("shift+down",  "tempo_down10",  "BPM -10"),
    ]

    DEFAULT_CSS = """
    PerformanceScreen {
        layout: vertical;
        background: $background;
    }
    #title-bar {
        height: 1;
        background: $primary;
        color: $background;
        text-style: bold;
        padding: 0 2;
        text-align: center;
    }
    #lanes-container {
        layout: horizontal;
        height: 1fr;
    }
    #status-bar {
        height: 1;
        background: $surface;
        color: $text-muted;
        text-style: dim;
        padding: 0 2;
    }
    """

    def __init__(self, project_name: str = "D·I·M", **kwargs) -> None:
        super().__init__(**kwargs)
        self._project_name = project_name
        self._lane_panels: dict[str, LanePanel] = {}
        self._tick_timer: Optional[Timer] = None
        self._link_active = False

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Label(
            f" D·I·M  ░  {self._project_name} ",
            id="title-bar",
        )
        yield TransportBar(id="transport")
        yield Horizontal(id="lanes-container")
        yield Label(
            "  Space play/pause   R rewind   S stop   ↑↓ BPM   L link   Q quit",
            id="status-bar",
        )

    def on_mount(self) -> None:
        self._build_lanes()
        self._tick_timer = self.set_interval(1.0 / TICK_HZ, self._tick)

    def _build_lanes(self) -> None:
        """Build lane panels from the currently loaded project."""
        from adapters.web import engine
        proj = engine.get_project_dict()
        if proj is None:
            return

        container = self.query_one("#lanes-container", Horizontal)
        container.remove_children()
        self._lane_panels.clear()

        for ln in proj["project"]["lanes"]:
            panel = LanePanel(
                lane_id=ln["id"],
                lane_name=ln["name"],
                color=ln.get("color", ""),
                is_conductor=ln.get("is_conductor", False),
                id=f"lane-{ln['id']}",
            )
            container.mount(panel)
            self._lane_panels[ln["id"]] = panel

    # ── Tick ──────────────────────────────────────────────────────────────────

    async def _tick(self) -> None:
        from adapters.web import engine
        state = engine.get_state()
        if not state.get("loaded"):
            return

        # Transport bar
        self.query_one("#transport", TransportBar).update_state(state)

        # Lane panels
        lanes = state.get("lanes", {})
        for lane_id, panel in self._lane_panels.items():
            lane_state = lanes.get(lane_id)
            if lane_state:
                panel.update_lane(lane_state)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_toggle_play(self) -> None:
        from adapters.web import engine
        state = engine.get_state()
        if state.get("playing"):
            engine.stop()
        else:
            engine.play()

    def action_rewind(self) -> None:
        from adapters.web import engine
        engine.rewind()

    def action_stop(self) -> None:
        from adapters.web import engine
        engine.stop()
        engine.rewind()

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_tempo_up(self) -> None:
        self._nudge_tempo(+1.0)

    def action_tempo_down(self) -> None:
        self._nudge_tempo(-1.0)

    def action_tempo_up10(self) -> None:
        self._nudge_tempo(+10.0)

    def action_tempo_down10(self) -> None:
        self._nudge_tempo(-10.0)

    def _nudge_tempo(self, delta: float) -> None:
        from adapters.web import engine
        state = engine.get_state()
        bpm = state.get("tempo_bpm", 120.0) + delta
        bpm = max(20.0, min(300.0, bpm))
        engine.set_tempo(bpm)

    def action_toggle_link(self) -> None:
        """Start Ableton Link if not running, show status."""
        try:
            from adapters.sync.link_sync import is_link_available, make_link_source
            from adapters.sync.manager import get_manager
            from adapters.web import engine as eng
            if not is_link_available():
                self._set_status("Link: aalink not installed")
                return
            mgr = get_manager()
            if mgr._link is None:
                link = make_link_source()
                mgr.set_engine_callbacks(eng.set_tempo, eng.set_playing)
                mgr.add_link(link)
                link.start()
                self._link_active = True
                self._set_status("Link: joined session")
            else:
                mgr._link.stop()
                mgr._link = None
                self._link_active = False
                self._set_status("Link: disconnected")
        except Exception as e:
            self._set_status(f"Link error: {e}")

    def _set_status(self, msg: str) -> None:
        self.query_one("#status-bar", Label).update(
            f"  {msg}  │  Space play/pause   R rewind   ↑↓ BPM   L link   Q quit"
        )
        self.set_timer(3.0, self._reset_status)

    def _reset_status(self) -> None:
        self.query_one("#status-bar", Label).update(
            "  Space play/pause   R rewind   S stop   ↑↓ BPM   L link   Q quit"
        )
