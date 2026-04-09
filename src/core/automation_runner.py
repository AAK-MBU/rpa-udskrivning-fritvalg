"""Module for the automation step runner.

The AutomationRunner executes a sequence of automation steps with:
- Per-step retry with exponential backoff
- Recovery actions between retries
- Screenshot capture immediately on failure
- Cleanup stack (runs in reverse on failure)
- BusinessError passthrough
- Step timing and summary logging
"""

import logging
import time
from dataclasses import dataclass, field

from mbu_rpa_core.exceptions import BusinessError, ProcessError

from src.core.screenshot import take_screenshot
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)


class StepError(ProcessError):
    """A ProcessError with an attached screenshot from the moment of failure."""

    def __init__(self, message: str, screenshot: str | None = None):
        super().__init__(message)
        self.screenshot = screenshot


@dataclass
class StepResult:
    """Result of a single automation step."""

    step: str
    attempts: int
    success: bool
    duration: float = 0.0
    screenshot: str | None = None


@dataclass
class AutomationRunner:
    """Runs a sequence of automation steps with retry, recovery, and cleanup.

    Usage:
        runner = AutomationRunner(name="Process-001")
        runner.register_cleanup(app.close)

        runner.step("Open form", app.navigate, "Forms > New", config=FLAKY_UI)
        runner.step("Fill data", app.fill_form, data)
        runner.step("Save", app.click, "button.save", config=SAVE_ACTION)

        logger.info(runner.summary())

    Exception handling order inside step():
        1. BusinessError  → pass through immediately (no retry, no screenshot, no cleanup)
        2. cfg.retryable  → retry with backoff, screenshot on each failure
        3. Exception       → screenshot, cleanup, wrap in StepError
    """

    name: str
    completed_steps: list[StepResult] = field(default_factory=list)
    _cleanup_actions: list[tuple] = field(default_factory=list)

    def register_cleanup(self, action, *args):
        """Register a cleanup action to run on failure.

        Actions run in reverse order (LIFO), like context managers.
        Each action is best-effort — a failing cleanup won't prevent
        subsequent cleanups from running.

        Args:
            action: Callable to execute during cleanup.
            *args: Arguments to pass to the callable.
        """
        self._cleanup_actions.append((action, args))

    def cleanup(self):
        """Run all registered cleanup actions in reverse order."""
        for action, args in reversed(self._cleanup_actions):
            try:
                action(*args)
            except Exception as e:
                logger.warning("Cleanup action failed: %s", e)

    def step(
        self,
        description: str,
        action,
        *args,
        config: StepConfig | None = None,
        **kwargs,
    ):
        """Execute a single automation step with optional retry.

        Args:
            description: Human-readable name for the step (used in logs and summary).
            action: Callable to execute.
            *args: Positional arguments passed to action.
            config: StepConfig controlling retry behavior. Defaults to no retry.
            **kwargs: Keyword arguments passed to action.

        Returns:
            Whatever the action returns.

        Raises:
            BusinessError: Passed through immediately — not an automation failure.
            StepError: Raised after retries are exhausted or on non-retryable errors.
                       Subclass of ProcessError, so existing except ProcessError catches it.
        """
        cfg = config or StepConfig()
        current_delay = cfg.delay

        for attempt in range(1, cfg.max_attempts + 1):
            start = time.time()
            try:
                result = action(*args, **kwargs)
                elapsed = time.time() - start
                self.completed_steps.append(
                    StepResult(description, attempt, success=True, duration=elapsed)
                )
                if attempt > 1:
                    logger.info(
                        "[%s] '%s' succeeded on attempt %d",
                        self.name,
                        description,
                        attempt,
                    )
                return result

            except BusinessError:
                # Business logic issue — not an automation failure.
                # Let it propagate untouched. The outer loop in main.py
                # handles these.
                elapsed = time.time() - start
                self.completed_steps.append(
                    StepResult(description, attempt, success=False, duration=elapsed)
                )
                raise

            except cfg.retryable as e:
                elapsed = time.time() - start

                # Screenshot IMMEDIATELY — before recovery or cleanup
                screenshot = take_screenshot(self.name, description, attempt)

                logger.warning(
                    "[%s] '%s' attempt %d/%d failed: %s",
                    self.name,
                    description,
                    attempt,
                    cfg.max_attempts,
                    e,
                )

                if attempt == cfg.max_attempts:
                    self.completed_steps.append(
                        StepResult(description, attempt, False, elapsed, screenshot)
                    )
                    self.cleanup()
                    raise StepError(
                        f"Step '{description}' failed after "
                        f"{cfg.max_attempts} attempts: {e}",
                        screenshot=screenshot,
                    ) from e

                # Run recovery action before next attempt
                if cfg.recovery:
                    try:
                        cfg.recovery()
                    except Exception as rec_err:
                        logger.warning("Recovery failed: %s", rec_err)

                time.sleep(current_delay)
                current_delay = min(current_delay * cfg.backoff, cfg.max_delay)

            except Exception as e:
                # Non-retryable — fail immediately with screenshot
                elapsed = time.time() - start
                screenshot = take_screenshot(self.name, description, 1)
                self.completed_steps.append(
                    StepResult(description, 1, False, elapsed, screenshot)
                )
                self.cleanup()
                raise StepError(
                    f"Step '{description}' failed (non-retryable): {e}",
                    screenshot=screenshot,
                ) from e

    def summary(self) -> str:
        """Generate a human-readable summary of all steps.

        Returns:
            Multi-line string showing each step's status, timing,
            retry count, and whether a screenshot was captured.

        Example output:
            Runner 'Process-001':
              [OK] Open case lookup [1.2s]
              [OK] Search for case [0.8s]
              [OK] Open case from results (attempt 3) [7.4s] [screenshot saved]
              [OK] Read case data [0.3s]
              [FAILED] Save case (attempt 4) [12.8s] [screenshot saved]
              Total: 22.5s
        """
        lines = [f"Runner '{self.name}':"]
        for s in self.completed_steps:
            status = "OK" if s.success else "FAILED"
            attempts = f" (attempt {s.attempts})" if s.attempts > 1 else ""
            has_screenshot = " [screenshot saved]" if s.screenshot else ""
            lines.append(
                f"  [{status}] {s.step}{attempts} [{s.duration:.1f}s]{has_screenshot}"
            )
        total = sum(s.duration for s in self.completed_steps)
        lines.append(f"  Total: {total:.1f}s")
        return "\n".join(lines)
