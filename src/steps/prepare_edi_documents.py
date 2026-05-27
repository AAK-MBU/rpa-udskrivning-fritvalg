# src/steps/prepare_edi_documents.py

"""Prepare documents for EDI portal upload.

Gathers all relevant documents from the database, copies them to a
temporary folder, and builds the file path string needed by the EDI
portal. Which documents are included depends on ctx.regionstilsagn:

- Always: the latest 'Journaludskrift' (renamed to include patient name)
- If regionstilsagn is True: also 'Udskrivning - Frit valg' documents
- If Romexis images exist: the zip file is already in the edi_portal folder

This step is entirely non-GUI — database queries and file copying.
The result (joined file paths) is stored on ctx.edi_portal_file_paths
for use by the EDI portal upload step.
"""

import logging
import os
import pathlib
import shutil

from mbu_solteqtand_shared_components.database.db_handler import SolteqTandDatabase

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)

TMP_FOLDER = r"C:\tmp\tmt"


def _get_documents_from_db(
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> list[dict]:
    """Retrieve the relevant documents from the database.

    Gets the latest 'Journaludskrift' document and other documents of
     the type 'Udskrivning - Frit valg!$#'.

    Args:
        db: The SolteqTandDatabase instance.
        ctx: The patient context.

    Returns:
        List of document dictionaries ready for copying.

    Raises:
        ValueError: If no documents are found at all.
    """
    document_types = ["Journaludskrift", "Udskrivning - Frit valg!$#"]

    documents = db.get_list_of_documents(
        filters={
            "ds.DocumentType": document_types,
            "p.cpr": ctx.patient_cpr,
            "ds.rn": "1",
            "ds.DocumentStoreStatusId": "1",
        }
    )

    if not documents:
        raise ValueError("No documents found for EDI portal.")

    logger.info("Found %d document(s) for patient.", len(documents))

    # Filter to keep only the latest Journaludskrift
    journal_docs = [d for d in documents if d["DocumentType"] == "Journaludskrift"]
    other_docs = [d for d in documents if d["DocumentType"] != "Journaludskrift"]

    latest_journal = None
    if journal_docs:
        latest_journal = max(journal_docs, key=lambda d: d["DocumentCreatedDate"])
        latest_journal["OriginalFilename"] = f"Journaludskrift - {ctx.patient_name}.pdf"

    filtered = other_docs
    if latest_journal:
        filtered.append(latest_journal)

    return filtered


def _copy_documents_to_temp(
    documents: list[dict],
    ctx: PatientContext,
) -> str:
    """Copy documents to the temporary EDI portal folder.

    Args:
        documents: List of document dicts with 'fileSourcePath' and 'OriginalFilename'.
        ctx: The patient context with patient_cpr.

    Returns:
        Path to the temporary directory containing the copied documents.
    """
    temp_dir = os.path.join(TMP_FOLDER, ctx.patient_cpr, "edi_portal")
    os.makedirs(temp_dir, exist_ok=True)

    for doc in documents:
        source = doc["fileSourcePath"]
        destination = os.path.join(temp_dir, doc["OriginalFilename"])
        shutil.copy2(source, destination)
        logger.info("Copied %s → %s", os.path.basename(source), doc["OriginalFilename"])

    return temp_dir


def _prepare_documents(
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> str:
    """Inner function that does the full gather-and-copy pipeline.

    Wrapped by runner.step() for error handling.

    Args:
        db: The SolteqTandDatabase instance.
        ctx: The patient context.

    Returns:
        Joined file paths string ready for EDI portal upload.
    """
    documents = _get_documents_from_db(db, ctx)
    temp_dir = _copy_documents_to_temp(documents, ctx)

    files = [f for f in pathlib.Path(temp_dir).iterdir() if f.is_file()]
    joined_paths = " ".join(f'"{f}"' for f in files)

    logger.info("Prepared %d file(s) for EDI portal upload.", len(files))
    return joined_paths


def prepare_edi_documents(
    runner: AutomationRunner,
    db: SolteqTandDatabase,
    ctx: PatientContext,
) -> None:
    """Gather all documents for EDI portal and copy to temp folder.

    Retrieves the relevant documents from the database, copies them
    to a temporary directory, and stores the joined file paths on
    ctx.edi_portal_file_paths for the EDI portal upload step.

    Args:
        runner: The automation runner managing this process.
        db: The SolteqTandDatabase instance.
        ctx: The patient context with patient_cpr, patient_name,
             and regionstilsagn set.
    """
    result = runner.step(
        "Prepare documents for EDI portal",
        _prepare_documents,
        db,
        ctx,
        config=StepConfig(
            max_attempts=2,
            delay=3.0,
            retryable=(TimeoutError, OSError, ConnectionError),
        ),
    )

    ctx.edi_portal_file_paths = result
    logger.info("EDI portal documents ready.")
