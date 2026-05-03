"""
D.I.M — tests/test_link_live.py
Live Ableton Link tempo test procedure.

Run:
    ./dim test tests/test_link_live.py -v -s

Sequence:
  1. Join Link session, wait for peers
  2. Random jumps across [66, 77, 88, 99, 111, 222], 4s each (shuffled, no repeat)
  3. Return to 111
  4. Sweep down 111 → 101, 1 BPM/step, 1s per step

All tempo changes are broadcast to the Link session so connected devices follow.
Requires: pip install aalink  (already installed)
Requires: at least one Ableton Link device on the LAN (otherwise test is skipped).
"""
import asyncio
import random
import time
import pytest

try:
    import aalink
    _AALINK = True
except ImportError:
    _AALINK = False


JUMP_TEMPOS   = [66, 77, 88, 99, 111, 222]
JUMP_HOLD_SEC = 4.0
SWEEP_FROM    = 111
SWEEP_TO      = 101
SWEEP_STEP_SEC = 1.0
PEER_WAIT_SEC  = 5.0

pytestmark = pytest.mark.asyncio


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ansi(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def _bold(t):   return _ansi("1", t)
def _cyan(t):   return _ansi("36", t)
def _yellow(t): return _ansi("33", t)
def _green(t):  return _ansi("32", t)
def _gray(t):   return _ansi("2", t)
def _red(t):    return _ansi("31", t)


async def _wait_peers(link, timeout: float = PEER_WAIT_SEC) -> bool:
    """Wait until at least 1 peer is visible on the Link session."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if link.num_peers > 0:
            return True
        await asyncio.sleep(0.2)
    return False


async def _set_tempo(link, bpm: float, label: str = "") -> None:
    """Set tempo and print confirmation."""
    link.tempo = bpm
    actual = link.tempo
    tag = f"  {label}" if label else ""
    print(f"  {_cyan(f'{actual:>7.2f} BPM')}{tag}  peers={link.num_peers}", flush=True)


# ── Test ───────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _AALINK, reason="aalink not installed")
@pytest.mark.asyncio
async def test_link_tempo_sequence():
    """
    Full Link tempo test sequence:
      - random jumps on [66,77,88,99,111,222]
      - return to 111
      - sweep 111 → 101
    """
    link = aalink.Link(120.0)
    link.enabled = True
    link.start_stop_sync_enabled = True

    tempo_log = []
    link.set_tempo_callback(lambda bpm: tempo_log.append(round(bpm, 2)))

    print()
    print(_bold("  ── D.I.M  Link Tempo Test ──────────────────"))
    print(f"  Waiting for peers ({PEER_WAIT_SEC}s)...")

    found = await _wait_peers(link, PEER_WAIT_SEC)
    if not found:
        pytest.skip(f"No Ableton Link peers found after {PEER_WAIT_SEC}s — connect a Link device")

    print(_green(f"  {link.num_peers} peer(s) found  ✓"))
    print()

    # ── Phase 1: Random jumps ──────────────────────────────────────────────────

    print(_bold("  Phase 1 — Random jumps"))
    print(_gray(f"  Values: {JUMP_TEMPOS}  hold={JUMP_HOLD_SEC}s each"))
    print()

    shuffled = JUMP_TEMPOS[:]
    random.shuffle(shuffled)

    for bpm in shuffled:
        await _set_tempo(link, bpm, _yellow("▶ jump"))
        await asyncio.sleep(JUMP_HOLD_SEC)

    print()

    # ── Phase 2: Return to 111 ─────────────────────────────────────────────────

    print(_bold("  Phase 2 — Return to 111"))
    await _set_tempo(link, 111.0, _yellow("▶ anchor"))
    await asyncio.sleep(JUMP_HOLD_SEC)
    print()

    # ── Phase 3: Sweep 111 → 101 ──────────────────────────────────────────────

    print(_bold("  Phase 3 — Sweep 111 → 101"))
    for bpm in range(SWEEP_FROM, SWEEP_TO - 1, -1):
        await _set_tempo(link, float(bpm), _yellow("▼ sweep"))
        await asyncio.sleep(SWEEP_STEP_SEC)

    print()
    print(_green("  ✓ Sequence complete."))
    print(_gray(f"  Tempo events logged: {len(tempo_log)}"))
    print()

    # ── Assertions ─────────────────────────────────────────────────────────────

    # Final tempo should be at or near 101 BPM
    final = link.tempo
    assert abs(final - 101.0) < 1.0, f"Expected ~101 BPM at end, got {final:.2f}"

    # All jump tempos should have been set
    for t in JUMP_TEMPOS:
        assert any(abs(log_t - t) < 1.0 for log_t in tempo_log), \
            f"BPM {t} never reached (log: {tempo_log})"
