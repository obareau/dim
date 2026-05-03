"""
D.I.M — adapters/debug/commands.py
All debug commands — each is an async generator that yields output lines.

Commands:
  run_tests          pytest suite
  link_scan          scan for Link peers (IP, hostname, packets)
  link_test_sequence full tempo jump/sweep test (broadcast to Link network)
  midi_ports         list MIDI input/output ports
  validate_project   validate a project JSON
  cli_playback       run CLI playback on example project
  system_info        Python, deps, network interfaces
  osc_test           send/receive a test OSC message
"""
from __future__ import annotations

import asyncio
import os
import sys
import socket
import subprocess
from typing import AsyncGenerator

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


Line = tuple[str, str]   # (style, text)  style = "info"|"ok"|"warn"|"err"|"head"|"dim"


def _l(style: str, text: str) -> Line:
    return (style, text)


# ── run_tests ─────────────────────────────────────────────────────────────────

async def run_tests(
    extra_args: list[str] | None = None,
    live_only: bool = False,
) -> AsyncGenerator[Line, None]:
    yield _l("head", "═══  pytest  ═══════════════════════════════")

    python  = os.path.join(_ROOT, ".venv", "bin", "python")
    cmd = [python, "-m", "pytest", os.path.join(_ROOT, "tests"),
           "-v", "--tb=short", "--no-header",
           "--ignore", os.path.join(_ROOT, "tests", "test_link_live.py")]
    if extra_args:
        cmd += extra_args

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env={**os.environ, "PYTHONPATH": _ROOT},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    passed = failed = 0
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip()
        if not line:
            continue
        if " PASSED" in line:
            passed += 1
            style = "ok"
        elif " FAILED" in line or " ERROR" in line:
            failed += 1
            style = "err"
        elif line.startswith("FAILED") or "AssertionError" in line:
            style = "err"
        elif line.startswith("="):
            style = "head"
        elif line.startswith("E ") or line.startswith(">"):
            style = "warn"
        else:
            style = "dim"
        yield _l(style, line)

    await proc.wait()
    status = "ok" if proc.returncode == 0 else "err"
    yield _l(status, f"{'✓' if proc.returncode==0 else '✗'}  {passed} passed  {failed} failed  (exit {proc.returncode})")


# ── link_scan ─────────────────────────────────────────────────────────────────

async def link_scan(duration: float = 5.0) -> AsyncGenerator[Line, None]:
    yield _l("head", "═══  Ableton Link — peer scan  ══════════════")

    try:
        import aalink
    except ImportError:
        yield _l("err", "aalink not installed — run: pip install aalink")
        return

    from adapters.debug.link_scanner import scan_peers, _local_ips

    local_ips = _local_ips()
    yield _l("dim",  f"  Local  : {', '.join(local_ips)}")
    yield _l("info", f"  Mcast  : 224.76.78.75:20808")
    yield _l("info", f"  Scanning {duration:.0f}s…")
    yield _l("dim", "")

    peers, sdk_count, err = await scan_peers(duration=duration)

    if err:
        yield _l("warn", f"  ⚠  {err}")

    if not peers:
        if sdk_count > 0:
            yield _l("warn", f"  SDK reports {sdk_count} peer(s) but no packets captured")
            yield _l("dim",  "  (device may be on a different interface)")
        else:
            yield _l("warn", "  No Link peers found.")
            yield _l("dim",  "  Check: device on same subnet, Link enabled.")
        return

    yield _l("ok", f"  Found {len(peers)} peer(s)   SDK count: {sdk_count}")
    yield _l("dim", "")
    yield _l("dim", f"  {'IP':<18}  {'HOSTNAME':<30}  PKTS")
    yield _l("dim", "  " + "─" * 58)

    for p in sorted(peers, key=lambda x: x.ip):
        host = p.hostname or "—"
        yield _l("ok", f"  {p.ip:<18}  {host:<30}  {p.packet_count}")


# ── link_test_sequence ────────────────────────────────────────────────────────

