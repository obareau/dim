"""
D.I.M — core/condition.py
Pure condition evaluation. No randomness unless explicitly used (50%, 25%...).
All functions are pure: state is immutable (dataclass, return new instances).
"""
from __future__ import annotations

import random
from dataclasses import dataclass


# ── Condition state ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConditionState:
    """
    Tracks pass count and manual trigger for a single condition instance.
    One ConditionState per cue_id or section_id in the cursor's cond_states dict.
    """
    pass_count: int         = 0     # number of times evaluate() has been called
    manual_triggered: bool  = False # True if a manual trigger just fired


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate(condition: str | None, state: ConditionState) -> bool:
    """
    Evaluate a condition string at the current state.
    Does NOT advance state — call next_state() after.

    Condition strings:
        None / "ALWAYS"   → always True
        "NEVER"           → always False
        "MANUAL"          → True only when state.manual_triggered
        "50%"             → probabilistic (die rolled each call)
        "AFTER:4"         → True after state.pass_count >= 4
        "1:2"             → True on pass 0,2,4... (1 out of 2)
        "3:4"             → True on passes 0,1,2 out of every 4
        "2:3"             → True on passes 0,1 out of every 3
    """
    if condition is None or condition.upper() == "ALWAYS":
        return True

    if condition.upper() == "NEVER":
        return False

    if condition.upper() == "MANUAL":
        return state.manual_triggered

    # Probabilistic: "50%", "25%", "75%", "33%"
    if condition.endswith("%"):
        probability = float(condition[:-1]) / 100.0
        return random.random() < probability

    upper = condition.upper()

    # AFTER:N — triggers once pass_count reaches N
    if upper.startswith("AFTER:"):
        n = int(condition[6:])
        return state.pass_count >= n

    # M:N ratio — play M passes out of every N
    if ":" in condition:
        m_str, n_str = condition.split(":", 1)
        m, n = int(m_str), int(n_str)
        if n <= 0:
            return True
        pass_in_cycle = state.pass_count % n
        return pass_in_cycle < m

    # Unknown condition → always True (fail-safe)
    return True


def next_state(state: ConditionState) -> ConditionState:
    """Return a new state after one evaluation (increment pass_count, reset manual)."""
    return ConditionState(
        pass_count=state.pass_count + 1,
        manual_triggered=False,
    )


def trigger_manual(state: ConditionState) -> ConditionState:
    """Return a new state with manual_triggered=True."""
    return ConditionState(
        pass_count=state.pass_count,
        manual_triggered=True,
    )


def reset_state() -> ConditionState:
    """Return a fresh condition state (0 passes, no manual)."""
    return ConditionState()
