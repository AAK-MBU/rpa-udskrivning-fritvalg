# src/steps/initialization_checks.py

"""Initialization checks — validate business rules and collect data.

Runs all pre-process checks against the database and populates
the PatientContext with the data needed by later steps. Each check
raises BusinessError if a business rule is violated.

These are database checks, not GUI automation, so they don't need
retry configs — they either work or raise.
"""

import logging

from mbu_dev_shared_components.solteqtand import SolteqTandApp, SolteqTandDatabase
from mbu_rpa_core.exceptions import BusinessError

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)


def _get_error_message(db_conn: str, code: str, default: str) -> str:
    """Look up a business error message from the database.

    Args:
        db_conn: RPA database connection string.
        code: The exception code to look up (e.g. "1A", "1B").
        default: Fallback message if the lookup fails.
    """
    try:
        from src.helpers.db_utils import get_exceptions

        exceptions = get_exceptions(db_conn)
        return next(
            (d["message_text"] for d in exceptions if d["exception_code"] == code),
            default,
        )
    except Exception as e:
        logger.warning("Failed to look up error message for code %s: %s", code, e)
        return default


def check_primary_clinic(
    db: SolteqTandDatabase, ctx: PatientContext, rpa_db_conn: str
) -> list:
    """Check if primary clinic is set and return the data.

    Raises:
        BusinessError: If no primary clinic is found.
    """
    result = db.get_list_of_primary_dental_clinics(filters={"p.cpr": ctx.patient_cpr})
    if not result:
        msg = _get_error_message(rpa_db_conn, "1A", "Primary clinic is not set.")
        raise BusinessError(msg)

    logger.info("Primary clinic is set.")
    return result


def check_extern_clinic(
    db: SolteqTandDatabase, ctx: PatientContext, rpa_db_conn: str
) -> list:
    """Check extern dentist data: exists, has contractor ID, has phone number.

    Raises:
        BusinessError: If any required extern clinic field is missing.
    """
    result = db.get_list_of_extern_dentist(filters={"p.cpr": ctx.patient_cpr})
    if not result:
        msg = _get_error_message(rpa_db_conn, "1B", "Extern dentist is not set.")
        raise BusinessError(msg)

    if not result[0].get("contractorId"):
        msg = _get_error_message(rpa_db_conn, "1C", "Contractor ID is not set.")
        raise BusinessError(msg)

    if not result[0].get("phoneNumber"):
        msg = _get_error_message(rpa_db_conn, "1E", "Phone number is not set.")
        raise BusinessError(msg)

    logger.info("Extern clinic data is valid.")
    return result


def check_extern_clinic_deal(
    db: SolteqTandDatabase, contractor_id: str, rpa_db_conn: str
) -> None:
    """Check if extern clinic has a deal with Aarhus Kommune.

    Raises:
        BusinessError: If no deal is found.
    """
    result = db.get_list_of_clinics(
        filters={"type": "3", "contractorId": contractor_id}
    )
    if not result:
        msg = _get_error_message(rpa_db_conn, "1D", "No deal with Aarhus Kommune.")
        raise BusinessError(msg)

    logger.info("Extern clinic has a deal with Aarhus Kommune.")


def check_administrative_note(
    db: SolteqTandDatabase, ctx: PatientContext, rpa_db_conn: str
) -> list:
    """Check if administrative note exists (required when tandplejeplan is True).

    Raises:
        BusinessError: If tandplejeplan is True but no note is found.
    """
    result = db.get_list_of_journal_notes(
        filters={
            "p.cpr": ctx.patient_cpr,
            "dn.Beskrivelse": "%Besked til privat tandlæge - Frit valg%",
        },
        order_by="ds.Dokumenteret",
        order_direction="DESC",
    )
    if not result and ctx.tandplejeplan:
        msg = _get_error_message(rpa_db_conn, "1F", "No administrative note found.")
        raise BusinessError(msg)

    logger.info("Administrative note check passed.")
    return result


def check_other_documents(
    db: SolteqTandDatabase, ctx: PatientContext, rpa_db_conn: str
) -> None:
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
        msg = _get_error_message(rpa_db_conn, "1I", "No other documents found.")
        raise BusinessError(msg)

    logger.info("Other documents check passed.")


def check_contractor_in_edi_portal(
    runner: AutomationRunner, app: SolteqTandApp, ctx: PatientContext, rpa_db_conn: str
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

        if result["rowCount"] == 0:
            msg = _get_error_message(
                rpa_db_conn, "1G", "Contractor not found in EDI portal."
            )
            raise BusinessError(msg)

        if result["isPhoneNumberMatch"] is False:
            msg = _get_error_message(rpa_db_conn, "1H", "Phone number does not match.")
            raise BusinessError(msg)

        logger.info("Contractor ID verified in EDI portal.")

    finally:
        runner.step("Close EDI portal", app.close_edi_portal)


def run_initialization_checks(
    runner: AutomationRunner,
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    item_data: dict,
    rpa_db_conn: str,
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
        rpa_db_conn: RPA database connection string for error message lookups.

    Returns:
        A fully populated PatientContext.

    Raises:
        BusinessError: If any business rule check fails.
    """
    ctx = PatientContext.from_item_data(item_data)

    logger.info("Running initialization checks for %s...", ctx.request_number)

    # Database checks — no GUI needed
    ctx.primary_clinic_data = check_primary_clinic(db, ctx, rpa_db_conn)
    ctx.extern_clinic_data = check_extern_clinic(db, ctx, rpa_db_conn)
    check_extern_clinic_deal(db, ctx.contractor_id, rpa_db_conn)
    ctx.administrative_note = check_administrative_note(db, ctx, rpa_db_conn)
    check_other_documents(db, ctx, rpa_db_conn)

    # GUI check — needs the runner for retry/screenshot
    check_contractor_in_edi_portal(runner, app, ctx, rpa_db_conn)

    logger.info("All initialization checks passed.")
    return ctx
