"""Open patient journal steps — find and open a patient by CPR number.

Opens the patient window in Solteq Tand using the CPR number from
the work item data. Registers cleanup to close the patient window
if later steps fail.
"""

import logging

from mbu_dev_shared_components.solteqtand import SolteqTandApp
from mbu_rpa_core.exceptions import BusinessError

from src.core.automation_runner import AutomationRunner
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)


def validate_cpr(cpr: str) -> str:
    """Validate and clean the CPR number.

    Args:
        cpr: The CPR number, potentially with a hyphen (e.g. "010203-1234").

    Returns:
        Cleaned 10-digit CPR string.

    Raises:
        BusinessError: If the CPR number is invalid.
    """
    cleaned = cpr.replace("-", "")

    if not cleaned.isdigit() or len(cleaned) != 10:
        raise BusinessError(f"Invalid CPR number: {cpr}")

    return cleaned


def open_patient(runner: AutomationRunner, app: SolteqTandApp, cpr: str):
    """Validate the CPR and open the patient in Solteq Tand.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        cpr: The patient's CPR number.

    Raises:
        BusinessError: If the CPR number is invalid.
        ProcessError: If the patient window fails to open after retries.
    """
    cleaned_cpr = validate_cpr(cpr)

    runner.step(
        f"Open patient {cleaned_cpr[:6]}-XXXX",
        app.open_patient,
        cleaned_cpr,
        config=StepConfig(
            max_attempts=3,
            delay=2.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    # Register cleanup so patient window is closed if later steps fail
    runner.register_cleanup(app.close_patient_window)

    logger.info("Patient window opened for CPR %s-XXXX.", cleaned_cpr[:6])
