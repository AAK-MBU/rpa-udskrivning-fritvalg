# src/steps/initialization_checks.py

"""Initialization checks — validate business rules and collect data.

Runs all pre-process checks against the database and populates
the PatientContext with the data needed by later steps. Each check
raises BusinessError if a business rule is violated.

These are database checks, not GUI automation, so they don't need
retry configs — they either work or raise.
"""

import logging

from mbu_rpa_core.exceptions import BusinessError
from mbu_solteqtand_shared_components.application import SolteqTandApp
from mbu_solteqtand_shared_components.database.db_handler import SolteqTandDatabase

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)


def check_primary_clinic(db: SolteqTandDatabase, ctx: PatientContext) -> list:
    """Check if primary clinic is set and return the data.

    Raises:
        BusinessError: If no primary clinic is found.
    """
    result = db.get_list_of_primary_dental_clinics(filters={"p.cpr": ctx.patient_cpr})

    if not result:
        logger.warning("No primary dental clinic found.")
        raise BusinessError("Fandt ingen stamklink.")

    logger.info("Primary clinic is set.")
    return result


def check_extern_clinic(db: SolteqTandDatabase, ctx: PatientContext) -> list:
    """Check extern dentist data: exists, has contractor ID, has phone number.

    Raises:
        BusinessError: If any required extern clinic field is missing.
    """
    result = db.get_list_of_extern_dentist(filters={"p.cpr": ctx.patient_cpr})
    if not result:
        logger.warning("No external dentist found.")
        raise BusinessError("Fandt ingen privatklink.")

    if not result[0].get("contractorId"):
        logger.warning("No contractor ID for external dentist.")
        raise BusinessError("Fandt ingen ydernummer.")

    if not result[0].get("phoneNumber"):
        logger.warning("No phone number for external dentist.")
        raise BusinessError("Telefonnummer er ikke sat for den private tandlæge")

    logger.info("Extern clinic data is valid.")
    return result


def check_extern_clinic_deal(db: SolteqTandDatabase, contractor_id: str) -> None:
    """Check if extern clinic has a contract with Aarhus Kommune.

    Raises:
        BusinessError: If no deal is found.
    """
    result = db.get_list_of_clinics(
        filters={"type": "3", "contractorId": contractor_id}
    )

    if not result:
        logger.warning("Clinic has no contract with Aarhus Kommune.")
        raise BusinessError("Klinikken har ikke en aftale.")

    logger.info("Extern clinic has a contract with Aarhus Kommune.")


def check_administrative_note(db: SolteqTandDatabase, ctx: PatientContext) -> list:
    """Check if administrative note exists (required when tandplejeplan is True).

    Raises:
        BusinessError: If tandplejeplan is True but no note is found.
    """
    result = db.get_list_of_journal_notes(
        filters={
            "p.cpr": ctx.patient_cpr,
            "dn.Beskrivelse": "%Besked til privat tandklinik - Frit valg%",
        },
        order_by="ds.Dokumenteret",
        order_direction="DESC",
    )

    if not result and ctx.tandplejeplan:
        logger.warning("No administrative note found.")
        raise BusinessError("Fandt ingen journalnotat")

    logger.info("Administrative note check passed.")

    return result


def check_other_documents(db: SolteqTandDatabase, ctx: PatientContext) -> None:
    """Check if other documents exist (required when regionstilsagn is True).

    Raises:
        BusinessError: If regionstilsagn is True but no documents found.
    """
    result = db.get_list_of_documents(
        filters={
            "p.cpr": ctx.patient_cpr,
            "ds.rn": "1",
            "ds.DocumentStoreStatusId": "1",
            "ds.DocumentType": "Udskrivning - Frit valg!$#",
        }
    )

    if not result and ctx.regionstilsagn:
        logger.warning("No other documents found.")
        raise BusinessError(
            "Der er sat kryds ved regionstilagn i formularen, men robotten fandt ingen yderligere dokumenter på sagen."
        )

    logger.info("Other documents check passed.")


def check_contractor_in_edi_portal(
    runner: AutomationRunner,
    app: SolteqTandApp,
    ctx: PatientContext,
) -> None:
    """Open EDI portal and verify the contractor ID is valid.

    This is the only check that uses the GUI — it opens the EDI portal,
    checks the contractor, then closes it. Uses the runner for retry.

    Raises:
        BusinessError: If contractor not found or phone number doesn't match.
    """
    runner.step(
        "Open EDI portal for contractor check",
        app.open_edi_portal,
        config=StepConfig(
            max_attempts=2,
            delay=3.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )
    runner.register_cleanup(app.close_edi_portal)

    try:
        result = runner.step(
            "Check contractor ID in EDI portal",
            app.edi_portal_check_contractor_id,
            ctx.extern_clinic_data,
        )

        if result is None:
            raise RuntimeError("EDI portal contractor check returned None.")

        if result["rowCount"] == 0:
            logger.warning("Contractor not found in EDI portal.")
            raise BusinessError("Fandt ikke ydernummeret i EDI Portalen")

        if result["isPhoneNumberMatch"] is False:
            logger.warning("Phone number does not match.")
            raise BusinessError(
                "Den eksterne tandlæges telefonnummer fra Solteq Tand matchede ikke telefonnummeret i EDI Portalen"
            )

        logger.info("Contractor ID verified in EDI portal.")

    except (BusinessError, RuntimeError):
        raise
    except Exception as e:
        logger.error("Unexpected error during EDI portal contractor check: %s", e)
        raise RuntimeError("EDI portal contractor check failed") from e
    finally:
        runner.step("Close EDI portal", app.close_edi_portal)
        runner.remove_cleanup(app.close_edi_portal)


def run_initialization_checks(
    runner: AutomationRunner,
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    item_data: dict,
) -> PatientContext:
    """Run all initialization checks and return a populated PatientContext.

    This is the main entry point. It creates the context from the item data,
    runs every check, populates the context with the collected data, and
    returns it for use by subsequent steps.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        db: The SolteqTandDatabase instance.
        item_data: Raw dictionary from the work queue item.

    Returns:
        A fully populated PatientContext.

    Raises:
        BusinessError: If any business rule check fails.
    """
    ctx = PatientContext.from_item_data(item_data)

    logger.info("Running initialization checks...")

    ctx.primary_clinic_data = check_primary_clinic(db, ctx)

    if ctx.primary_clinic_data is None:
        raise ValueError("Primary clinic data is missing.")

    ctx.extern_clinic_data = check_extern_clinic(db, ctx)

    if ctx.extern_clinic_data is None:
        raise ValueError("Extern clinic data is missing.")

    if ctx.contractor_id is None:
        raise ValueError("Contractor ID is missing.")

    check_extern_clinic_deal(db, ctx.contractor_id)

    ctx.administrative_note = check_administrative_note(db, ctx)

    # check_other_documents(db, ctx)

    # GUI check — needs the runner for retry/screenshot
    check_contractor_in_edi_portal(runner, app, ctx)

    logger.info("All initialization checks passed.")
    return ctx
