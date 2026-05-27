# src/steps/get_romexis_images.py

"""Get images from Romexis and create a zip file.

Fetches the patient's dental images from the Romexis database,
processes them (adds black bar with patient info, applies gamma
correction, rotation, and mirroring), and creates a zip file
for upload via the EDI portal.

This step is entirely non-GUI — it queries databases, reads files
from the Romexis network share, processes images, and creates a zip.
Returns None if the patient has no images in Romexis, which is not
an error — some patients simply don't have images.

The zip path is stored on ctx.romexis_zip_path for use by the
EDI portal step.
"""

import logging
import os

from romexis.db_handler import RomexisDbHandler

from src.core.automation_runner import AutomationRunner
from src.core.patient_context import PatientContext
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)

TMP_FOLDER = r"C:\tmp\tmt"


def _get_person_info(db: RomexisDbHandler, cpr: str) -> tuple[str, str] | None:
    """Retrieve person ID and name from Romexis database.

    Args:
        db: The RomexisDbHandler instance.
        cpr: The patient's CPR number.

    Returns:
        Tuple of (person_id, person_name) or None if not found.
    """
    person_data = db.get_person_data(external_id=cpr)

    if not person_data:
        logger.info("No person data found in Romexis for CPR.")
        return None

    person = person_data[0]

    if not person.get("person_id"):
        logger.info("Person ID not found in Romexis.")
        return None

    if not person.get("first_name") and not person.get("last_name"):
        logger.info("Person name not found in Romexis.")
        return None

    person_id = person["person_id"]
    person_name = " ".join(
        filter(
            None,
            [
                person.get("first_name"),
                person.get("second_name"),
                person.get("third_name"),
                person.get("last_name"),
            ],
        )
    )

    return person_id, person_name


def _get_image_data(db: RomexisDbHandler, person_id: str) -> list:
    """Retrieve image IDs and image data from Romexis.

    Args:
        db: The RomexisDbHandler instance.
        person_id: The Romexis person ID.

    Returns:
        List of image data dictionaries, empty if no images found.
    """
    image_ids = db.get_image_ids(patient_id=person_id)

    if not image_ids:
        return []

    return db.get_image_data(image_ids=image_ids)


def _process_and_zip_images(
    romexis_db: RomexisDbHandler,
    cpr: str,
    person_name: str,
    images_data: list,
) -> tuple[str, str]:
    """Process images and create a zip file.

    Imports the image processing and zip functions from
    the shared components library. Processes images with
    threading for performance, cleans up .img files, and
    creates the final zip.

    Args:
        romexis_db: The RomexisDbHandler for gamma data lookups.
        cpr: The patient's CPR number (used for folder paths).
        person_name: The patient's name (used for zip filename).
        images_data: List of image data from the database.

    Returns:
        Tuple of (zip_full_path, zip_filename).
    """
    from src.steps.romexis.image_handler import (
        clear_img_files_in_folder,
        process_images_threaded,
    )
    from src.steps.romexis.zip_handler import create_zip_from_images

    destination_path = os.path.join(TMP_FOLDER, cpr, "img")

    logger.info("Processing %d images for patient.", len(images_data))
    process_images_threaded(images_data, destination_path, cpr, person_name, romexis_db)

    logger.info("Removing .img files from temp folder.")
    clear_img_files_in_folder(folder_path=destination_path)

    logger.info("Creating zip file.")
    zip_full_path, zip_filename = create_zip_from_images(
        ssn=cpr, person_name=person_name, source_folder=destination_path
    )

    logger.info("Zip created: %s", zip_filename)
    return zip_full_path, zip_filename


def _fetch_and_process_romexis_images(
    ctx: PatientContext,
    romexis_db_conn: str,
) -> tuple[str, str] | None:
    """Inner function that does the full fetch-process-zip pipeline.

    Wrapped by runner.step() for screenshot and error handling.

    Args:
        ctx: The patient context with patient_cpr set.
        romexis_db_conn: Romexis database connection string.

    Returns:
        Tuple of (zip_path, zip_filename) or None if no images found.
    """
    romexis_db = RomexisDbHandler(conn_str=romexis_db_conn)

    person_info = _get_person_info(romexis_db, ctx.patient_cpr)
    if person_info is None:
        logger.info("Patient not found in Romexis, skipping image export.")
        return None

    person_id, person_name = person_info

    images_data = _get_image_data(romexis_db, person_id)
    if not images_data:
        logger.info("No images found for patient in Romexis, skipping.")
        return None

    return _process_and_zip_images(
        romexis_db, ctx.patient_cpr, person_name, images_data
    )


def get_romexis_images(
    runner: AutomationRunner,
    romexis_db_conn: str,
    ctx: PatientContext,
) -> None:
    """Fetch images from Romexis, process them, and create a zip file.

    The entire pipeline (database lookup → image processing → zip creation)
    is wrapped in a single runner step for error handling and screenshot
    support. If the patient has no images in Romexis, the step completes
    successfully with no zip created.

    The zip path is stored on ctx.romexis_zip_path for use by the
    EDI portal upload step.

    Args:
        runner: The automation runner managing this process.
        ctx: The patient context with patient_cpr set.
        romexis_db_conn: Romexis database connection string.
    """
    result = runner.step(
        "Fetch and process Romexis images",
        _fetch_and_process_romexis_images,
        ctx,
        romexis_db_conn,
        config=StepConfig(
            max_attempts=2,
            delay=5.0,
            retryable=(TimeoutError, OSError, ConnectionError),
        ),
    )

    if result is not None:
        zip_path, zip_filename = result
        ctx.romexis_zip_path = zip_path
        ctx.romexis_zip_filename = zip_filename
        logger.info("Romexis images ready: %s", zip_filename)
    else:
        ctx.romexis_zip_path = None
        ctx.romexis_zip_filename = None
        logger.info("No Romexis images for this patient.")
