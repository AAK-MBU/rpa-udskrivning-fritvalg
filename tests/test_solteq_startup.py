import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock the solteqtand module before importing the step
sys.modules["mbu_dev_shared_components.solteqtand"] = MagicMock()

from src.core.automation_runner import AutomationRunner, StepError
from src.steps.solteq_start_app import start_solteq


class TestStartSolteq:
    @patch("src.steps.solteq_start_app.get_solteq_credentials")
    @patch("src.steps.solteq_start_app.SolteqTandApp")
    def test_starts_and_logs_in(self, mock_app_class, mock_creds, runner):
        mock_creds.return_value = ("user", "pass")
        mock_app = MagicMock()
        mock_app_class.return_value = mock_app

        result = start_solteq(runner)

        mock_app.start_application.assert_called_once()
        mock_app.login.assert_called_once()
        assert result is mock_app

    @patch("src.steps.solteq_start_app.get_solteq_credentials")
    @patch("src.steps.solteq_start_app.SolteqTandApp")
    def test_registers_cleanup(self, mock_app_class, mock_creds, runner):
        mock_creds.return_value = ("user", "pass")
        mock_app_class.return_value = MagicMock()

        start_solteq(runner)

        assert len(runner._cleanup_actions) == 1

    @patch("src.steps.solteq_start_app.get_solteq_credentials")
    @patch("src.steps.solteq_start_app.SolteqTandApp")
    def test_records_two_steps(self, mock_app_class, mock_creds, runner):
        mock_creds.return_value = ("user", "pass")
        mock_app_class.return_value = MagicMock()

        start_solteq(runner)

        assert len(runner.completed_steps) == 2
        assert runner.completed_steps[0].step == "Start Solteq Tand"
        assert runner.completed_steps[1].step == "Log in to Solteq Tand"

    @patch("src.steps.solteq_start_app.get_solteq_credentials")
    @patch("src.steps.solteq_start_app.SolteqTandApp")
    def test_login_failure_raises_step_error(self, mock_app_class, mock_creds, runner):
        mock_creds.return_value = ("user", "pass")
        mock_app = MagicMock()
        mock_app.login.side_effect = RuntimeError("Login failed")
        mock_app_class.return_value = mock_app

        with pytest.raises(StepError, match="Log in to Solteq Tand"):
            start_solteq(runner)

    @patch("src.steps.solteq_start_app.get_solteq_credentials")
    def test_missing_credentials_raises(self, mock_creds, runner):
        mock_creds.side_effect = ValueError("Credentials not found")

        with pytest.raises(ValueError):
            start_solteq(runner)
