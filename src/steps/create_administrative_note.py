# src/steps/create_administrative_note.py

"""Create administrative note — check if it exists, create if not.

Creates a final administrative note in the patient's journal
confirming that the discharge process was completed by the robot.
This is the last step in the process, serving as an audit trail.

Checks the database for an existing note with the same text
created within the last month. If found, the step is skipped.
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

JOURNAL_NOTE = (
    "Administrativt notat 'Udskrivning til frit valg gennemført af robot. "
    "Sendt information til pt. og sendt journal og billedmateriale til "
    "privat tandlæge via EDI-portal. Se dokumentskab. "
    "Journal flyttet til Tandplejen Aarhus'"
)


def _note_exists(db: SolteqTandDatabase, ctx: PatientContext) -> bool:
    """Check if the administrative note was already created within the last month.

    Args:
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr.

    Returns:
        True if the note already exists.
    """
    one_month_ago = datetime.datetime.now(datetime.UTC).replace(
        tzinfo=None
    ) - relativedelta(months=1)

    result = db.get_list_of_journal_notes(
        filters={
            "p.cpr": ctx.patient_cpr,
            "dn.Beskrivelse": f"%{JOURNAL_NOTE}%",
            "ds.Dokumenteret": (">=", one_month_ago),
        },
        order_by="ds.Dokumenteret",
        order_direction="DESC",
    )

    logger.info("Found %d existing administrative note(s).", len(result))
    return bool(result)


def create_administrative_note(
    runner: AutomationRunner,
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> None:
    """Create the administrative note if it doesn't already exist.

    Checks the database for an existing note created within the
    last month. If none is found, creates it via the Solteq Tand
    GUI with the 'complete' checkmark set.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr.
    """
    if _note_exists(db, ctx):
        logger.info("Administrative note already exists, skipping.")
        return

    logger.info("Creating administrative note.")

    runner.step(
        "Create administrative note",
        app.create_journal_note,
        note_message=JOURNAL_NOTE,
        checkmark_in_complete=True,
        config=StepConfig(
            max_attempts=3,
            delay=3.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    logger.info("Administrative note created successfully.")
