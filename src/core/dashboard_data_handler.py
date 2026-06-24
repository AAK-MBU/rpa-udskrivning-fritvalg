# src/core/dashboard_data_handler.py
"""Handler for fetching and updating dashboard data."""

import logging
import os
from typing import Any

from mbu_process_dashboard_shared_components import process_step_run
from mbu_process_dashboard_shared_components.process_dashboard_client import (
    ProcessDashboardClient,
)

from src.helpers import config

logger = logging.getLogger(__name__)

CLIENT = ProcessDashboardClient(api_admin_token=os.environ.get("API_ADMIN_TOKEN"))


def handle_process_dashboard(
    status: str,
    process_step_name: str,
    cpr: str = "",
    failure: Exception | None = None,
    rerun_config: dict | None = None,
):
    """
    Method for handling updating the process dashboard
    """
    try:
        client = CLIENT

        status_update_data: dict[str, Any] = {"status": status}

        citizen_cpr = cpr

        logger.info("before get_step_run_id_for_process_step_cpr() ...")

        step_run_id = process_step_run.get_step_run_id_for_process_step_cpr(
            client=client,
            process_name=config.PROCESS_NAME,
            step_name=process_step_name,
            cpr=citizen_cpr,
        )

        if failure:
            step_run_update_data = process_step_run.build_step_run_update(
                status=status, failure=failure, rerun_config=rerun_config
            )

            status_update_data["failure"] = failure

        else:
            step_run_update_data = process_step_run.build_step_run_update(status=status)

        logger.info("before update_dashboard_step_run_by_id() ...")

        updated_step_run_data, status_code = (
            process_step_run.update_dashboard_step_run_by_id(
                client=client,
                step_run_id=step_run_id,
                update_data=step_run_update_data,
            )
        )

        return updated_step_run_data, status_code
    except Exception as e:
        logger.error("Error in handle_process_dashboard: %s", e)
        raise e
