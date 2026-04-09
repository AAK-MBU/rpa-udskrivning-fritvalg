import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock the solteqtand module before importing the step
sys.modules["mbu_dev_shared_components.solteqtand"] = MagicMock()

from mbu_rpa_core.exceptions import BusinessError

from src.core.automation_runner import AutomationRunner, StepError
from src.steps.solteq_open_patient_journal import open_patient, validate_cpr


class TestValidateCpr:
    def test_valid_cpr(self):
        assert validate_cpr("0102031234") == "0102031234"

    def test_strips_hyphen(self):
        assert validate_cpr("010203-1234") == "0102031234"

    def test_rejects_too_short(self):
        with pytest.raises(BusinessError, match="Invalid CPR"):
            validate_cpr("12345")

    def test_rejects_letters(self):
        with pytest.raises(BusinessError, match="Invalid CPR"):
            validate_cpr("010203abcd")

    def test_rejects_empty(self):
        with pytest.raises(BusinessError, match="Invalid CPR"):
            validate_cpr("")


class TestOpenPatient:
    def test_opens_patient_successfully(self, runner, mock_app):
        open_patient(runner, mock_app, "010203-1234")
        mock_app.open_patient.assert_called_once_with("0102031234")

    def test_registers_cleanup(self, runner, mock_app):
        open_patient(runner, mock_app, "0102031234")
        assert len(runner._cleanup_actions) == 1

    def test_invalid_cpr_raises_business_error(self, runner, mock_app):
        with pytest.raises(BusinessError):
            open_patient(runner, mock_app, "invalid")
        mock_app.open_patient.assert_not_called()

    def test_masks_cpr_in_step_description(self, runner, mock_app):
        open_patient(runner, mock_app, "0102031234")
        step_name = runner.completed_steps[0].step
        assert "XXXX" in step_name
        assert "1234" not in step_name

    def test_retries_on_timeout(self, runner, mock_app):
        mock_app.open_patient.side_effect = [TimeoutError(), None]
        open_patient(runner, mock_app, "0102031234")
        assert mock_app.open_patient.call_count == 2
