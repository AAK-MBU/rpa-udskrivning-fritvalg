# src/steps/update_patient_info.py

"""Update patient information — status, primary clinic, and primary dentist.

Reads current values from PatientContext (populated during initialization)
and updates them in Solteq Tand if they don't match the expected defaults.
Also determines the discharge document filename based on patient age and
stores it on the context for later steps.
"""

import logging

from mbu_solteqtand_shared_components.application import SolteqTandApp

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import FLAKY_UI

logger = logging.getLogger(__name__)

# Default values that patients should be set to during discharge
DEFAULT_CLINIC_NAME = "Tandplejen Aarhus"
DEFAULT_CLINICIAN_NAME = " Frit valg"


def _get_age_based_values(ctx: PatientContext) -> str:
    """Determine status and document filename based on patient age.

    Args:
        ctx: The patient context with is_under_16 already set.

    Returns:
        str
    """
    if ctx.is_under_16:
        return "Frit valg 0-15 år"
    return "Frit valg fra 16 år"


def update_patient_info(
    runner: AutomationRunner,
    app: SolteqTandApp,
    ctx: PatientContext,
) -> None:
    """Update patient status, primary clinic, and primary dentist.

    Only updates fields that differ from the expected defaults.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        ctx: The patient context with initialization data populated.
    """
    status = _get_age_based_values(ctx)

    # Update status if needed
    if ctx.patient_status != status:
        logger.info(
            "Updating patient status from '%s' to '%s'.",
            ctx.patient_status,
            status,
        )
        runner.step(
            "Update patient status",
            app.change_status,
            status=status,
            config=FLAKY_UI,
        )
    else:
        logger.info("Patient status already '%s', no update needed.", status)

    # Update primary clinic if needed
    if ctx.preferred_clinic_name != DEFAULT_CLINIC_NAME:
        logger.info(
            "Updating primary clinic from '%s' to '%s'.",
            ctx.preferred_clinic_name,
            DEFAULT_CLINIC_NAME,
        )
        runner.step(
            "Change primary clinic",
            app.change_primary_clinic,
            current_primary_clinic=ctx.preferred_clinic_name,
            is_field_locked=ctx.is_preferred_clinic_locked,
            config=FLAKY_UI,
        )
    else:
        logger.info(
            "Primary clinic already '%s', no update needed.", DEFAULT_CLINIC_NAME
        )

    # Update primary dentist if needed
    if ctx.clinician_name != DEFAULT_CLINICIAN_NAME:
        logger.info(
            "Updating primary dentist from '%s' to '%s'.",
            ctx.clinician_name,
            DEFAULT_CLINICIAN_NAME,
        )
        runner.step(
            "Change primary dentist",
            app.change_primary_patient_dentist,
            new_value=DEFAULT_CLINICIAN_NAME,
            config=FLAKY_UI,
        )
    else:
        logger.info(
            "Primary dentist already '%s', no update needed.",
            DEFAULT_CLINICIAN_NAME,
        )

    logger.info("Patient info updated.")
