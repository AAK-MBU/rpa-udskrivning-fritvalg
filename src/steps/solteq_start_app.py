"""Solteq Tand startup steps — launch application and log in.

Uses the SolteqTandApp. Credentials are fetched from the
Automation Server, and the app path is read from the
process config.
"""

import logging

from dotenv import load_dotenv
from mbu_dev_shared_components.database.connection import RPAConnection
from mbu_solteqtand_shared_components.application import SolteqTandApp

from src.core.automation_runner import AutomationRunner
from src.core.step_configs import StepConfig

logger = logging.getLogger(__name__)

# Path to the Solteq Tand executable
SOLTEQ_TAND_APP_PATH = r"C:\Program Files (x86)\TM Care\TM Tand\TMTand.exe"


def get_rpa_credentials(credential_name: str) -> dict[str, Any]:
    """
    Get credentials from RPA connection

    Args:
        credential_name (str): Name of the credential to retrieve

    Returns:
        dict[str, Any]: Dictionary containing username, password,
                       and other credential data
    """
    with RPAConnection(db_env="PROD", commit=False) as rpa_conn:
        return rpa_conn.get_credential(credential_name)


def get_solteq_credentials() -> tuple[str, str]:
    """Retrieve Solteq Tand credentials from environment.

    Returns:
        Tuple of (username, password).

    Raises:
        ValueError: If credentials are not configured.
    """
    load_dotenv()

    creds = get_rpa_credentials("solteq_tand_svcrpambu001")
    username = creds["username"]
    password = creds["decrypted_password"]


    if not username or not password:
        raise ValueError(
            "Solteq credentials not found. "
        )

    return username, password


def start_solteq(runner: AutomationRunner) -> SolteqTandApp:
    """Launch Solteq Tand and log in.

    This creates the SolteqTandApp instance, starts the application,
    and performs login. The runner registers cleanup actions so the
    app is closed properly if later steps fail.

    Args:
        runner: The automation runner managing this process.

    Returns:
        The logged-in SolteqTandApp instance.
    """
    username, password = get_solteq_credentials()

    app = SolteqTandApp(SOLTEQ_TAND_APP_PATH, username, password)

    runner.step(
        "Start Solteq Tand",
        app.start_application,
        config=StepConfig(
            max_attempts=2,
            delay=5.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    # Register cleanup so app is closed if anything fails later
    runner.register_cleanup(app.close_solteq_tand)

    runner.step(
        "Log in to Solteq Tand",
        app.login,
        config=StepConfig(
            max_attempts=2,
            delay=3.0,
            retryable=(TimeoutError, RuntimeError),
        ),
    )

    logger.info("Solteq Tand started and logged in.")
    return app
