"""Look up EDI recipient redirects from the RPA database.

Some clinics exist in Solteq under their own provider number (ydernummer),
but are reached through a shared recipient in the EDI portal (e.g. Hasle Torv
and Brobjergparken -> 485055). These redirects are maintained in
[RPA].[rpa].[ProviderNumberRedirects] with scope 'EDI' (managed via
automation-hub). 'SOLTEQ' rows are handled upstream by the journalizing
process and are already reflected in the clinic set on the patient, so they
are ignored here.
"""

import logging

from mbu_rpa_core.database.connection import RPAConnection

logger = logging.getLogger(__name__)

_EDI_REDIRECT_QUERY = """
    SELECT [target_provider_number], [target_phone_number], [edi_subject_suffix]
    FROM [RPA].[rpa].[ProviderNumberRedirects]
    WHERE [source_provider_number] = ?
      AND [scope] = N'EDI'
      AND [is_active] = 1
"""


def get_edi_redirect(contractor_id: str | None) -> dict | None:
    """Return the active EDI redirect for a contractor, or None.

    Args:
        contractor_id: The clinic's provider number as registered in Solteq.

    Returns:
        {"contractor_id": str, "phone_number": str | None,
         "subject_suffix": str | None}, or None if no active EDI redirect.
        phone_number None means: keep the clinic's own phone number.

    Raises:
        Any database error. A failing lookup must not silently fall back to
        the clinic's own number, as that could send to the wrong recipient.
    """
    contractor_id = (contractor_id or "").strip()
    if not contractor_id:
        return None

    with RPAConnection(db_env="PROD", commit=False) as rpa_conn:
        rows = rpa_conn.execute_query(
            _EDI_REDIRECT_QUERY, [contractor_id], return_dict=True
        )

    if not rows:
        return None

    row = rows[0]
    suffix = (row["edi_subject_suffix"] or "").strip() or None
    return {
        "contractor_id": row["target_provider_number"],
        "phone_number": row["target_phone_number"],
        "subject_suffix": suffix,
    }


def build_edi_subject(base_subject: str, subject_suffix: str | None) -> str:
    """Append the optional clinic suffix and truncate to the EDI portal's 66 chars."""
    if not base_subject:
        raise ValueError("EDI portal subject is required but empty.")
    subject = f"{base_subject} {subject_suffix}" if subject_suffix else base_subject
    return subject[:66]
