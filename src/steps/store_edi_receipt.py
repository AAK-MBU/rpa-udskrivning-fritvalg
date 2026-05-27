# src/steps/store_edi_receipt.py

"""Store EDI portal receipt in Solteq — check if exists, upload if not.

After the EDI portal sends the documents, a receipt PDF is downloaded
and renamed (by the edi_portal_handler pipeline). This step checks
if the receipt has already been uploaded to Solteq Tand's document
store. If not, it uploads it via the GUI.

Reads ctx.edi_receipt_path (set by step 12) and ctx.patient_name
for the document filename pattern.
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


def _receipt_already_uploaded(db: SolteqTandDatabase, ctx: PatientContext) -> bool:
    """Check if the EDI receipt has already been uploaded within the last month.

    Args:
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr and patient_name.

    Returns:
        True if the receipt document already exists in Solteq.
    """
    one_month_ago = datetime.datetime.now() - relativedelta(months=1)

    documents = db.get_list_of_documents(
        filters={
            "p.cpr": ctx.patient_cpr,
            "ds.OriginalFilename": f"%EDI Portal - {ctx.patient_name}%",
            "ds.rn": "1",
            "ds.DocumentStoreStatusId": "1",
            "ds.DocumentCreatedDate": (">=", one_month_ago),
        }
    )

    logger.info("Found %d existing EDI receipt document(s).", len(documents))
    return bool(documents)


def store_edi_receipt(
    runner: AutomationRunner,
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> None:
    """Upload the EDI receipt PDF to Solteq if not already uploaded.

    Checks the database for an existing receipt document. If none
    is found, uploads the receipt PDF via the Solteq Tand GUI.

    If ctx.edi_receipt_path is None (no receipt was generated,
    e.g. because the message was already sent), the step is skipped.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        db: The SolteqTandDatabase instance.
        ctx: The patient context with edi_receipt_path, patient_cpr,
             and patient_name set.
    """
    if not ctx.edi_receipt_path:
        logger.info("No EDI receipt path set, skipping upload.")
        return

    if _receipt_already_uploaded(db, ctx):
        logger.info("EDI receipt already uploaded to Solteq, skipping.")
        return

    logger.info("Uploading EDI receipt to Solteq: %s", ctx.edi_receipt_path)

    runner.step(
        "Upload EDI receipt to Solteq",
        app.create_document,
        document_full_path=ctx.edi_receipt_path,
        config=StepConfig(
            max_attempts=3,
            delay=3.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    logger.info("EDI receipt uploaded successfully.")
