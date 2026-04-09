# tests/test_automation_runner.py

from unittest.mock import MagicMock

import pytest
from mbu_rpa_core.exceptions import BusinessError, ProcessError

from src.core.automation_runner import AutomationRunner, StepError, StepResult
from src.core.step_configs import StepConfig


class TestStepSuccess:
    """Steps that succeed."""

    def test_step_returns_action_result(self, runner):
        action = MagicMock(return_value=42)
        result = runner.step("Get value", action)
        assert result == 42

    def test_step_passes_args_and_kwargs(self, runner):
        action = MagicMock()
        runner.step("Do thing", action, "a", "b", config=None, key="val")
        action.assert_called_once_with("a", "b", key="val")

    def test_successful_step_recorded(self, runner):
        runner.step("Do thing", MagicMock())
        assert len(runner.completed_steps) == 1
        assert runner.completed_steps[0].success is True
        assert runner.completed_steps[0].attempts == 1

    def test_multiple_steps_recorded_in_order(self, runner):
        runner.step("Step 1", MagicMock())
        runner.step("Step 2", MagicMock())
        runner.step("Step 3", MagicMock())
        names = [s.step for s in runner.completed_steps]
        assert names == ["Step 1", "Step 2", "Step 3"]


class TestStepRetry:
    """Steps that fail then succeed."""

    def test_retries_on_retryable_error(self, runner):
        action = MagicMock(side_effect=[TimeoutError("slow"), "ok"])
        config = StepConfig(max_attempts=3, delay=0.01, retryable=(TimeoutError,))

        result = runner.step("Flaky step", action, config=config)

        assert result == "ok"
        assert action.call_count == 2

    def test_retry_records_correct_attempt_count(self, runner):
        action = MagicMock(side_effect=[TimeoutError(), TimeoutError(), "ok"])
        config = StepConfig(max_attempts=3, delay=0.01, retryable=(TimeoutError,))

        runner.step("Flaky step", action, config=config)

        assert runner.completed_steps[0].attempts == 3
        assert runner.completed_steps[0].success is True

    def test_recovery_called_between_retries(self, runner):
        recovery = MagicMock()
        action = MagicMock(side_effect=[TimeoutError(), "ok"])
        config = StepConfig(
            max_attempts=3,
            delay=0.01,
            retryable=(TimeoutError,),
            recovery=recovery,
        )

        runner.step("Recover step", action, config=config)

        recovery.assert_called_once()

    def test_recovery_failure_does_not_prevent_retry(self, runner):
        recovery = MagicMock(side_effect=RuntimeError("recovery broke"))
        action = MagicMock(side_effect=[TimeoutError(), "ok"])
        config = StepConfig(
            max_attempts=3,
            delay=0.01,
            retryable=(TimeoutError,),
            recovery=recovery,
        )

        result = runner.step("Recover step", action, config=config)
        assert result == "ok"


class TestStepFailure:
    """Steps that exhaust all retries."""

    def test_raises_step_error_after_max_attempts(self, runner):
        action = MagicMock(side_effect=TimeoutError("always slow"))
        config = StepConfig(max_attempts=3, delay=0.01, retryable=(TimeoutError,))

        with pytest.raises(StepError, match="failed after 3 attempts"):
            runner.step("Doomed step", action, config=config)

    def test_step_error_is_subclass_of_process_error(self, runner):
        action = MagicMock(side_effect=TimeoutError())
        config = StepConfig(max_attempts=1, delay=0.01, retryable=(TimeoutError,))

        with pytest.raises(ProcessError):
            runner.step("Doomed step", action, config=config)

    def test_non_retryable_error_fails_immediately(self, runner):
        action = MagicMock(side_effect=ValueError("bad input"))
        config = StepConfig(max_attempts=5, delay=0.01, retryable=(TimeoutError,))

        with pytest.raises(StepError, match="non-retryable"):
            runner.step("Bad step", action, config=config)

        # Should not have retried
        assert action.call_count == 1

    def test_failed_step_recorded(self, runner):
        action = MagicMock(side_effect=TimeoutError())
        config = StepConfig(max_attempts=2, delay=0.01, retryable=(TimeoutError,))

        with pytest.raises(StepError):
            runner.step("Fail step", action, config=config)

        assert runner.completed_steps[0].success is False
        assert runner.completed_steps[0].attempts == 2


