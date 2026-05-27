# src/steps/create_booking_reminders.py

"""Create booking reminders — check if they exist, create if not.

Sets booking reminders based on the patient's age:
- Under 16: two reminders — one at age 16 ('Frit valg fra 16 år')
  and one at age 22 ('Arkiveres 22 år').
- 16 or older: one reminder — at age 22 ('Arkiveres 22 år').

Each reminder is checked against the database before creation.
If it already exists, it's skipped. The GUI action (creating the
reminder) is wrapped in runner.step() for retry and screenshot support.
"""

import logging

from mbu_solteqtand_shared_components.application import SolteqTandApp
from mbu_solteqtand_shared_components.database.db_handler import SolteqTandDatabase

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import StepConfig
from src.helpers.cpr_utils import future_dates

logger = logging.getLogger(__name__)

# Base data shared by all booking reminders
BOOKING_REMINDER_DEFAULTS = {
    "comboBoxBookingType": "Husk",
    "comboBoxDentist": " Frit valg",
    "comboBoxChair": "Frit valg",
    "dateTimePickerStartTime": "07:45",
    "textBoxDuration": "5",
    "comboBoxStatus": "Behovsaftale",
}


def _build_reminders(ctx: PatientContext) -> list[dict]:
    """Build the list of reminders based on the patient's age.

    Args:
        ctx: The patient context with patient_cpr and is_under_16 set.

    Returns:
        List of reminder dictionaries ready for the GUI.
    """
    date_at_16, date_at_22 = future_dates(ctx.patient_cpr)

    # Set time to 07:45 for the booking
    date_at_16 = date_at_16.replace(hour=7, minute=45)
    date_at_22 = date_at_22.replace(hour=7, minute=45)

    reminders = []

    if ctx.is_under_16:
        reminders.append(
            {
                **BOOKING_REMINDER_DEFAULTS,
                "textBoxBookingText": "Frit valg fra 16 år",
                "futureDate": date_at_16.strftime("%d-%m-%Y"),
                "futureDateTime": date_at_16.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            }
        )

    # Both under-16 and 16+ get the archive-at-22 reminder
    reminders.append(
        {
            **BOOKING_REMINDER_DEFAULTS,
            "textBoxBookingText": "Arkiveres 22 år",
            "futureDate": date_at_22.strftime("%d-%m-%Y"),
            "futureDateTime": date_at_22.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }
    )

    return reminders


def _reminder_exists(
    db: SolteqTandDatabase, ctx: PatientContext, reminder: dict
) -> bool:
    """Check if a specific booking reminder already exists in the database.

    Args:
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr.
        reminder: The reminder dictionary containing futureDateTime.

    Returns:
        True if the reminder already exists.
    """
    existing = db.get_list_of_bookings(
        filters={
            "p.cpr": ctx.patient_cpr,
            "bt.Description": "Husk",
            "CONVERT(datetime2(0), b.StartTime)": reminder["futureDateTime"],
        }
    )
    return bool(existing)


def create_booking_reminders(
    runner: AutomationRunner,
    app: SolteqTandApp,
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> None:
    """Create booking reminders if they don't already exist.

    Builds the appropriate reminders based on the patient's age,
    checks each one against the database, and creates any that
    are missing via the Solteq Tand GUI.

    Args:
        runner: The automation runner managing this process.
        app: The logged-in SolteqTandApp instance.
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr and is_under_16 set.
    """
    reminders = _build_reminders(ctx)

    logger.info(
        "Processing %d booking reminder(s) for patient (under 16: %s).",
        len(reminders),
        ctx.is_under_16,
    )

    for reminder in reminders:
        date_label = reminder["futureDate"]

        if _reminder_exists(db, ctx, reminder):
            logger.info("Booking reminder for %s already exists, skipping.", date_label)
            continue

        logger.info("Creating booking reminder for %s.", date_label)

        runner.step(
            f"Create booking reminder {date_label}",
            app.create_booking_reminder,
            reminder,
            config=StepConfig(
                max_attempts=3,
                delay=2.0,
                retryable=(TimeoutError, RuntimeError),
            ),
        )

        logger.info("Booking reminder for %s created successfully.", date_label)
