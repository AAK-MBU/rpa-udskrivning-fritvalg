# src/core/process_item.py

"""Module to handle item processing.

Orchestrates the automation steps for a single work item.
Each phase is a function in processes/steps/ that receives
the runner and app instance.
"""

import logging

from src.core.application_handler import get_app
from src.core.automation_runner import AutomationRunner
from src.steps.solteq_open_patient_journal import open_patient
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

    # Step 1: Open Solteq application.
    app = get_app()
    if app is None:
        app = start_solteq(runner)
        set_app(app)

    # Step 2: Navigate to the journal in Solteq Tand.
    patient_cpr = item_data.get("patient_cpr", "")
    open_patient(runner, app, patient_cpr)

    logger.info(runner.summary())