async def link_test_sequence() -> AsyncGenerator[Line, None]:
    yield _l("head", "═══  Link tempo test sequence  ══════════════")

    try:
        import aalink
    except ImportError:
        yield _l("err", "aalink not installed")
        return

    import random

    JUMP_TEMPOS    = [66, 77, 88, 99, 111, 222]
    JUMP_HOLD_SEC  = 4.0
    SWEEP_FROM     = 111
    SWEEP_TO       = 101
    SWEEP_STEP_SEC = 1.0
    PEER_WAIT_SEC  = 5.0

    link = aalink.Link(120.0)
    link.enabled = True
    link.start_stop_sync_enabled = True

    # Wait for peers
    yield _l("info", f"Waiting for peers ({PEER_WAIT_SEC:.0f}s)…")
    deadline = asyncio.get_event_loop().time() + PEER_WAIT_SEC
    while asyncio.get_event_loop().time() < deadline:
        if link.num_peers > 0:
            break
        await asyncio.sleep(0.2)

    peers = link.num_peers
    if peers == 0:
        yield _l("warn", "No peers — broadcasting anyway (solo mode)")
    else:
        yield _l("ok", f"  {peers} peer(s) connected  ✓")

    yield _l("dim", "")

    # Phase 1: random jumps
    yield _l("head", "  Phase 1 — Random jumps")
    shuffled = JUMP_TEMPOS[:]
    random.shuffle(shuffled)
    for bpm in shuffled:
        link.tempo = float(bpm)
        actual = link.tempo
        yield _l("info", f"  ▶  {actual:>7.2f} BPM   peers={link.num_peers}")
        await asyncio.sleep(JUMP_HOLD_SEC)

    yield _l("dim", "")

    # Phase 2: anchor 111
    yield _l("head", "  Phase 2 — Return to 111")
    link.tempo = 111.0
    yield _l("info", f"  ▶  {link.tempo:>7.2f} BPM  (anchor)")
    await asyncio.sleep(JUMP_HOLD_SEC)

    yield _l("dim", "")

    # Phase 3: sweep 111→101
    yield _l("head", "  Phase 3 — Sweep 111 → 101")
    for bpm in range(SWEEP_FROM, SWEEP_TO - 1, -1):
        link.tempo = float(bpm)
        yield _l("info", f"  ▼  {link.tempo:>7.2f} BPM")
        await asyncio.sleep(SWEEP_STEP_SEC)

    link.enabled = False
    yield _l("dim", "")
    yield _l("ok", "  ✓  Sequence complete.")


# ── midi_ports ────────────────────────────────────────────────────────────────

async def midi_ports() -> AsyncGenerator[Line, None]:
    yield _l("head", "═══  MIDI ports  ════════════════════════════")
    try:
        import mido
    except ImportError:
        yield _l("err", "mido not installed — run: pip install mido python-rtmidi")
        return

    ins  = mido.get_input_names()
    outs = mido.get_output_names()

    yield _l("info", f"Inputs  ({len(ins)}):")
    for p in ins:
        yield _l("ok",  f"  ◀  {p}")
    if not ins:
        yield _l("dim", "  (none)")

    yield _l("dim", "")
    yield _l("info", f"Outputs ({len(outs)}):")
    for p in outs:
        yield _l("ok",  f"  ▶  {p}")
    if not outs:
        yield _l("dim", "  (none)")


# ── validate_project ──────────────────────────────────────────────────────────

async def validate_project(path: str | None = None) -> AsyncGenerator[Line, None]:
    yield _l("head", "═══  Project validation  ════════════════════")
    if path is None:
        path = os.path.join(_ROOT, "formats", "example_project.json")

    yield _l("info", f"File: {os.path.basename(path)}")

    try:
        sys.path.insert(0, _ROOT)
        from core.serializer import load_project
        from core.validator import validate
        proj = load_project(path)
        errors = validate(proj)
    except Exception as e:
        yield _l("err", f"Load error: {e}")
        return

    yield _l("ok",  f"  Project : {proj.name}")
    yield _l("dim", f"  Tempo   : {proj.tempo_bpm} BPM  {proj.time_signature}")
    yield _l("dim", f"  Lanes   : {len(proj.lanes)}")
    total_sections = sum(len(l.sections) for l in proj.lanes)
    total_cues     = sum(len(s.cues) for l in proj.lanes for s in l.sections)
    yield _l("dim", f"  Sections: {total_sections}   Cues: {total_cues}")
    yield _l("dim", "")

    if not errors:
        yield _l("ok", "  ✓  Valid — no errors or warnings")
        return

    errs  = [e for e in errors if e.level == "error"]
    warns = [e for e in errors if e.level == "warning"]

    for e in errs:
        yield _l("err",  f"  ✗  {e}")
    for w in warns:
        yield _l("warn", f"  ⚠  {w}")

    style = "err" if errs else "warn"
    yield _l(style, f"  {len(errs)} error(s)  {len(warns)} warning(s)")


# ── cli_playback ──────────────────────────────────────────────────────────────

