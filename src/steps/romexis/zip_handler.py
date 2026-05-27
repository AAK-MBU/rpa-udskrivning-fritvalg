"""
This module handles the creation and splitting of ZIP files.
It includes functions to create a ZIP file from images, split a ZIP file into smaller parts
if it exceeds a specified size, and process the ZIP file to check its size and split it if necessary.
"""

import logging
import os
import zipfile
from pathlib import Path

from romexis.helper_functions import zip_folder_contents

logger = logging.getLogger(__name__)

TMP_FOLDER = r"C:\tmp\tmt"


def create_zip_from_images(
    ssn: str, person_name: str, source_folder: str
) -> tuple[str, str]:
    """Zip processed image files.

    Args:
        ssn: Patient's social security number.
        person_name: Patient's name, used for the ZIP file's name.
        source_folder: Path to the folder containing the processed image files.

    Returns:
        zip_full_path: Full path to the created ZIP.
        zip_filename: The name of the ZIP file (without the path).
    """
    logger.info(
        "Starting ZIP creation",
        extra={
            "source_folder": source_folder,
        },
    )

    if not os.path.isdir(source_folder):
        logger.error("Source folder does not exist", extra={"path": source_folder})
        raise FileNotFoundError(f"Source folder does not exist: {source_folder}")

    if not any(Path(source_folder).iterdir()):
        logger.warning("Source folder is empty", extra={"path": source_folder})
        raise ValueError(f"Source folder is empty, nothing to zip: {source_folder}")

    zip_file_path = os.path.join(TMP_FOLDER, ssn, "edi_portal")

    if not os.path.exists(zip_file_path):
        try:
            os.makedirs(zip_file_path, exist_ok=True)
        except OSError:
            logger.exception(
                "Failed to create ZIP directory", extra={"path": str(zip_file_path)}
            )
            raise

    zip_filename = f"{person_name}.zip"
    zip_full_path = os.path.join(zip_file_path, zip_filename)

    try:
        logger.info(
            "Creating ZIP file",
            extra={"destination": str(zip_full_path)},
        )
        zip_folder_contents(source_folder, zip_full_path)

    except Exception:
        logger.exception(
            "Failed to create ZIP file",
            extra={"destination": str(zip_full_path)},
        )
        raise

    logger.info(
        "ZIP file created successfully",
        extra={
            "zip_path": str(zip_full_path),
            "zip_filename": zip_filename,
        },
    )

    return zip_full_path, zip_filename


def split_zip(
    input_zip_path: str, output_dir: str | None = None, max_size: int | None = None
) -> Path:
    """
    Split a ZIP file into smaller parts if it exceeds the specified size.

    Args:
        input_zip_path (str): Path to the input ZIP file.
        output_dir (str | None): Directory to save the split ZIP files. If None, a new directory will be created.
        max_size (int | None): Maximum size of each split ZIP file in bytes.

    Returns:
        Path: Path to the directory containing the split ZIP files.
    """
    input_path = Path(input_zip_path)

    if not input_path.is_file():
        logger.error("ZIP file not found", extra={"path": input_zip_path})
        raise FileNotFoundError(f"Input ZIP file does not exist: {input_zip_path}")

    if max_size is None or max_size <= 0:
        logger.error("Invalid max_size", extra={"max_size": max_size})
        raise ValueError("max_size must be a positive integer")

    if output_dir is None:
        output_dir = input_path.parent / f"{input_zip_path.stem}_split"
    else:
        output_dir = Path(output_dir)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception(
            "Failed to create output directory", extra={"path": str(output_dir)}
        )
        raise

    with zipfile.ZipFile(input_path, "r") as original_zip:
        file_infos = original_zip.infolist()

        buckets = []
        current_bucket = []
        current_size = 0

        for info in file_infos:
            file_compressed_size = info.compress_size
            if file_compressed_size > max_size:
                if current_bucket:
                    buckets.append(current_bucket)
                    current_bucket = []
                    current_size = 0
                buckets.append([info])
                continue

            if current_size + file_compressed_size > max_size:
                buckets.append(current_bucket)
                current_bucket = []
                current_size = 0

            current_bucket.append(info)
            current_size += file_compressed_size

        if current_bucket:
            buckets.append(current_bucket)

        for idx, bucket in enumerate(buckets, start=1):
            part_zip_path = output_dir / f"{input_path.stem}_part{idx}.zip"
            with zipfile.ZipFile(
                part_zip_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as part_zip:
                for info in bucket:
                    data = original_zip.read(info.filename)
                    part_zip.writestr(info, data)

    logger.info(
        "ZIP split completed",
        extra={
            "parts_created": len(buckets),
            "output_dir": str(output_dir),
        },
    )
    return output_dir


def process_zip(input_zip_path: str, max_size: int | None = None) -> Path:
    """
    Check the size of the ZIP file and split if necessary.

    Args:
        input_zip_path (str): Path to the input ZIP file.
        max_size (int | None): Maximum size of each split ZIP file in bytes. Default is 50 MB.

    returns:
        Path | None: Path to the directory containing the split ZIP files, or None if no splitting was needed.
    """
    input_path = Path(input_zip_path)

    if not input_path.is_file():
        logger.error("ZIP file not found", extra={"path": input_zip_path})
        raise FileNotFoundError(f"ZIP file does not exist: {input_zip_path}")

    if max_size is None:
        max_size = 50 * 1024 * 1024  # 50 MB

    zip_size = input_path.stat().st_size

    logger.info(
        "Processing ZIP",
        extra={
            "path": str(input_path),
            "size_bytes": zip_size,
            "max_size": max_size,
        },
    )

    if zip_size > max_size:
        logger.info("ZIP exceeds max size, splitting", extra={"size": zip_size})
        output_dir = split_zip(
            input_zip_path=input_path, output_dir=None, max_size=max_size
        )
        return output_dir

    logger.info("ZIP within size limit, no split needed", extra={"size": zip_size})
    return input_path