class TestBusinessError:
    """BusinessError passes through without retry or cleanup."""

    def test_business_error_passes_through(self, runner):
        action = MagicMock(side_effect=BusinessError("Case is closed"))
        config = StepConfig(max_attempts=3, delay=0.01, retryable=(TimeoutError,))

        with pytest.raises(BusinessError, match="Case is closed"):
            runner.step("Validate", action, config=config)

    def test_business_error_not_retried(self, runner):
        action = MagicMock(side_effect=BusinessError("bad data"))
        config = StepConfig(max_attempts=5, delay=0.01, retryable=(TimeoutError,))

        with pytest.raises(BusinessError):
            runner.step("Validate", action, config=config)

        assert action.call_count == 1

    def test_business_error_does_not_trigger_cleanup(self, runner):
        cleanup = MagicMock()
        runner.register_cleanup(cleanup)

        action = MagicMock(side_effect=BusinessError("bad"))

        with pytest.raises(BusinessError):
            runner.step("Validate", action)

        cleanup.assert_not_called()

    def test_business_error_recorded_as_failed(self, runner):
        action = MagicMock(side_effect=BusinessError("bad"))

        with pytest.raises(BusinessError):
            runner.step("Validate", action)

        assert runner.completed_steps[0].success is False


class TestCleanup:
    """Cleanup stack behavior."""

    def test_cleanup_runs_in_reverse_order(self, runner):
        call_order = []
        runner.register_cleanup(lambda: call_order.append("first"))
        runner.register_cleanup(lambda: call_order.append("second"))
        runner.register_cleanup(lambda: call_order.append("third"))

        action = MagicMock(side_effect=ValueError("boom"))

        with pytest.raises(StepError):
            runner.step("Explode", action)

        assert call_order == ["third", "second", "first"]

    def test_cleanup_continues_after_individual_failure(self, runner):
        call_order = []
        runner.register_cleanup(lambda: call_order.append("first"))
        runner.register_cleanup(lambda: (_ for _ in ()).throw(RuntimeError("oops")))
        runner.register_cleanup(lambda: call_order.append("third"))

        action = MagicMock(side_effect=ValueError("boom"))

        with pytest.raises(StepError):
            runner.step("Explode", action)

        # First and third should still run despite second failing
        assert "first" in call_order
        assert "third" in call_order

    def test_cleanup_runs_on_retryable_exhaustion(self, runner):
        cleanup = MagicMock()
        runner.register_cleanup(cleanup)

        action = MagicMock(side_effect=TimeoutError())
        config = StepConfig(max_attempts=2, delay=0.01, retryable=(TimeoutError,))

        with pytest.raises(StepError):
            runner.step("Timeout step", action, config=config)

        cleanup.assert_called_once()


class TestSummary:
    """Summary output."""

    def test_summary_includes_runner_name(self, runner):
        assert "Test-Runner" in runner.summary()

    def test_summary_shows_ok_steps(self, runner):
        runner.step("Do thing", MagicMock())
        summary = runner.summary()
        assert "[OK] Do thing" in summary

    def test_summary_shows_failed_steps(self, runner):
        action = MagicMock(side_effect=ValueError())

        with pytest.raises(StepError):
            runner.step("Bad thing", action)

        assert "[FAILED] Bad thing" in runner.summary()

    def test_summary_shows_retry_count(self, runner):
        action = MagicMock(side_effect=[TimeoutError(), "ok"])
        config = StepConfig(max_attempts=3, delay=0.01, retryable=(TimeoutError,))

        runner.step("Flaky", action, config=config)

        assert "(attempt 2)" in runner.summary()

    def test_summary_shows_total_time(self, runner):
        runner.step("Fast", MagicMock())
        assert "Total:" in runner.summary()
