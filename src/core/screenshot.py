# src/core/screenshot.py

"""Module for capturing screenshots during automation failures.

Screenshots are taken immediately when an error occurs, before any
cleanup or recovery runs, so they capture the actual error state.
"""

import base64
import logging
import os
import re
from datetime import UTC, datetime

from PIL import ImageGrab

logger = logging.getLogger(__name__)

# SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "screenshots")


def take_screenshot(runner_name: str, step: str, attempt: int) -> str | None:
    """Capture screenshot immediately and save to disk.

    Args:
        runner_name: Name of the automation runner.
        step: Description of the step that failed.
        attempt: Which attempt number failed.

    Returns:
        File path to the saved screenshot, or None if capture failed.
    """
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)

        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        safe_step = re.sub(r"[^\w\-]", "_", step)[:50]
        safe_runner = re.sub(r"[^\w\-]", "_", runner_name)[:50]
        filename = f"{timestamp}_{safe_runner}_{safe_step}_attempt{attempt}.png"
        filepath = os.path.join(SCREENSHOT_DIR, filename)

        screenshot = ImageGrab.grab()
        screenshot.save(filepath, format="PNG")

        logger.info("Screenshot saved: %s", filepath)
        return filepath

    except Exception as e:
        logger.warning("Failed to capture screenshot: %s", e)
        return None


def screenshot_to_base64(filepath: str) -> str | None:
    """Convert a saved screenshot to base64 for email embedding.

    Args:
        filepath: Path to the PNG screenshot file.

    Returns:
        Base64-encoded string of the image, or None if conversion failed.
    """
    try:
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.warning("Failed to encode screenshot: %s", e)
        return None
