# src/steps/create_medical_record.py

"""Create digital journal (medical record) — check if it exists, create if not.

Checks the database for an existing 'Journaludskrift' document
(partial copy of the printed journal) created within the last month.
If none is found, creates it through the Solteq Tand GUI using
create_digital_printet_journal.

This is the patient's dental journal that gets included in the
EDI portal upload.
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

DOCUMENT_TYPE = "Journaludskrift"
DOCUMENT_DESCRIPTION_PATTERN = "%Printet journal%(delvis kopi)%"


def _document_exists(db: SolteqTandDatabase, ctx: PatientContext) -> bool:
    """Check if a medical record document was already created within the last month.

    Args:
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr.

    Returns:
        True if the document already exists.
    """
    # one_month_ago = datetime.datetime.now() - relativedelta(months=1)
    one_month_ago = datetime.datetime.now(datetime.UTC).replace(
        tzinfo=None
    ) - relativedelta(months=1)

    documents = db.get_list_of_documents(
        filters={
            "p.cpr": ctx.patient_cpr,
            "ds.DocumentDescription": DOCUMENT_DESCRIPTION_PATTERN,
            "ds.DocumentType": DOCUMENT_TYPE,
            "ds.rn": "1",
            "ds.DocumentStoreStatusId": "1",
            "ds.DocumentCreatedDate": (">=", one_month_ago),
        }
    )

    logger.info("Found %d existing medical record document(s).", len(documents))
    return bool(documents)


def create_medical_record(
    runner: AutomationRunner,
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> None:
    """Create the digital journal if it doesn't already exist.

    Checks the database for an existing medical record document
    created within the last month. If none is found, creates it
    via the Solteq Tand GUI.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr.
    """
    if _document_exists(db, ctx):
        logger.info("Medical record document already exists, skipping.")
        return

    logger.info("Medical record document not found, creating it.")

    runner.step(
        "Create digital journal",
        app.create_digital_printet_journal,
        config=StepConfig(
            max_attempts=3,
            delay=3.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    logger.info("Medical record document created successfully.")
