"""
D.I.M — run_tui.py
Entry point for the TUI (Textual) interface.

Usage:
    ./dim tui formats/example_project.json
    ./dim tui formats/example_project.json --play
    ./dim tui formats/example_project.json --link
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="D.I.M TUI", add_help=True)
    parser.add_argument("project", nargs="?", default=None,
                        help="Path to project JSON")
    parser.add_argument("--play", action="store_true",
                        help="Auto-play on launch")
    parser.add_argument("--link", action="store_true",
                        help="Enable Ableton Link on launch")
    args = parser.parse_args()

    project_path = args.project
    if project_path and not os.path.isabs(project_path):
        project_path = os.path.join(_ROOT, project_path)

    from adapters.tui.app import run_tui
    run_tui(
        project_path=project_path,
        auto_play=args.play,
        link=args.link,
    )


if __name__ == "__main__":
    main()
