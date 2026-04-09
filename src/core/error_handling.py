"""Module for handling errors.

Updated to use screenshots already captured by the AutomationRunner
at the moment of failure, rather than grabbing a new screenshot after
cleanup and reset have changed the screen state.
"""

import json
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage

from automation_server_client import WorkItem
from mbu_dev_shared_components.database.connection import RPAConnection
from mbu_rpa_core.exceptions import BusinessError, ProcessError

from src.core.screenshot import screenshot_to_base64


@dataclass
class ErrorContext:
    """Context for error handling."""

    item: WorkItem | None = None
    action: Callable | None = None
    send_mail: bool = False
    process_name: str | None = None


def handle_error(
    error: ProcessError | BusinessError,
    log,
    context: ErrorContext | None = None,
) -> None:
    """Handle an error by logging, updating the work item, and optionally sending email.

    Args:
        error: The error to handle.
        log: Logging function to log messages (e.g. logger.info, logger.error).
        context: Context object containing additional parameters.
    """
    if context is None:
        context = ErrorContext()

    error_json = json.dumps(error.__dictinfo__())

    log_msg = f"Error: {error}"
    if context.item:
        log_msg = f"{repr(error)} raised for item: {context.item}. " + log_msg
        if context.action:
            context.action(error_json)

    log(log_msg)

    if context.send_mail:
        # Use the screenshot captured by the runner.
        screenshot_path = getattr(error, "screenshot", None)
        send_error_email(
            error=error,
            screenshot_path=screenshot_path,
            process_name=context.process_name,
        )


def send_error_email(
    error: ProcessError | BusinessError,
    screenshot_path: str | None = None,
    process_name: str | None = None,
) -> None:
    """Send email to defined recipient with error information.

    Args:
        error: The error to include in the email.
        screenshot_path: Path to a screenshot already saved to disk.
                         If provided, it is embedded in the email as base64.
        process_name: Name of the process where the error occurred.
    """
    rpa_conn = RPAConnection(db_env="PROD", commit=False)
    with rpa_conn:
        error_email = rpa_conn.get_constant("Error Email")["value"]
        error_sender = rpa_conn.get_constant("Email Friend")["value"]
        smtp_server = rpa_conn.get_constant("smtp_server")["value"]
        smtp_port = rpa_conn.get_constant("smtp_port")["value"]

    msg = EmailMessage()
    msg["to"] = error_email
    msg["from"] = error_sender
    msg["subject"] = f"Error: {process_name}" if process_name else "Process Error"

    error_dict = error.__dictinfo__()

    # Convert saved screenshot to base64 for email embedding
    screenshot_b64 = None
    if screenshot_path:
        screenshot_b64 = screenshot_to_base64(screenshot_path)

    if screenshot_b64:
        html_message = f"""
            <html>
                <body>
                    <p>Error type: {error_dict["type"]}</p>
                    <p>Error message: {error_dict["message"]}</p>
                    <p>{error_dict["traceback"]}</p>
                    <img src="data:image/png;base64,{screenshot_b64}" alt="Screenshot">
                </body>
            </html>
        """
    else:
        html_message = f"""
            <html>
                <body>
                    <p>Error type: {error_dict["type"]}</p>
                    <p>Error message: {error_dict["message"]}</p>
                    <p>{error_dict["traceback"]}</p>
                </body>
            </html>
        """

    msg.set_content("Please enable HTML to view this message.")
    msg.add_alternative(html_message, subtype="html")

    with smtplib.SMTP(smtp_server, smtp_port) as smtp:
        smtp.starttls()
        smtp.send_message(msg)
