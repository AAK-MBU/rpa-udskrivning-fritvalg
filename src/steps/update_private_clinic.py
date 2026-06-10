# src/steps/update_private_clinic.py

"""Update the patient's private clinic in Solteq Tand.

Uses the patient's clinic name from the patient context and updates the
private clinic through the Solteq Tand GUI. The GUI action is wrapped in
runner.step() for retry and screenshot support.
"""

import logging

from mbu_solteqtand_shared_components.application import SolteqTandApp

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)


def check_if_exists():
    """ """
    pass


def update_private_clinic(
    runner: AutomationRunner,
    app: SolteqTandApp,
    ctx: PatientContext,
) -> None:
    """Update the patient's private clinic in Solteq Tand.

    Changes the patient's private clinic through the Solteq Tand GUI,
    retrying the step if supported transient errors occur.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        ctx: The patient context containing the clinic name.
    """
    logger.info("Update private clinic with %s.", ctx.clinic_name)

    runner.step(
        "Update private clinic",
        app.change_private_clinic,
        config=StepConfig(
            max_attempts=3,
            delay=2.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    logger.info("Clinic updated successfully.")
