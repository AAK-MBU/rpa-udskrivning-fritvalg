# src/helpers/cpr_utils.py

"""Utility functions for Danish CPR numbers.

Handles CPR-to-birthdate conversion using the official DST/CPR
century rules, and age calculations used to determine which
document templates and booking rules apply.
"""

from datetime import datetime
from zoneinfo import ZoneInfo


def cpr_to_birthdate(cpr: str) -> datetime:
    """Convert a Danish CPR number (DDMMYYSSSS) to a birth date.

    Uses the official century rules from DST/CPR:
        personal 0000-1999 → 1900-1999 if YY >= 37, else 2000-2036
        personal 2000-4999 → 1900-1999
        personal 5000-8999 → 1900-1999 if YY >= 37, else 2000-2036
        personal 9000-9999 → 1800-1899 if YY >= 37, else 2000-2036

    Args:
        cpr: A 10-digit CPR string (DDMMYYSSSS), no hyphens.

    Returns:
        A datetime representing the birth date.

    Raises:
        ValueError: If the CPR format is invalid.
    """
    CPR_LEN = 10
    PERSONAL_LOW_MAX = 1999
    PERSONAL_MID_MAX = 4999
    PERSONAL_HIGH_MAX = 8999
    PERSONAL_TOP_MAX = 9999
    YEAR_SPLIT = 37

    PERSONAL_LOW_MIN = 0
    PERSONAL_MID_MIN = 2000
    PERSONAL_HIGH_MIN = 5000
    PERSONAL_TOP_MIN = 9000

    if len(cpr) != CPR_LEN or not cpr.isdigit():
        raise ValueError("CPR number must be exactly 10 digits (DDMMYYSSSS)")

    day = int(cpr[0:2])
    month = int(cpr[2:4])
    yy = int(cpr[4:6])
    ssss = int(cpr[6:10])

    if PERSONAL_LOW_MIN <= ssss <= PERSONAL_LOW_MAX:
        year = 1900 + yy if yy >= YEAR_SPLIT else 2000 + yy
    elif PERSONAL_MID_MIN <= ssss <= PERSONAL_MID_MAX:
        year = 1900 + yy
    elif PERSONAL_HIGH_MIN <= ssss <= PERSONAL_HIGH_MAX:
        year = 1900 + yy if yy >= YEAR_SPLIT else 2000 + yy
    elif PERSONAL_TOP_MIN <= ssss <= PERSONAL_TOP_MAX:
        year = 1800 + yy if yy >= YEAR_SPLIT else 2000 + yy
    else:
        raise ValueError("Invalid CPR personal-number range")

    return datetime(year, month, day, tzinfo=ZoneInfo("Europe/Copenhagen"))


def is_under_16(cpr: str) -> bool:
    """Check if a person is under 16 years old based on their CPR.

    Args:
        cpr: A 10-digit CPR string (DDMMYYSSSS), no hyphens.

    Returns:
        True if the person is younger than 16.
    """
    AGE_LIMIT: int = 16
    birth_date = cpr_to_birthdate(cpr)
    today = datetime.now(ZoneInfo("Europe/Copenhagen")).date()
    age = (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )
    return age < AGE_LIMIT


def future_dates(cpr: str) -> tuple[datetime, datetime]:
    """Calculate the dates when the patient turns 16 and 22.

    Used for booking reminders — a reminder is set at 16 years
    (transition to 'Frit valg fra 16 år') and at 22 years
    (patient gets archived).

    Handles leap year birthdays safely by falling back to Feb 28
    if Feb 29 doesn't exist in the target year.

    Args:
        cpr: A 10-digit CPR string (DDMMYYSSSS), no hyphens.

    Returns:
        Tuple of (date_at_16, date_at_22) as datetime objects.
    """
    birth_date = cpr_to_birthdate(cpr)

    def add_years_safely(date: datetime, years: int) -> datetime:
        target_year = date.year + years
        try:
            return date.replace(year=target_year)
        except ValueError:
            return date.replace(year=target_year, day=28)

    date_16_years = add_years_safely(birth_date, 16)
    date_22_years = add_years_safely(birth_date, 22)

    return date_16_years, date_22_years
