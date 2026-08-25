"""
This module handles the processing of images.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from romexis.helper_functions import add_black_bar_and_text_to_image

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


def log_file_info(file_path: str, image_id: object = None) -> None:
    """Log what kind of file this is, for diagnosing a processing failure.

    Never raises, so it is safe to call from an except block.

    Args:
        file_path: Path to the image file on the Romexis share.
        image_id: Romexis image_id, for cross-referencing the log.
    """
    parts = [f"image_id={image_id}", f"path={file_path}"]

    try:
        if not os.path.exists(file_path):
            parts.append("exists=False")
            logger.error("FILE INFO: %s", " | ".join(parts))
            return

        parts.append(f"size={os.path.getsize(file_path)}")

        with open(file_path, "rb") as f:
            head = f.read(132)

        parts.append(f"first_bytes={head[:12].hex(' ')}")

        is_dicom = head[128:132] == b"DICM"
        parts.append(f"dicom={is_dicom}")

        if is_dicom:
            try:
                import pydicom

                ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                parts.append(f"transfer_syntax={ds.file_meta.TransferSyntaxUID}")
                parts.append(f"syntax_name={ds.file_meta.TransferSyntaxUID.name}")
                parts.append(f"sop_class={ds.get('SOPClassUID', '')}")
                parts.append(f"modality={ds.get('Modality', '')}")
                parts.append(f"size_px={ds.get('Columns', '?')}x{ds.get('Rows', '?')}")
                parts.append(f"bits={ds.get('BitsAllocated', '')}")
                parts.append(f"photometric={ds.get('PhotometricInterpretation', '')}")
                parts.append(f"frames={ds.get('NumberOfFrames', 1)}")
            except ImportError:
                parts.append("pydicom=NOT INSTALLED")
            # pylint: disable-next = broad-exception-caught
            except Exception as e:  # noqa: BLE001
                parts.append(f"dicom_read_error={type(e).__name__}: {e}")

    # pylint: disable-next = broad-exception-caught
    except Exception as e:  # noqa: BLE001
        parts.append(f"log_error={type(e).__name__}: {e}")

    logger.error("FILE INFO: %s", " | ".join(parts))


def process_images_threaded(
    images_data, destination_path, ssn, person_name, db_handler
) -> None:
    """Process images concurrently using threads."""
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}

        for img in images_data:
            gamma_data = db_handler.get_gamma_data(image_id=img["image_id"])
            source_path = build_source_path(img["file_path"])

            if not os.path.exists(source_path):
                logger.info("Skipping missing file: %s", source_path)
                continue

            formatted_date = format_image_date(img.get("image_date"))
            image_type = img.get("image_type")

            future = executor.submit(
                add_black_bar_and_text_to_image,
                source_path,
                destination_path,
                ssn,
                person_name,
                formatted_date,
                image_type,
                rotation_angle=img.get("rotation_angle", 0),
                is_mirror=img.get("is_mirror", False),
                gamma_value=(
                    gamma_data[0]["gamma_value"]
                    if gamma_data and gamma_data[0].get("gamma_value")
                    else 1.0
                ),
            )
            futures[future] = (img["image_id"], source_path)

        for future in as_completed(futures):
            image_id, source_path = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(
                    "Image processing failed for image_id=%s: %s: %s",
                    image_id,
                    type(e).__name__,
                    e,
                )
                log_file_info(source_path, image_id)
                raise


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
