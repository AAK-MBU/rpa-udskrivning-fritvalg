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
    from src.steps.solteq_start_app import start_solteq

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
    else:
        logger.info("No Solteq app instance to close.")


def hard_close():
    """Forcefully close Solteq Tand by killing the process."""
    logger.info("Closing applications hard...")
    from src.helpers.clean_up import kill_tand

    kill_tand()


def close():
    """Close Solteq softly (hard-kill fallback), then clean up other apps."""
    logger.info("Closing applications...")
    try:
        try:
            soft_close()
        except Exception as e:
            logger.warning("Soft close failed (%s); falling back to hard close.", e)
            hard_close()
    finally:
        logger.info("Cleaning up remaining applications.")
        from src.helpers.clean_up import kill_adobe, kill_msedge

        kill_adobe()
        kill_msedge()
    logger.info("Finished closing applications.")


def reset():
    """Reset the application by closing and restarting."""
    logger.info("Resetting applications...")
    close()
    startup()
    logger.info("Finished resetting applications.")
