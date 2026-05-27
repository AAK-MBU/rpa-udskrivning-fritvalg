# src/steps/process_event.py

"""Process departure event — check if it exists, create if not.

Checks the database for an archived 'Afgang til klinik 751' event
for the patient. If none exists, triggers the event through the
Solteq Tand GUI. If it already exists, skips silently.

This follows the idempotency pattern used throughout the process:
check first, act only if needed. Safe to run multiple times.
"""

import datetime
import logging
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from mbu_solteqtand_shared_components.application import SolteqTandApp
from mbu_solteqtand_shared_components.database.db_handler import SolteqTandDatabase

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import FLAKY_UI

logger = logging.getLogger(__name__)

EVENT_NAME = "Afgang til klinik 751"


def _check_and_process_event(
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> None:
    """Check if the departure event exists and process it if found.

    Queries the database for events matching the patient's CPR
    within the last month. If exactly one event is found, it gets
    processed through the GUI. If none are found, the step is skipped.

    Raises:
        ValueError: If more than one matching event is found,
                    indicating unexpected data that needs manual review.
    """

    logger.info("Checking if event '%s' exists for patient.", EVENT_NAME)
    one_month_ago = (
        datetime.datetime.now(ZoneInfo("Europe/Copenhagen")) - relativedelta(months=1)
    ).date()

    events = db.get_list_of_events(
        filters={
            "p.cpr": ctx.patient_cpr,
            "e.currentStateText": EVENT_NAME,
            "e.archived": 0,
            "e.currentStateDate": (">=", one_month_ago),
        }
    )

    if len(events) > 1:
        logger.error("Events: %s", events)
        raise ValueError("Found more than one event to process")

    if events:
        app.process_event()

        logger.info("Event '%s' exists, successfully processed.", EVENT_NAME)

    logger.info("Event '%s' not found, skipping.", EVENT_NAME)


def process_event(
    runner: AutomationRunner,
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> None:
    """Check if the departure event exists, process it if it exists.

    The database check and GUI action are wrapped in a single runner step.
    This means retries cover the entire operation — if the GUI times out
    after the database check succeeded, the retry re-checks the database
    first, which is safe because the check is read-only.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        db: The SolteqTandDatabase instance.
        ctx: The patient context.
    """

    runner.step(
        "Check and process depature event",
        _check_and_process_event,
        app,
        db,
        ctx,
        config=FLAKY_UI,
    )
