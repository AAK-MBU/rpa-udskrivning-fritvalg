# src/steps/romexis/image_normalizer.py

"""
Normalizes Romexis image exports into a format the processing pipeline can read.

Most Romexis files are camera-raw-like and are decoded by rawpy inside
``add_black_bar_and_text_to_image``. Some are not: Romexis also stores DICOM
objects, which neither rawpy nor Pillow can open, producing
``LibRawFileUnsupportedError`` followed by ``UnidentifiedImageError``.

This module sniffs the real format from the file's magic bytes and, when the
pipeline cannot read it natively, rewrites the pixels as a lossless PNG in a
staging directory.

The staged file deliberately keeps the original filename, including the ``.img``
extension, because ``add_black_bar_and_text_to_image`` derives its output name
via ``copied_path.replace(".img", ".tiff")``. Renaming to ``.png`` here would
break that substitution and produce TIFF bytes in a ``.png`` file. Pillow
identifies formats by content, not extension, so PNG bytes in a ``.img`` file
open correctly.
"""

import logging
import os

import numpy as np
import pydicom
from PIL import Image
from pydicom.pixels import apply_voi_lut

logger = logging.getLogger(__name__)

DICM_MAGIC_OFFSET = 128
HEADER_READ_SIZE = DICM_MAGIC_OFFSET + 4

# Formats rawpy or Pillow already handle inside the pipeline. Anything matched
# here is passed through untouched.
NATIVE_MAGIC_PREFIXES = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"II*\x00",  # TIFF little-endian (also camera raw)
    b"MM\x00*",  # TIFF big-endian
    b"BM",  # BMP
)


class ImageNormalizationError(Exception):
    """Raised when a source file cannot be normalized into a readable image."""


def sniff_format(path: str) -> str:
    """
    Identify a file's real format from its magic bytes.

    Returns:
        "dicom", "native" for formats the pipeline reads directly, or "unknown".
    """
    try:
        with open(path, "rb") as f:
            header = f.read(HEADER_READ_SIZE)
    except OSError:
        logger.exception("Could not read header", extra={"source_path": path})
        return "unknown"

    if header[DICM_MAGIC_OFFSET:HEADER_READ_SIZE] == b"DICM":
        return "dicom"

    if header.startswith(NATIVE_MAGIC_PREFIXES):
        return "native"

    return "unknown"


def _dicom_to_grayscale_array(ds: pydicom.Dataset) -> np.ndarray:
    """Decode a DICOM dataset to an 8-bit grayscale array."""
    array = ds.pixel_array

    # Multi-frame objects (e.g. CBCT stacks) are not single images; take frame 0.
    number_of_frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
    if number_of_frames > 1 and array.ndim >= 3:
        logger.warning(
            "Multi-frame DICOM, using first frame only",
            extra={"frames": number_of_frames},
        )
        array = array[0]

    photometric = str(ds.get("PhotometricInterpretation", "")).upper()

    # Colour source (photos imported into Romexis): convert via Pillow.
    if array.ndim == 3 and array.shape[-1] in (3, 4):
        return np.array(Image.fromarray(array[..., :3]).convert("L"))

    # Honour the windowing the DICOM asks for; only meaningful above 8-bit.
    if array.dtype != np.uint8 and "WindowCenter" in ds:
        array = apply_voi_lut(array, ds)

    # MONOCHROME1 is inverted: low values are white.
    if photometric == "MONOCHROME1":
        array = array.max() - array

    if array.dtype != np.uint8:
        low, high = float(array.min()), float(array.max())
        array = ((array - low) / max(high - low, 1.0) * 255.0).astype(np.uint8)

    return array


def _convert_dicom(source_path: str, staged_path: str) -> None:
    """Write the DICOM's pixels to staged_path as a lossless PNG."""
    dataset = pydicom.dcmread(source_path)

    if "PixelData" not in dataset:
        raise ImageNormalizationError(
            f"DICOM contains no pixel data (SOPClassUID={dataset.get('SOPClassUID')})"
        )

    array = _dicom_to_grayscale_array(dataset)
    Image.fromarray(array, mode="L").save(staged_path, format="PNG")

    logger.info(
        "Converted DICOM for pipeline",
        extra={
            "source_path": source_path,
            "staged_path": staged_path,
            "transfer_syntax": str(dataset.file_meta.TransferSyntaxUID),
            "size": f"{array.shape[1]}x{array.shape[0]}",
        },
    )


def normalize_image_source(source_path: str, staging_dir: str) -> str:
    """
    Return a path the image pipeline can read.

    Files already in a supported format are returned unchanged. Others are
    converted into staging_dir under their original filename.

    Args:
        source_path: Path to the file on the Romexis share.
        staging_dir: Directory for converted files. Caller owns cleanup.

    Returns:
        Path to pass to add_black_bar_and_text_to_image.

    Raises:
        ImageNormalizationError: The file holds no usable image.
    """
    image_format = sniff_format(source_path)

    if image_format == "native":
        return source_path

    if image_format == "unknown":
        # Let rawpy try — this is the normal path for Romexis raw files, whose
        # proprietary headers we deliberately don't try to enumerate here.
        return source_path

    # Keep the original filename so downstream extension handling still works.
    staged_path = os.path.join(staging_dir, os.path.basename(source_path))

    try:
        _convert_dicom(source_path, staged_path)
    except ImageNormalizationError:
        raise
    except Exception as exc:
        raise ImageNormalizationError(
            f"Failed to convert DICOM {source_path}: {exc}"
        ) from exc

    return staged_path
