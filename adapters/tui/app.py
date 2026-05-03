"""
D.I.M — adapters/tui/app.py
Textual application entry point.

Usage:
    ./dim tui formats/example_project.json
    ./dim tui formats/example_project.json --link
"""
from __future__ import annotations

import os
import sys

from textual.app import App

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class DimTuiApp(App):
    """
    D.I.M TUI — full-screen performance view.
    Shares the same engine as the web adapter (can run standalone or alongside).
    """

    CSS = """
    Screen {
        background: #0d0d0d;
    }
    """

    TITLE = "D·I·M"
    SUB_TITLE = "Dawless Is More"

    def __init__(self, project_path: str | None = None,
                 auto_play: bool = False,
                 link: bool = False,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self._project_path = project_path
        self._auto_play    = auto_play
        self._link         = link

    def on_mount(self) -> None:
        from adapters.web import engine
        from adapters.tui.screens.performance import PerformanceScreen

        # Init engine (no SocketIO needed for TUI-only mode)
        engine.init(None)
        engine.start_thread()

        project_name = "D·I·M"
        if self._project_path:
            try:
                proj = engine.load(self._project_path)
                project_name = proj.name
            except Exception as e:
                project_name = f"Error: {e}"

        if self._auto_play:
            engine.play()

        # Start Link if requested
        if self._link:
            try:
                from adapters.sync.link_sync import make_link_source, is_link_available
                from adapters.sync.manager import get_manager
                if is_link_available():
                    mgr = get_manager()
                    link = make_link_source()
                    mgr.set_engine_callbacks(engine.set_tempo, engine.set_playing)
                    mgr.add_link(link)
                    link.start()
            except Exception:
                pass

        self.push_screen(PerformanceScreen(project_name=project_name))


def run_tui(project_path: str | None = None,
            auto_play: bool = False,
            link: bool = False) -> None:
    """Entry point called from run_tui.py / dim launcher."""
    app = DimTuiApp(
        project_path=project_path,
        auto_play=auto_play,
        link=link,
    )
    app.run()
