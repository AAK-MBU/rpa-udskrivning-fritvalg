# src/steps/romexis/image_handler.py

"""
This module handles the processing of images.
"""

import logging
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from romexis.helper_functions import add_black_bar_and_text_to_image

from src.steps.romexis.image_normalizer import (
    ImageNormalizationError,
    normalize_image_source,
)

logger = logging.getLogger(__name__)

ROMEXIS_ROOT_PATH = r"\\SRVAPPROMEX04\romexis_images$"


def build_source_path(raw_path: str) -> str:
    """Convert relative path to full UNC path."""
    return os.path.join(
        ROMEXIS_ROOT_PATH,
        raw_path[3:].replace("romexis_images/", "").replace("/", "\\"),
    )


def format_image_date(date_value: object) -> str | None:
    """
    Format a YYYYMMDD value into DD/MM/YYYY string.

    Args:
        date_value: Value representing a date in YYYYMMDD format (int or str)

    Returns:
        Formatted date string (DD/MM/YYYY) or None if invalid
    """
    if date_value is None:
        logger.warning("Received None as date_value")
        return None

    date_str = str(date_value).strip()

    YYYYMMDD_LENGTH = 8

    if len(date_str) != YYYYMMDD_LENGTH or not date_str.isdigit():
        logger.warning(
            "Invalid date format",
            extra={"date_value": date_value},
        )
        return None

    try:
        parsed_date = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]))
        formatted_date = parsed_date.strftime("%d/%m/%Y")

        logger.debug(
            "Successfully formatted date",
            extra={
                "input": date_value,
                "output": formatted_date,
            },
        )

        return formatted_date

    except ValueError:
        logger.warning(
            "Invalid date value (failed parsing)",
            extra={"date_value": date_value},
        )
        return None


def _process_single_image(
    source_path: str,
    staging_dir: str,
    *args,
    **kwargs,
) -> None:
    """Normalize the source format if needed, then run standard processing.

    Runs on a worker thread so conversion cost is parallelized alongside
    the rest of the image processing.

    Args:
        source_path: Path to the file on the Romexis share.
        staging_dir: Directory for format-converted intermediates.
        *args: Positional arguments forwarded to add_black_bar_and_text_to_image.
        **kwargs: Keyword arguments forwarded to add_black_bar_and_text_to_image.
    """
    readable_path = normalize_image_source(source_path, staging_dir)
    add_black_bar_and_text_to_image(readable_path, *args, **kwargs)


def process_images_threaded(
    images_data, destination_path, ssn, person_name, db_handler
) -> None:
    """Process images concurrently using threads.

    Raises:
        RuntimeError: One or more images could not be processed.
    """
    futures = {}
    failures = []
    staging_dir = tempfile.mkdtemp(prefix="romexis_normalize_")

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            for img in images_data:
                source_path = build_source_path(img["file_path"])

                if not os.path.exists(source_path):
                    logger.info("Skipping missing file: %s", source_path)
                    continue

                if os.path.getsize(source_path) == 0:
                    logger.warning("Skipping zero-byte file: %s", source_path)
                    continue

                gamma_data = db_handler.get_gamma_data(image_id=img["image_id"])

                future = executor.submit(
                    _process_single_image,
                    source_path,
                    staging_dir,
                    destination_path,
                    ssn,
                    person_name,
                    format_image_date(img.get("image_date")),
                    img.get("image_type"),
                    rotation_angle=img.get("rotation_angle", 0),
                    is_mirror=img.get("is_mirror", False),
                    gamma_value=(
                        gamma_data[0]["gamma_value"]
                        if gamma_data and gamma_data[0].get("gamma_value")
                        else 1.0
                    ),
                )
                futures[future] = (img["image_id"], source_path)

            # Drain every future before re-raising, so no worker's exception is
            # left unretrieved and the executor shuts down cleanly.
            for future in as_completed(futures):
                image_id, source_path = futures[future]
                try:
                    future.result()
                except ImageNormalizationError:
                    logger.exception(
                        "Unsupported image format",
                        extra={"image_id": image_id, "source_path": source_path},
                    )
                    failures.append((image_id, source_path))
                except Exception:
                    logger.exception(
                        "Image processing failed",
                        extra={"image_id": image_id, "source_path": source_path},
                    )
                    failures.append((image_id, source_path))
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    if failures:
        # A patient record export must not silently omit images. To degrade
        # instead of failing the work item, log and return here rather than raise.
        logger.error(
            "%d of %d images failed",
            len(failures),
            len(futures),
            extra={"failed_images": [image_id for image_id, _ in failures]},
        )
        raise RuntimeError(
            f"{len(failures)} of {len(futures)} images could not be processed: "
            f"{[image_id for image_id, _ in failures]}"
        )


def clear_img_files_in_folder(folder_path: str) -> None:
    """Clear all .img files in the specified folder."""
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) and file_path.endswith(".img"):
                logger.info("Removing file: %s", file_path)
                os.remove(file_path)
        # pylint: disable-next = broad-exception-caught
        except Exception as e:
            print(f"Error removing file {file_path}: {e}")
            logger.error("Error removing file %s: %s", file_path, e)
