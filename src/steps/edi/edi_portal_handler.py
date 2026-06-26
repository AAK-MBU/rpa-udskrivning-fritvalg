"""This module provides the EDI portal handler for processing EDI-related tasks."""

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pyodbc

from src.steps.edi import edi_portal_functions as edifuncs

logger = logging.getLogger(__name__)


# Context object to hold all inputs and intermediate state
@dataclass
class EdiContext:
    """
    EdiContext is a context object that holds all inputs and intermediate state
    required for processing in the EDI portal handler.

    Attributes:
        extern_clinic_data (Dict[str, Any]): External clinic data used in processing.
        queue_element (Dict[str, Any]): Queue element containing relevant information.
        journal_note (str): Note to be added to the journal.
        path_to_files_for_upload (str): Path to the files that need to be uploaded.
        subject (str): Subject of the context. Defaults to an empty string.
        receipt_path (Optional[str]): Path to the receipt file. Defaults to None.
        consent (bool): Whether the patient has given consent to upload files.
    """

    extern_clinic_data: dict[str, Any]
    queue_element: dict[str, Any]
    path_to_files_for_upload: str
    consent: bool
    subject: str | None = None
    journal_note: str | None = None
    value_data: dict[str, Any] | None = None
    receipt_path: str | None = None


# A pipeline step is any callable that receives the context and operates on it
Step = Callable[[EdiContext], bool | None]


def edi_portal_handler(context: EdiContext) -> str | None:
    """
    Executes the end-to-end EDI portal workflow using a Context object.

    Steps are defined as functions (or lambdas) that take the shared context,
    enabling cleaner signatures and centralized state management.

    Args:
        context (EdiContext):
            Holds all input parameters and manages intermediate state such as
            computed subject lines and receipt paths.

    Returns:
        Optional[str]:
            Path to the renamed PDF receipt, or None on failure.
    """

    def get_constant(constant_name: str, conn_string: str) -> dict[str, Any] | None:
        """
        Fetch a single constant from the [RPA].[rpa].[Constants] table.

        Args:
            constant_name: Constant's [name] column value to match.
            conn_string:   ODBC connection string.

        Returns:
            A dict with ``{"name": ..., "value": ...}`` if the row exists,
            otherwise **None**.

        Raises:
            pyodbc.Error: Propagates any database errors.
        """
        query = """
            SELECT [name], [value]
            FROM   [RPA].[rpa].[Constants]
            WHERE  [name] = ?
        """

        with pyodbc.connect(conn_string) as conn:
            row = conn.cursor().execute(query, constant_name).fetchone()

        if row is None:
            return None

        return {"name": row.name, "value": row.value}

    conn_string = os.getenv("DBCONNECTIONSTRINGPROD", "")
    constant = get_constant(
        constant_name="udskrivning_edi_portal_content",
        conn_string=conn_string,
    )
    if constant is None:
        raise RuntimeError(
            "Constant 'udskrivning_edi_portal_content' not found in the database."
        )

    # Data til edi_portal_content
    context.value_data = (
        json.loads(constant["value"])
        if isinstance(constant["value"], str)
        else constant["value"]
    )

    patient_name = context.queue_element.get("patient_name")
    subject = context.value_data["edi_portal_content"]["subject"]

    if not subject:
        raise ValueError("Subject is required.")

    if context.extern_clinic_data[0]["contractorId"] == "477052":
        subject = subject + " på Tandklinikken Hasle Torv"
    elif context.extern_clinic_data[0]["contractorId"] == "470678":
        subject = subject + " på Tandklinikken Brobjergparken"

    # Truncate subject to 66 characters to fit EDI portal limitations
    subject = subject[:66]

    context.subject = subject

    # Define the ordered list of pipeline steps
    pipeline: list[Step] = [
        # Navigation
        lambda ctxt: edifuncs.edi_portal_is_patient_data_sent(subject=ctxt.subject),
        lambda _: edifuncs.edi_portal_go_to_send_journal(),
        lambda _: edifuncs.edi_portal_click_next_button(sleep_time=2),
        # Contractor lookup and selection
        lambda ctxt: edifuncs.edi_portal_lookup_contractor_id(
            extern_clinic_data=ctxt.extern_clinic_data
        ),
        lambda ctxt: edifuncs.edi_portal_choose_receiver(
            extern_clinic_data=ctxt.extern_clinic_data
        ),
        lambda _: edifuncs.edi_portal_click_next_button(sleep_time=2),
        # Add journal content
        lambda ctxt: edifuncs.edi_portal_add_content(
            edi_portal_content=ctxt.value_data["edi_portal_content"],
            journal_continuation_text=ctxt.journal_note,
            extern_clinic_data=ctxt.extern_clinic_data,
        ),
        lambda _: edifuncs.edi_portal_click_next_button(sleep_time=2),
        # File upload
        lambda ctxt: (
            edifuncs.edi_portal_upload_files(
                path_to_files=ctxt.path_to_files_for_upload
            )
            if ctxt.consent
            else None
        ),
        lambda _: edifuncs.edi_portal_click_next_button(sleep_time=2),
        # Priority & send
        # lambda ctxt: edifuncs.edi_portal_choose_priority(),
        lambda _: edifuncs.edi_portal_click_next_button(sleep_time=10),
        lambda _: time.sleep(5),
        lambda _: edifuncs.edi_portal_send_message(),
        # Retrieve the sent receipt
        lambda ctxt: setattr(
            ctxt,
            "receipt_path",
            edifuncs.edi_portal_get_journal_sent_receip(subject=ctxt.subject),
        ),
        # Rename the receipt on disk
        lambda ctxt: setattr(
            ctxt,
            "receipt_path",
            edifuncs.rename_file(
                file_path=ctxt.receipt_path,  # type: ignore
                new_name=f"EDI Portal - {patient_name}",
                extension=".pdf",
            ),
        ),
    ]

    step_names = [
        "is_patient_data_sent",
        "go_to_send_journal",
        "click_next (page 1→2)",
        "lookup_contractor_id",
        "choose_receiver",
        "click_next (page 2→3)",
        "add_content",
        "click_next (page 3→4)",
        "upload_files",
        "click_next (page 4→5)",
        "click_next (page 5→send)",
        "sleep_60",
        "send_message",
    ]

    # Execute each step in sequence
    skip_steps = False
    for i, step in enumerate(
        pipeline[:-2]
    ):  # Exclude the last two steps from conditional skipping
        name = step_names[i] if i < len(step_names) else f"step_{i}"
        try:
            logger.info("[EDI] Step %d/%d: %s", i + 1, len(pipeline) - 2, name)
            if skip_steps:
                logger.info("[EDI] Skipping %s (already sent).", name)
                continue

            result = step(context)
            if result:
                logger.info(
                    "[EDI] %s returned True — skipping remaining steps until last two.",
                    name,
                )
                skip_steps = True
            else:
                logger.info("[EDI] %s done.", name)
        except Exception as e:
            logger.error("[EDI] Step %d (%s) failed: %s", i + 1, name, e)
            raise RuntimeError(f"EDI step '{name}' failed: {e}") from e

    # Always run the last two steps
    for step in pipeline[-2:]:
        try:
            step(context)
        except Exception as e:
            logger.error(
                "Step %s failed: %s",
                step.__name__ if hasattr(step, "__name__") else step,
                e,
            )
            raise RuntimeError(
                f"Step {step.__name__ if hasattr(step, '__name__') else step} failed: {e}"
            ) from e

    return context.receipt_path
