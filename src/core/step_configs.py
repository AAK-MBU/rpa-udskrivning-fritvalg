# src/core/step_configs.py

"""Module for step configuration and reusable retry presets."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class StepConfig:
    """Configuration for a single automation step's retry behavior.

    Attributes:
        max_attempts: Total number of tries before giving up.
        delay: Initial wait between attempts in seconds.
        backoff: Multiply delay by this factor after each failure.
        max_delay: Cap on the delay so backoff doesn't grow forever.
        retryable: Tuple of exception types worth retrying.
                   Anything else propagates immediately.
        recovery: Optional callable to run between retries,
                  e.g. dismiss a dialog or navigate to a known state.
    """

    max_attempts: int = 1
    delay: float = 1.0
    backoff: float = 2.0
    max_delay: float = 30.0
    retryable: tuple = (TimeoutError,)
    recovery: Callable | None = None


# ----------------------
# Reusable presets
# ----------------------

# No retry — fail immediately on any error.
NO_RETRY = StepConfig()

# Flaky UI elements that sometimes need a moment to appear.
FLAKY_UI = StepConfig(
    max_attempts=3,
    delay=1.0,
    retryable=(TimeoutError,),
)

# Save/submit actions that can timeout under load.
SAVE_ACTION = StepConfig(
    max_attempts=4,
    delay=2.0,
    backoff=2.0,
    max_delay=15.0,
    retryable=(TimeoutError,),
)

# Network-dependent operations (file downloads, API calls).
NETWORK_CALL = StepConfig(
    max_attempts=5,
    delay=2.0,
    backoff=3.0,
    max_delay=30.0,
    retryable=(TimeoutError, ConnectionError),
)
