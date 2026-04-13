# src/core/process_item.py

"""Module to handle item processing.

Orchestrates the automation steps for a single work item.
Each phase is a function in processes/steps/ that receives
the runner and app instance.
"""

import logging
import os

from mbu_dev_shared_components.solteqtand import SolteqTandDatabase

from src.core.application_handler import get_app, set_app
from src.core.automation_runner import AutomationRunner
from src.steps.initialization_checks import run_initialization_checks
from src.steps.solteq_open_patient_journal import open_patient, test_break_stuff
from src.steps.solteq_start_app import start_solteq

logger = logging.getLogger(__name__)


def process_item(item_data: dict, item_reference: str):
    """Process a single work item through all automation phases.

    Args:
        item_data: Dictionary containing the item's data payload.
        item_reference: Unique reference string for the item.

    Raises:
        BusinessError: If business validation fails (item goes to pending_user).
        ProcessError: If an automation step fails after retries (item is failed).
    """
    runner = AutomationRunner(name=f"Process-{item_reference}")

    # Step 1: Open Solteq application and log in.
    app = get_app()
    if app is None:
        app = start_solteq(runner)
        set_app(app)

    # Step 2: Navigate to the patients journal in Solteq Tand.
    patient_cpr = item_data.get("cpr", "")
    open_patient(runner, app, patient_cpr)

    # Step 3: Initialization checks -> produces PatientContext
    solteq_db_obj = SolteqTandDatabase(os.getenv("DBCONNECTIONSTRINGSOLTEQTAND", ""))
    rpa_db_conn = os.getenv("DBCONNECTIONSTRINGDEV", "")

    ctx = run_initialization_checks(runner, app, solteq_db_obj, item_data, rpa_db_conn)

    # Step 4: Check if patient is under 16 years.

    # Step 5: Update patient journal data.

    # Step 6: Check if patient has a specific event, if so, process it.

    # Step 7: Create booking reminder; Check if exists, if not, create it.

    # Step 8: Create discharge document; Check if exists, if not, create it.

    # Step 9: Send discharge document; Check if has been send, if not, send it.

    # Step 10: Get images from Romexis and create zip file.

    # Step 11: Create digital journal; Check if exists, if not, create it.

    # Step 12: Get all other relevant documents

    # Step 13: Send journal and images trough EDI Portal

    # Step 14: Download receipt PDF from EDI Portal and store in Solteq

    # Step 15: Create administrativ note

    logger.info("administrativt notat: %s", ctx.administrative_note)

    logger.info(runner.summary())
