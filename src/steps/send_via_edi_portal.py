# src/steps/send_via_edi_portal.py

"""Send journal and images through the EDI portal.

Opens the EDI portal in Solteq Tand, runs the full send pipeline
(navigate → select receiver → add content → upload files → send),
downloads the receipt PDF, and closes the portal.

The EDI portal handler from the old framework (edi_portal_handler)
is reused as-is — it contains the complex multi-step GUI pipeline
that navigates through the portal's pages. This step wraps it with
proper open/close handling, runner integration, and context mapping.

The receipt PDF path is stored on ctx.edi_receipt_path for use by
the next step (upload receipt to Solteq).
"""

import json
import logging
import time

import pyodbc
from mbu_solteqtand_shared_components.application import SolteqTandApp

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import StepConfig
from src.steps.edi.edi_portal_handler import EdiContext, edi_portal_handler

logger = logging.getLogger(__name__)


def _get_edi_portal_content(db_conn: str) -> dict:
    """Fetch the EDI portal content configuration from the database.

    Args:
        db_conn: RPA database connection string.

    Returns:
        Parsed JSON dictionary with EDI portal content configuration.

    Raises:
        RuntimeError: If the constant is not found in the database.
    """
    query = """
        SELECT [name], [value]
        FROM   [RPA].[rpa].[Constants]
        WHERE  [name] = ?
    """

    with pyodbc.connect(db_conn) as conn:
        row = conn.cursor().execute(query, "udskrivning_edi_portal_content").fetchone()

    if row is None:
        raise RuntimeError(
            "Constant 'udskrivning_edi_portal_content' not found in the database."
        )

    value = row.value
    return json.loads(value) if isinstance(value, str) else value


def _build_subject(ctx: PatientContext, value_data: dict) -> str:
    """Build the EDI portal subject line.

    Adds clinic-specific suffix for Hasle Torv and Brobjergparken,
    and truncates to 66 characters (EDI portal limitation).

    Args:
        ctx: The patient context with extern_clinic_data.
        value_data: Parsed EDI portal content configuration.

    Returns:
        The subject string, max 66 characters.
    """
    subject = value_data["edi_portal_content"]["subject"]

    if not subject:
        raise ValueError("EDI portal subject is required but empty.")

    contractor_id = ctx.contractor_id

    if contractor_id == "477052":
        subject = subject + " på Tandklinikken Hasle Torv"
    elif contractor_id == "470678":
        subject = subject + " på Tandklinikken Brobjergparken"

    return subject[:66]


def _run_edi_pipeline(
    app: SolteqTandApp,
    ctx: PatientContext,
    rpa_db_conn: str,
    runner: AutomationRunner,
) -> str | None:
    """Open EDI portal, run the send pipeline, close portal.

    This is the inner function wrapped by runner.step().

    Args:
        app: The logged-in SolteqTandApp instance.
        ctx: The patient context with all required data.
        rpa_db_conn: RPA database connection string.

    Returns:
        Path to the receipt PDF, or None if the pipeline indicates
        the message was already sent.
    """
    # Get EDI portal content configuration
    value_data = _get_edi_portal_content(rpa_db_conn)
    subject = _build_subject(ctx, value_data)

    logger.info("EDI portal subject: %s", subject)

    # Build the queue_element dict that edi_portal_handler expects
    queue_element = {
        "patient_cpr": ctx.patient_cpr,
        "patient_name": ctx.patient_name,
    }

    # Build the EdiContext for the old handler
    edi_ctx = EdiContext(
        extern_clinic_data=ctx.extern_clinic_data,
        queue_element=queue_element,
        path_to_files_for_upload=ctx.edi_portal_file_paths,
        journal_note=ctx.journal_note_text,
    )

    # Open portal
    app.open_edi_portal()
    runner.register_cleanup(app.close_edi_portal)
    time.sleep(5)

    try:
        receipt_pdf = edi_portal_handler(edi_ctx)
        return receipt_pdf
    finally:
        app.close_edi_portal()
        runner.remove_cleanup(app.close_edi_portal)


def send_via_edi_portal(
    runner: AutomationRunner,
    app: SolteqTandApp,
    rpa_db_conn: str,
    ctx: PatientContext,
) -> None:
    """Send journal and images through the EDI portal.

    Opens the EDI portal, runs the full send pipeline (navigate,
    select receiver, add content, upload files, send), downloads
    the receipt PDF, and closes the portal.

    The receipt path is stored on ctx.edi_receipt_path for the
    next step (upload receipt to Solteq).

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        rpa_db_conn: RPA database connection string.
        ctx: The patient context with extern_clinic_data,
             edi_portal_file_paths, and journal_note_text set.

    """
    receipt_path = runner.step(
        "Send documents via EDI portal",
        _run_edi_pipeline,
        app,
        ctx,
        rpa_db_conn,
        runner,
        config=StepConfig(
            max_attempts=2,
            delay=5.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    ctx.edi_receipt_path = receipt_path

    if receipt_path:
        logger.info("EDI portal receipt saved: %s", receipt_path)
    else:
        logger.info(
            "EDI portal pipeline completed (message may have been sent previously)."
        )
