# tests/test_error_handling.py

from unittest.mock import MagicMock, patch

import pytest
from mbu_rpa_core.exceptions import ProcessError

from src.core.automation_runner import StepError
from src.core.error_handling import ErrorContext, handle_error


class TestHandleError:
    def test_logs_error_message(self):
        error = ProcessError("Something broke")
        log = MagicMock()

        handle_error(error, log)

        log.assert_called_once()
        assert "Something broke" in log.call_args[0][0]

    def test_calls_item_action(self):
        error = ProcessError("fail")
        log = MagicMock()
        item = MagicMock()
        action = MagicMock()

        context = ErrorContext(item=item, action=action)
        handle_error(error, log, context)

        action.assert_called_once()

    @patch("src.core.error_handling.send_error_email")
    def test_sends_email_when_configured(self, mock_send):
        error = ProcessError("fail")
        log = MagicMock()
        context = ErrorContext(send_mail=True, process_name="Test")

        handle_error(error, log, context)

        mock_send.assert_called_once()

    @patch("src.core.error_handling.send_error_email")
    def test_passes_screenshot_to_email(self, mock_send):
        error = StepError("fail", screenshot="/tmp/shot.png")
        log = MagicMock()
        context = ErrorContext(send_mail=True)

        handle_error(error, log, context)

        mock_send.assert_called_once_with(
            error=error,
            screenshot_path="/tmp/shot.png",
            process_name=None,
        )

    @patch("src.core.error_handling.send_error_email")
    def test_no_email_without_flag(self, mock_send):
        error = ProcessError("fail")
        log = MagicMock()
        context = ErrorContext(send_mail=False)

        handle_error(error, log, context)

        mock_send.assert_not_called()
