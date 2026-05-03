"""
D.I.M — run_web.py
Entry point for the web interface.

Usage:
    ./dim formats/example_project.json           ← recommended
    ./dim formats/example_project.json --port 8080

    # or manually with the venv python:
    python3 -m venv .venv && .venv/bin/pip install flask flask-socketio pytest
    PYTHONPATH=. .venv/bin/python run_web.py formats/example_project.json
"""
from __future__ import annotations

import argparse
import os
import socket
import sys

# Ensure project root on path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from adapters.web.app import create_app

# ── ANSI ──────────────────────────────────────────────────────────────────────

R  = "\033[0m"
B  = "\033[1m"
D  = "\033[2m"
RD = "\033[31m"
GR = "\033[32m"
YL = "\033[33m"
CY = "\033[36m"
WH = "\033[97m"


# ── Port helpers ──────────────────────────────────────────────────────────────

def _port_free(port: int) -> bool:
    """Return True if nothing is listening on port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _find_port(start: int, max_tries: int = 20) -> int:
    for port in range(start, start + max_tries):
        if _port_free(port):
            return port
    raise RuntimeError(f"No free port found between {start} and {start + max_tries - 1}")


# ── Banner ────────────────────────────────────────────────────────────────────

def _banner(port: int, host: str, project_path: str | None, project_name: str | None) -> None:
    w = 52
    line = "─" * w

    print()
    print(f"  {B}{WH}{'D · I · M':^{w}}{R}")
    print(f"  {D}{'Dawless Is More':^{w}}{R}")
    print(f"  {D}{line}{R}")
    print()

    url = f"http://localhost:{port}"
    print(f"  {CY}{'':>2}{'Web':>8}  {B}{url}{R}")
    print(f"  {'':>2}{'Editor':>8}  {D}{url}/editor{R}")
    print(f"  {'':>2}{'Perform':>8}  {D}{url}/performance{R}")
    print()

    if project_path:
        name = project_name or os.path.basename(project_path)
        print(f"  {'':>2}{'Project':>8}  {YL}{name}{R}")
    else:
        print(f"  {YL}  No project loaded — open {url} to import one{R}")

    print()
    print(f"  {D}{line}{R}")
    print(f"  {D}  Space: play/pause   Ctrl+C: quit{R}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="D.I.M Web Server", add_help=True)
    parser.add_argument("project", nargs="?", default=None,
                        help="Path to project JSON file to load on startup")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("DIM_PORT", 5001)),
                        help="Starting port (auto-increments if busy, default: 5001)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug mode")
    args = parser.parse_args()

    # Resolve project path
    project_path = args.project
    if project_path and not os.path.isabs(project_path):
        project_path = os.path.join(_ROOT, project_path)

    # Find a free port
    requested = args.port
    port = _find_port(requested)
    if port != requested:
        print(f"\n  {YL}Port {requested} busy → using {port}{R}")

    # Create app + load project
    app, socketio = create_app(project_path)

    # Grab project name for banner
    project_name = None
    if project_path:
        try:
            from adapters.web import engine as _eng
            pd = _eng.get_project_dict()
            if pd:
                project_name = pd["project"].get("name")
        except Exception:
            pass

    # Print banner
    _banner(port, args.host, project_path, project_name)

    # Suppress Werkzeug's "production" warning — it's fine for local use
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    socketio.run(app, host=args.host, port=port, debug=args.debug,
                 use_reloader=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
