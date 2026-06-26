# src/core/process_item.py

"""Module to handle item processing.

Orchestrates the automation steps for a single work item.
Each phase is a function in processes/steps/ that receives
the runner and app instance.
"""

import logging
import os

from mbu_rpa_core.exceptions import BusinessError
from mbu_solteqtand_shared_components.database.db_handler import SolteqTandDatabase

from src import steps
from src.core.application_handler import get_app, set_app
from src.core.automation_runner import AutomationRunner
from src.core.dashboard_data_handler import handle_process_dashboard
from src.helpers import config
from src.helpers.clean_up import (
    clean_up_download_folder,
    clean_up_tmp_folder,
    release_keys,
)

logger = logging.getLogger(__name__)


def process_item(item_data: dict, item_reference: str, item_id: int):
    """Process a single work item through all automation phases.

    Args:
        item_data: Dictionary containing the item's data payload.
        item_reference: Unique reference string for the item.

    Raises:
        BusinessError: If business validation fails (item goes to pending_user).
        ProcessError: If an automation step fails after retries (item is failed).
    """

    raw_cpr = item_data.get("patient_cpr") or item_data.get("cpr", "")
    cpr = raw_cpr.replace("-", "")

    runner = AutomationRunner(name=f"Process-{item_reference}")
    try:
        release_keys()

        # Step 1: Open Solteq application and log in.
        app = get_app()
        if app is None:
            app = steps.start_solteq(runner)
            set_app(app)

        # Step 2: Navigate to the patients journal in Solteq Tand.
        steps.open_patient(runner=runner, app=app, cpr=item_data.get("cpr", ""))

        # Step 3: Initialization checks -> produces PatientContext (ctx)
        solteq_db_obj = SolteqTandDatabase(
            os.getenv("DBCONNECTIONSTRINGSOLTEQTAND", "")
        )
        ctx = steps.run_initialization_checks(runner, app, solteq_db_obj, item_data)

        handle_process_dashboard(
            status="running",
            process_step_name=config.PROCESS_STEP_NAME,
            cpr=cpr,
        )

        # Step 4: Get images from Romexis and create zip file.
        if ctx.consent:
            romexis_db_conn = os.getenv("ROMEXIS_DB_CONNSTR", "")
            steps.get_romexis_images(runner, romexis_db_conn, ctx)

        # Step 5: Create digital journal; Check if exists, if not, create it.
        steps.create_medical_record(runner, app, solteq_db_obj, ctx)

        # Step 6: Get all other relevant documents
        if ctx.consent:
            steps.prepare_edi_documents(runner, solteq_db_obj, ctx)

        # Step 7: Send journal and images trough EDI Portal
        rpa_db_conn = os.getenv("DBCONNECTIONSTRINGPROD", "")
        steps.send_via_edi_portal(runner, app, rpa_db_conn, ctx)

        # Step 8: Download receipt PDF from EDI Portal and store in Solteq
        steps.store_edi_receipt(runner, app, solteq_db_obj, ctx)

        # Step 9: Create administrativ note
        steps.create_administrative_note(runner, app, solteq_db_obj, ctx)

        # Step 10: Update patient journal data.
        steps.update_patient_info(runner, app, ctx)

        # Step 11: Check if patient has a specific event, if so, process it.
        steps.process_event(runner, app, solteq_db_obj, ctx)

        # Step 12: Create booking reminder; Check if exists, if not, create it.
        steps.create_booking_reminders(runner, app, solteq_db_obj, ctx)

        handle_process_dashboard(
            status="success",
            process_step_name=config.PROCESS_STEP_NAME,
            cpr=cpr,
        )

    except BusinessError as be:
        logger.error("Business error occurred: %s", be)
        handle_process_dashboard(
            status="failed",
            process_step_name=config.PROCESS_STEP_NAME,
            cpr=cpr,
            failure=be,
            rerun_config={"workitem_id": item_id},
        )
        raise
    except Exception as e:
        logger.error("%s", e)
        handle_process_dashboard(
            status="failed",
            process_step_name=config.PROCESS_STEP_NAME,
            cpr=cpr,
            failure=e,
        )
        raise
    finally:
        clean_up_download_folder()
        clean_up_tmp_folder()
        logger.info(runner.summary())
