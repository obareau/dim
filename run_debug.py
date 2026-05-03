"""
D.I.M — run_debug.py
Debug & Test Launcher — Textual TUI.

Usage:
    ./dim debug
    PYTHONPATH=. .venv/bin/python run_debug.py

Keyboard:
    ↑ ↓      navigate commands
    Enter    run selected command
    Esc / q  quit
    c        clear output
"""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Footer, Label, ListItem, ListView, RichLog, Static


# ── Style palette ──────────────────────────────────────────────────────────────

_STYLE = {
    "head": "bold cyan",
    "ok":   "green",
    "warn": "yellow",
    "err":  "bold red",
    "info": "white",
    "dim":  "dim white",
}


# ── Command registry ───────────────────────────────────────────────────────────

COMMANDS: list[dict] = [
    {
        "id":    "run_tests",
        "label": "▸  Run all tests",
        "desc":  "pytest — full suite (excluding live Link)",
        "icon":  "🧪",
    },
    {
        "id":    "link_scan",
        "label": "▸  Scan Link peers",
        "desc":  "Discover Ableton Link devices on the LAN (5s)",
        "icon":  "🔍",
    },
    {
        "id":    "link_test",
        "label": "▸  Link tempo sequence",
        "desc":  "Random jumps [66,77,88,99,111,222] → sweep 111→101",
        "icon":  "🎛",
    },
    {
        "id":    "midi_ports",
        "label": "▸  MIDI ports",
        "desc":  "List all MIDI input / output ports",
        "icon":  "🎹",
    },
    {
        "id":    "validate",
        "label": "▸  Validate project",
        "desc":  "Validate formats/example_project.json",
        "icon":  "✅",
    },
    {
        "id":    "cli_play",
        "label": "▸  CLI playback (32 beats)",
        "desc":  "Run the sequencer on example_project.json",
        "icon":  "▶",
    },
    {
        "id":    "osc_test",
        "label": "▸  OSC loopback test",
        "desc":  "Send + receive a test OSC message",
        "icon":  "📡",
    },
    {
        "id":    "sysinfo",
        "label": "▸  System info",
        "desc":  "Python, deps, network interfaces",
        "icon":  "ℹ",
    },
]


# ── Widgets ────────────────────────────────────────────────────────────────────

class CommandList(ListView):
    """Left sidebar — list of available commands."""

    DEFAULT_CSS = """
    CommandList {
        width: 32;
        border-right: solid $primary 50%;
        background: $surface;
        padding: 0;
    }
    CommandList > ListItem {
        padding: 0 1;
        height: 3;
        color: $text;
    }
    CommandList > ListItem.--highlight {
        background: $primary 30%;
        color: $text;
    }
    CommandList > ListItem Label {
        width: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        items = []
        for cmd in COMMANDS:
            item = ListItem(
                Label(f" {cmd['label']}"),
                id=f"cmd-{cmd['id']}",
            )
            items.append(item)
        super().__init__(*items, **kwargs)


class OutputPanel(RichLog):
    """Right panel — scrollable output log."""

    DEFAULT_CSS = """
    OutputPanel {
        background: $background;
        padding: 1 2;
        border: none;
        height: 1fr;
        scrollbar-gutter: stable;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(highlight=True, markup=True, wrap=True, **kwargs)

    def emit_line(self, style: str, text: str) -> None:
        rich_style = _STYLE.get(style, "white")
        self.write(f"[{rich_style}]{text}[/{rich_style}]")

    def emit_header(self) -> None:
        self.write("")
        self.write("[bold cyan]" + "─" * 60 + "[/bold cyan]")


class InfoBar(Static):
    """Bottom info bar showing selected command description."""

    DEFAULT_CSS = """
    InfoBar {
        height: 1;
        background: $surface;
        color: $text-muted;
        text-style: dim;
        padding: 0 2;
        dock: bottom;
    }
    """

    description: reactive[str] = reactive("Select a command and press Enter")

    def render(self) -> str:
        return f"  {self.description}"


# ── App ────────────────────────────────────────────────────────────────────────

class DebugLauncher(App):
    """D.I.M Debug & Test Launcher."""

    TITLE    = "D·I·M  Debug"
    CSS = """
    DebugLauncher {
        background: #0d0d0d;
    }
    #title {
        height: 1;
        background: $primary;
        color: $background;
        text-style: bold;
        text-align: center;
        padding: 0 2;
    }
    #body {
        height: 1fr;
        layout: horizontal;
    }
    #desc-bar {
        height: 1;
        background: $surface;
        color: $text-muted;
        text-style: dim;
        padding: 0 2;
    }
    Footer {
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("enter",       "run_command",  "Run",    priority=True),
        Binding("c",           "clear_output", "Clear"),
        Binding("q,escape",    "quit",         "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Label(" D·I·M  ░  Debug & Test Launcher", id="title")
        with Horizontal(id="body"):
            yield CommandList(id="cmd-list")
            yield OutputPanel(id="output")
        yield Label("", id="desc-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._update_desc()
        output = self.query_one("#output", OutputPanel)
        output.write("[bold cyan]D·I·M Debug Launcher[/bold cyan]")
        output.write("[dim]Select a command and press Enter.[/dim]")
        output.write("")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._update_desc()

    def _update_desc(self) -> None:
        lst = self.query_one("#cmd-list", CommandList)
        idx = lst.index
        if idx is not None and 0 <= idx < len(COMMANDS):
            desc = COMMANDS[idx]["desc"]
            label = COMMANDS[idx]["label"].strip()
            self.query_one("#desc-bar", Label).update(
                f"  {label}  │  {desc}"
            )

    def action_clear_output(self) -> None:
        self.query_one("#output", OutputPanel).clear()

    def action_run_command(self) -> None:
        lst = self.query_one("#cmd-list", CommandList)
        idx = lst.index
        if idx is None or idx < 0 or idx >= len(COMMANDS):
            return
        cmd_id = COMMANDS[idx]["id"]
        self.run_worker(self._execute(cmd_id), exclusive=False)

    async def _execute(self, cmd_id: str) -> None:
        from adapters.debug import commands as cmds

        output = self.query_one("#output", OutputPanel)
        output.emit_header()

        gen = None
        if cmd_id == "run_tests":
            gen = cmds.run_tests()
        elif cmd_id == "link_scan":
            gen = cmds.link_scan(duration=5.0)
        elif cmd_id == "link_test":
            gen = cmds.link_test_sequence()
        elif cmd_id == "midi_ports":
            gen = cmds.midi_ports()
        elif cmd_id == "validate":
            gen = cmds.validate_project()
        elif cmd_id == "cli_play":
            gen = cmds.cli_playback(beats=32)
        elif cmd_id == "osc_test":
            gen = cmds.osc_test()
        elif cmd_id == "sysinfo":
            gen = cmds.system_info()

        if gen is None:
            output.emit_line("warn", f"Unknown command: {cmd_id}")
            return

        async for style, text in gen:
            output.emit_line(style, text)

        output.scroll_end(animate=False)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    DebugLauncher().run()


if __name__ == "__main__":
    main()
