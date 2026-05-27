"""Module for handling Solteq Tand application startup and close.

The SolteqTandApp instance is stored as a module-level variable
so that other modules (like reset in main.py) can access it via
get_app(). The runner steps in solteq_startup.py handle the actual
start/login, and this module provides the global access point.
"""

import logging

from mbu_solteqtand_shared_components.application import SolteqTandApp

logger = logging.getLogger(__name__)

APP: SolteqTandApp | None = None


def get_app() -> SolteqTandApp | None:
    """Get the current Solteq Tand application instance."""
    return APP


def set_app(app: SolteqTandApp) -> None:
    """Set the Solteq Tand application instance after startup.

    Args:
        app: The logged-in SolteqTandApp instance from solteq_startup.
    """
    global APP  # noqa: PLW0603
    APP = app


def startup():
    """Start Solteq Tand via the runner steps.

    Note: In the new framework, startup is handled through the
    AutomationRunner in process_item.py via start_solteq().
    This function is kept for compatibility with main.py's reset().
    """
    logger.info("Starting applications...")

    from src.core.automation_runner import AutomationRunner
    from src.steps.solteq_start_app import get_solteq_credentials, start_solteq

    runner = AutomationRunner(name="Startup")
    app = start_solteq(runner)
    set_app(app)


def soft_close():
    """Close the Solteq Tand application gracefully."""
    logger.info("Closing applications softly...")
    if APP:
        try:
            APP.close_patient_window()
        except Exception as e:
            logger.warning("Error closing patient window: %s", e)
        try:
            APP.close_solteq_tand()
        except Exception as e:
            logger.warning("Error closing Solteq Tand: %s", e)


def hard_close():
    """Forcefully close Solteq Tand by killing the process."""
    logger.info("Closing applications hard...")
    import subprocess

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "TMTand.exe"],
            check=False,
            capture_output=True,
        )
    except Exception as e:
        logger.warning("Error killing TMTand.exe: %s", e)


def close():
    """Close Solteq Tand softly, falling back to hard close."""
    try:
        soft_close()
    except Exception:
        hard_close()


def reset():
    """Reset the application by closing and restarting."""
    close()
    startup()