async def cli_playback(path: str | None = None, beats: int = 32) -> AsyncGenerator[Line, None]:
    yield _l("head", "═══  CLI playback  ══════════════════════════")
    if path is None:
        path = os.path.join(_ROOT, "formats", "example_project.json")
    yield _l("info", f"File: {os.path.basename(path)}  ({beats} beats)")

    python = os.path.join(_ROOT, ".venv", "bin", "python")
    cmd = [python, os.path.join(_ROOT, "cli.py"),
           "play", path, "--beats", str(beats), "--step", "1"]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env={**os.environ, "PYTHONPATH": _ROOT},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip()
        if not line:
            continue
        if "✓" in line:
            yield _l("ok", line)
        elif "⚠" in line or "Error" in line:
            yield _l("err", line)
        elif line.startswith("  ▶") or line.startswith("    ▸"):
            yield _l("info", line)
        elif line.startswith("  ■") or line.startswith("  ◼") or line.startswith("    ◂"):
            yield _l("dim", line)
        else:
            yield _l("dim", line)

    await proc.wait()


# ── system_info ───────────────────────────────────────────────────────────────

async def system_info() -> AsyncGenerator[Line, None]:
    yield _l("head", "═══  System info  ═══════════════════════════")

    import platform
    yield _l("info", f"  Python   {sys.version.split()[0]}  ({platform.machine()})")
    yield _l("info", f"  OS       {platform.system()} {platform.release()}")
    yield _l("dim", "")

    # Deps
    deps = [
        ("flask",         "flask"),
        ("flask_socketio","flask_socketio"),
        ("aalink",        "aalink"),
        ("mido",          "mido"),
        ("python-osc",    "pythonosc"),
        ("textual",       "textual"),
        ("pytest",        "pytest"),
        ("pytest-asyncio","pytest_asyncio"),
    ]
    yield _l("info", "  Dependencies:")
    for label, import_name in deps:
        try:
            import importlib.metadata as meta
            try:
                ver = meta.version(label)
            except Exception:
                mod = __import__(import_name)
                ver = getattr(mod, "__version__", "✓")
            yield _l("ok",  f"    ✓  {label:<22} {ver}")
        except (ImportError, Exception):
            yield _l("warn", f"    ✗  {label:<22} not installed")

    yield _l("dim", "")

    # Network interfaces
    yield _l("info", "  Network interfaces:")
    try:
        import subprocess as sp
        result = sp.run(["ifconfig"], capture_output=True, text=True)
        iface = ""
        for line in result.stdout.splitlines():
            if line and not line.startswith("\t") and not line.startswith(" "):
                iface = line.split(":")[0]
            if "inet " in line and "127.0.0.1" not in line:
                ip = line.strip().split()[1]
                yield _l("ok", f"    {iface:<8}  {ip}")
    except Exception as e:
        yield _l("warn", f"  (ifconfig failed: {e})")

    yield _l("dim", "")

    # Test suite count
    try:
        import glob
        test_files = glob.glob(os.path.join(_ROOT, "tests", "test_*.py"))
        yield _l("dim", f"  Test files: {len(test_files)}")
    except Exception:
        pass


# ── osc_test ──────────────────────────────────────────────────────────────────

async def osc_test(port: int = 57141) -> AsyncGenerator[Line, None]:
    yield _l("head", "═══  OSC loopback test  ══════════════════════")

    try:
        from pythonosc import udp_client
        from pythonosc.osc_message_builder import OscMessageBuilder
        from pythonosc.osc_bundle_builder import OscBundleBuilder
    except ImportError:
        yield _l("err", "python-osc not installed — run: pip install python-osc")
        return

    # Use raw UDP sockets — no blocking server thread needed
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        rx.bind(("127.0.0.1", port))
        rx.settimeout(1.0)
    except Exception as e:
        yield _l("err", f"Could not bind 127.0.0.1:{port} — {e}")
        rx.close()
        return

    client = udp_client.SimpleUDPClient("127.0.0.1", port)
    client.send_message("/dim/test", [120.0, 4.0, 1])
    yield _l("info", f"  Sent  →  /dim/test  [120.0, 4.0, 1]  to 127.0.0.1:{port}")

    loop = asyncio.get_running_loop()
    try:
        data, addr = await asyncio.wait_for(
            loop.run_in_executor(None, rx.recvfrom, 1024),
            timeout=1.5
        )
        rx.close()
        # Parse the raw OSC message to show address + args
        try:
            from pythonosc.osc_message import OscMessage
            msg = OscMessage(data)
            yield _l("ok", f"  Recv  ←  {msg.address}  {list(msg)}")
        except Exception:
            yield _l("ok", f"  Recv  ←  {len(data)} bytes from {addr[0]}:{addr[1]}")
        yield _l("ok", "  ✓  OSC loopback OK")
    except (asyncio.TimeoutError, Exception) as e:
        rx.close()
        yield _l("warn", f"  ✗  No reply in 1.5s ({e})")
