# src/steps/send_discharge_document.py

"""Send discharge document via DigitalPost — check if sent, send if not.

Looks up the discharge document in the database and checks the
SentToNemSMS flag. If the document exists but hasn't been sent,
it's sent via the Solteq Tand GUI. If it's already sent or doesn't
exist, the step is skipped.

Depends on ctx.discharge_document_filename being set by the
update_patient_info step (step 4).
"""

import datetime
import logging

from dateutil.relativedelta import relativedelta
from mbu_solteqtand_shared_components.application import SolteqTandApp
from mbu_solteqtand_shared_components.database.db_handler import SolteqTandDatabase

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)

DIGITAL_POST_SUBJECT = "Orientering om udskrivning til privat tandlæge"


def _get_unsent_document(db: SolteqTandDatabase, ctx: PatientContext) -> dict | None:
    """Find the discharge document and check if it's been sent.

    Args:
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr and discharge_document_filename.

    Returns:
        The document dict if it exists and hasn't been sent, None otherwise.
    """
    one_month_ago = datetime.datetime.now(datetime.UTC).replace(
        tzinfo=None
    ) - relativedelta(months=1)

    documents = db.get_list_of_documents(
        filters={
            "p.cpr": ctx.patient_cpr,
            "ds.OriginalFilename": f"%{ctx.discharge_document_filename}%",
            "ds.rn": "1",
            "ds.DocumentStoreStatusId": "1",
            "ds.DocumentCreatedDate": (">=", one_month_ago),
        }
    )

    if not documents:
        logger.info("No discharge document found, nothing to send.")
        return None

    if documents[0].get("SentToNemSMS"):
        logger.info("Discharge document already sent to DigitalPost.")
        return None

    return documents[0]


def _send_document(app: SolteqTandApp, ctx: PatientContext) -> None:
    """Send the discharge document via DigitalPost through the GUI.

    Args:
        app: The logged-in SolteqTandApp instance.
        ctx: The patient context with discharge_document_filename set.
    """
    metadata = {
        "documentTitle": ctx.discharge_document_filename + ".pdf",
        "digitalPostSubject": DIGITAL_POST_SUBJECT,
    }

    app.send_discharge_document_digitalpost(metadata=metadata)


def send_discharge_document(
    runner: AutomationRunner,
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> None:
    """Send the discharge document via DigitalPost if not already sent.

    Checks the database for the discharge document. If it exists
    and hasn't been sent to DigitalPost (SentToNemSMS is False),
    sends it via the Solteq Tand GUI. Otherwise skips.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr and
             discharge_document_filename set.
    """
    unsent_document = _get_unsent_document(db, ctx)

    if unsent_document is None:
        return

    logger.info(
        "Sending discharge document '%s' via DigitalPost.",
        ctx.discharge_document_filename,
    )

    runner.step(
        "Send discharge document via DigitalPost",
        _send_document,
        app,
        ctx,
        config=StepConfig(
            max_attempts=3,
            delay=3.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    logger.info("Discharge document sent to DigitalPost successfully.")
