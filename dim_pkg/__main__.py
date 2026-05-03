"""
D.I.M — dim_pkg/__main__.py
Entry point: `python -m dim_pkg` or the `dim` console script (pip install).

Usage:
    dim [project.json] [--port 5001] [--host 0.0.0.0]
    dim web   [project.json] [--port 5001] [--host 0.0.0.0]
    dim cli   play   formats/example_project.json
    dim tui   [project.json] [--play] [--link]
    dim debug
    dim test  [pytest args...]
    dim version
"""
from __future__ import annotations

import sys
import os

# When installed via pip, siblings (core/, adapters/, network/) are top-level packages.
# When run from source, the project root must be on sys.path.
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _usage() -> None:
    print(__doc__)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        _usage()
        return

    cmd = args[0]

    # ── version ───────────────────────────────────────────────────────────────
    if cmd == "version":
        try:
            from importlib.metadata import version
            print(f"dim {version('dim-sequencer')}")
        except Exception:
            from dim_pkg import __version__
            print(f"dim {__version__}")
        return

    # ── test ──────────────────────────────────────────────────────────────────
    if cmd == "test":
        import subprocess
        tests_dir = os.path.join(_HERE, "tests")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", tests_dir] + args[1:],
            env={**os.environ, "PYTHONPATH": _HERE},
        )
        sys.exit(result.returncode)

    # ── cli ───────────────────────────────────────────────────────────────────
    if cmd == "cli":
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cli", os.path.join(_HERE, "cli.py")
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        sys.argv = ["dim-cli"] + args[1:]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return

    # ── tui ───────────────────────────────────────────────────────────────────
    if cmd == "tui":
        from adapters.tui.app import run_tui
        import argparse
        p = argparse.ArgumentParser(prog="dim tui")
        p.add_argument("project", nargs="?", default=None)
        p.add_argument("--play", action="store_true")
        p.add_argument("--link", action="store_true")
        opts = p.parse_args(args[1:])
        run_tui(project_path=opts.project, autoplay=opts.play, use_link=opts.link)
        return

    # ── debug ─────────────────────────────────────────────────────────────────
    if cmd == "debug":
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "run_debug", os.path.join(_HERE, "run_debug.py")
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return

    # ── web (default) ─────────────────────────────────────────────────────────
    import argparse
    p = argparse.ArgumentParser(prog="dim")
    p.add_argument("project", nargs="?", default=None,
                   help="Path to project JSON file")
    p.add_argument("--port", "-p", type=int, default=5001)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--debug", action="store_true")

    # Accept both `dim project.json` and `dim web project.json`
    rest = args[1:] if cmd == "web" else args
    opts = p.parse_args(rest)

    from adapters.web.app import create_app
    app, socketio = create_app(project_path=opts.project)
    print(f"\n  D.I.M  →  http://{opts.host}:{opts.port}\n")
    socketio.run(app, host=opts.host, port=opts.port, debug=opts.debug,
                 allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
