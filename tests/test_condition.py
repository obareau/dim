"""Tests for core/condition.py"""
import pytest
from core.condition import ConditionState, evaluate, next_state, trigger_manual, reset_state


class TestEvaluateAlways:
    def test_none(self):
        assert evaluate(None, ConditionState()) is True

    def test_always(self):
        assert evaluate("ALWAYS", ConditionState()) is True

    def test_never(self):
        assert evaluate("NEVER", ConditionState()) is False


class TestEvaluateManual:
    def test_not_triggered(self):
        assert evaluate("MANUAL", ConditionState(manual_triggered=False)) is False

    def test_triggered(self):
        assert evaluate("MANUAL", ConditionState(manual_triggered=True)) is True


class TestEvaluateProbabilistic:
    def test_100_percent(self):
        # 100% → always True
        for _ in range(20):
            assert evaluate("100%", ConditionState()) is True

    def test_0_percent(self):
        # 0% → always False
        for _ in range(20):
            assert evaluate("0%", ConditionState()) is False

    def test_50_percent_distribution(self):
        # 50% → roughly half (test distribution over many trials)
        results = [evaluate("50%", ConditionState()) for _ in range(1000)]
        true_ratio = sum(results) / len(results)
        assert 0.35 < true_ratio < 0.65, f"Expected ~50%, got {true_ratio:.0%}"


class TestEvaluateAfter:
    def test_after_4_not_yet(self):
        state = ConditionState(pass_count=3)
        assert evaluate("AFTER:4", state) is False

    def test_after_4_exact(self):
        state = ConditionState(pass_count=4)
        assert evaluate("AFTER:4", state) is True

    def test_after_4_beyond(self):
        state = ConditionState(pass_count=10)
        assert evaluate("AFTER:4", state) is True


class TestEvaluateNthPass:
    def test_1_out_of_2(self):
        """1:2 → True on passes 0, 2, 4... (even passes)"""
        assert evaluate("1:2", ConditionState(pass_count=0)) is True   # pass 0: 0%2==0 < 1 → True
        assert evaluate("1:2", ConditionState(pass_count=1)) is False  # pass 1: 1%2==1 < 1 → False
        assert evaluate("1:2", ConditionState(pass_count=2)) is True   # pass 2: 2%2==0 < 1 → True
        assert evaluate("1:2", ConditionState(pass_count=3)) is False

    def test_3_out_of_4(self):
        """3:4 → True on passes 0,1,2 of every 4"""
        assert evaluate("3:4", ConditionState(pass_count=0)) is True
        assert evaluate("3:4", ConditionState(pass_count=1)) is True
        assert evaluate("3:4", ConditionState(pass_count=2)) is True
        assert evaluate("3:4", ConditionState(pass_count=3)) is False
        assert evaluate("3:4", ConditionState(pass_count=4)) is True  # wraps

    def test_1_out_of_4(self):
        """1:4 → True only on passes 0, 4, 8..."""
        assert evaluate("1:4", ConditionState(pass_count=0)) is True
        assert evaluate("1:4", ConditionState(pass_count=1)) is False
        assert evaluate("1:4", ConditionState(pass_count=2)) is False
        assert evaluate("1:4", ConditionState(pass_count=3)) is False
        assert evaluate("1:4", ConditionState(pass_count=4)) is True


class TestNextState:
    def test_increments_pass_count(self):
        s0 = ConditionState()
        s1 = next_state(s0)
        assert s1.pass_count == 1
        assert s1.manual_triggered is False

    def test_resets_manual(self):
        s = ConditionState(manual_triggered=True)
        s2 = next_state(s)
        assert s2.manual_triggered is False

    def test_immutable(self):
        s = ConditionState(pass_count=5)
        _ = next_state(s)
        assert s.pass_count == 5  # original unchanged


class TestTriggerManual:
    def test_sets_flag(self):
        s = ConditionState()
        s2 = trigger_manual(s)
        assert s2.manual_triggered is True

    def test_preserves_pass_count(self):
        s = ConditionState(pass_count=7)
        s2 = trigger_manual(s)
        assert s2.pass_count == 7


class TestNthPassSequence:
    def test_1_out_of_2_sequence(self):
        """Simulate 6 passes of 1:2 condition."""
        state = reset_state()
        results = []
        for _ in range(6):
            results.append(evaluate("1:2", state))
            state = next_state(state)
        assert results == [True, False, True, False, True, False]
