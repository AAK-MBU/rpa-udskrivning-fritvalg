# src/steps/create_discharge_document.py

"""Create discharge document — check if it exists, create if not.

Creates a discharge document from a template based on the patient's age:
- Under 16: 'Følgebrev - Frit valg 0-15 år'
- 16 or older: 'Følgebrev - Frit valg fra 16 år'

The document filename is read from ctx.discharge_document_filename,
which was set during the update_patient_info step. The template name
is derived from the same age check.

Checks the database for an existing document created within the last
month. If found, the step is skipped. If not, creates the document
via the Solteq Tand GUI using create_document_from_template.
"""

import datetime
import logging
import os

from dateutil.relativedelta import relativedelta
from mbu_solteqtand_shared_components.application import SolteqTandApp
from mbu_solteqtand_shared_components.database.db_handler import SolteqTandDatabase

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)

TMP_FOLDER = r"C:\tmp\tmt"


def _get_template_name(ctx: PatientContext) -> str:
    """Get the document template name based on patient age.

    Args:
        ctx: The patient context with is_under_16 set.

    Returns:
        The template name string.
    """
    if ctx.is_under_16:
        return "Følgebrev - Frit valg 0-15 år"
    return "Følgebrev - Frit valg fra 16 år"


def _document_exists(db: SolteqTandDatabase, ctx: PatientContext) -> bool:
    """Check if a discharge document was already created within the last month.

    Args:
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr and discharge_document_filename.

    Returns:
        True if the document already exists.
    """
    one_month_ago = datetime.datetime.now() - relativedelta(months=1)

    documents = db.get_list_of_documents(
        filters={
            "p.cpr": ctx.patient_cpr,
            "ds.OriginalFilename": f"%{ctx.discharge_document_filename}%",
            "ds.rn": "1",
            "ds.DocumentStoreStatusId": "1",
            "ds.DocumentCreatedDate": (">=", one_month_ago),
        }
    )

    logger.info("Found %d existing discharge document(s).", len(documents))
    return bool(documents)


def _create_document(app: SolteqTandApp, ctx: PatientContext) -> None:
    """Create the discharge document from a template via the GUI.

    Creates the tmp folder for the patient if it doesn't exist,
    then calls the Solteq Tand GUI to generate the document.

    Args:
        app: The logged-in SolteqTandApp instance.
        ctx: The patient context with patient_cpr, is_under_16,
             and discharge_document_filename set.
    """
    folder_path = os.path.join(TMP_FOLDER, ctx.patient_cpr)
    os.makedirs(folder_path, exist_ok=True)

    template_name = _get_template_name(ctx)

    metadata = {
        "templateName": template_name,
        "destinationPath": folder_path,
        "dischargeDocumentFilename": ctx.discharge_document_filename,
    }

    app.create_document_from_template(metadata=metadata)


def create_discharge_document(
    runner: AutomationRunner,
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> None:
    """Create the discharge document if it doesn't already exist.

    Checks the database for an existing document created within
    the last month. If none is found, creates it from the
    age-appropriate template via the Solteq Tand GUI.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr, is_under_16,
             and discharge_document_filename set.
    """
    if _document_exists(db, ctx):
        logger.info("Discharge document already exists, skipping.")
        return

    logger.info(
        "Creating discharge document '%s' with template '%s'.",
        ctx.discharge_document_filename,
        _get_template_name(ctx),
    )

    runner.step(
        "Create discharge document",
        _create_document,
        app,
        ctx,
        config=StepConfig(
            max_attempts=3,
            delay=3.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    logger.info("Discharge document created successfully.")
