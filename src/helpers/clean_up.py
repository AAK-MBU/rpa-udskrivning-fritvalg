# src/helpers/clean_up.py
"""Module for resetting and cleaning up during and after a process run."""

import ctypes
import logging
import os
import shutil
from pathlib import Path

import psutil
from psutil import AccessDenied, NoSuchProcess, ZombieProcess

from . import config

logger = logging.getLogger(__name__)


def release_keys() -> None:
    """Release Ctrl, Alt, and Shift keys if they are stuck."""

    logger.info("Releasing Ctrl, Alt, and Shift keys.")
    try:
        # Use Windows API to release keys
        user32 = ctypes.windll.user32

        # Key codes
        keys_to_release = [
            0x11,  # VK_CONTROL
            0x10,  # VK_SHIFT
            0x12,  # VK_MENU (Alt)
            0x5B,  # VK_LWIN
            0x5C,  # VK_RWIN
            0xA2,  # VK_LCONTROL
            0xA3,  # VK_RCONTROL
            0xA0,  # VK_LSHIFT
            0xA1,  # VK_RSHIFT
            0xA4,  # VK_LMENU
            0xA5,  # VK_RMENU
        ]

        # Send key up events (0x0002 is KEYEVENTF_KEYUP)
        for key in keys_to_release:
            user32.keybd_event(key, 0, 0x0002, 0)

    # pylint: disable-next = broad-exception-caught
    except Exception as e:
        logger.error("Error releasing keys: %s", e)


def clean_up_tmp_folder() -> None:
    """Clean up the temporary folder."""
    logger.info("Cleaning up temporary folder.")
    if os.path.exists(config.TMP_FOLDER):
        for filename in os.listdir(config.TMP_FOLDER):
            file_path = os.path.join(config.TMP_FOLDER, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as error:  # pylint: disable=broad-except
                logger.error("Failed to delete %s. Reason: %s", file_path, error)
        logger.info("Temporary folder %s cleaned up.", config.TMP_FOLDER)
    else:
        logger.info("Temporary folder %s does not exist.", config.TMP_FOLDER)


def clean_up_download_folder() -> None:
    """Clean up the download folder."""
    download_folder = str(Path.home() / "Downloads")

    logger.info("Cleaning up download folder.")
    if os.path.exists(download_folder):
        for filename in os.listdir(download_folder):
            file_path = os.path.join(download_folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as error:  # pylint: disable=broad-except
                logger.error("Failed to delete %s. Reason: %s", file_path, error)
        logger.info("Download folder %s cleaned up.", download_folder)
    else:
        logger.info("Download folder %s does not exist.", download_folder)


def _find_processes(application_name: str) -> list:
    """Return all running processes whose name or exe matches application_name."""
    target = application_name.lower()
    procs = []
    for proc in psutil.process_iter(
        attrs=["pid", "name", "exe", "cmdline"], ad_value=None
    ):
        try:
            name = (proc.info.get("name") or "").lower()
            exe_base = os.path.basename(proc.info.get("exe") or "").lower()
            if target in (name, exe_base):
                procs.append(proc)
        except (NoSuchProcess, ZombieProcess):
            continue
        # pylint: disable-next = broad-exception-caught
        except Exception as e:
            logger.error(
                "While enumerating %s, skipping PID %s: %s",
                application_name,
                getattr(proc, "pid", "?"),
                e,
            )
    return procs


def _signal_process(proc, action: str, application_name: str) -> bool:
    """Apply terminate/kill to one process. Returns False if it no longer exists."""
    try:
        getattr(proc, action)()
        return True
    except (NoSuchProcess, ZombieProcess):
        return False
    except AccessDenied as e:
        logger.error(
            "Access denied %sing %s (PID %s): %s",
            action,
            application_name,
            proc.pid,
            e,
        )
    # pylint: disable-next = broad-exception-caught
    except Exception as e:
        logger.error(
            "Unexpected error %sing %s (PID %s): %s",
            action,
            application_name,
            proc.pid,
            e,
        )
    return True


def kill_application(application_name: str) -> None:
    """Best-effort kill of all processes matching application_name on Windows."""
    logger.info("Killing %s processes.", application_name)

    procs = _find_processes(application_name)

    # Try graceful terminate first
    for proc in procs:
        _signal_process(proc, "terminate", application_name)

    # Wait a moment, then force kill stragglers
    gone, alive = psutil.wait_procs(procs, timeout=5)

    for p in gone:
        logger.info("%s (PID %s) exited cleanly.", application_name, p.pid)

    for proc in alive:
        _signal_process(proc, "kill", application_name)


def kill_adobe() -> None:
    """Kill all Adobe Acrobat/Reader processes, whichever variant is installed."""
    for name in ("Acrobat.exe", "AcroRd32.exe"):
        kill_application(name)


def kill_msedge() -> None:
    """Kill all Microsoft Edge processes."""
    kill_application("msedge.exe")


def kill_tand() -> None:
    """Kill all TMTand processes."""
    kill_application("TMTand.exe")
