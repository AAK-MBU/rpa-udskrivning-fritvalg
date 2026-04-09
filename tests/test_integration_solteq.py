# tests/test_integration_solteq.py

"""Integration tests — require Solteq Tand installed and running.

Run with: uv run pytest tests/ -v -m integration

These tests use real credentials and launch the real application.
Only run on a machine configured for RPA execution.
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.integration

# Guard the imports — skip the entire file if dependencies are missing
try:
    from src.core.automation_runner import AutomationRunner, StepError
    from src.steps.solteq_open_patient_journal import open_patient, validate_cpr
    from src.steps.solteq_start_app import SOLTEQ_TAND_APP_PATH, start_solteq

    HAS_DEPENDENCIES = True
except ImportError:
    HAS_DEPENDENCIES = False

if not HAS_DEPENDENCIES:
    pytest.skip(
        "Solteq dependencies not available (uiautomation not installed)",
        allow_module_level=True,
    )


# ------------------------------------------------------------------
# Test data
# ------------------------------------------------------------------
TEST_PATIENT_CPR = os.getenv("TEST_PATIENT_CPR", "")


def has_solteq_installed() -> bool:
    return os.path.exists(SOLTEQ_TAND_APP_PATH)


def has_credentials() -> bool:
    return bool(os.getenv("SOLTEQ_USERNAME") and os.getenv("SOLTEQ_PASSWORD"))


def has_test_cpr() -> bool:
    return bool(TEST_PATIENT_CPR)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
@pytest.fixture(scope="module")
def solteq_app():
    """Start Solteq Tand once for all tests in this module."""
    if not has_solteq_installed():
        pytest.skip("Solteq Tand not installed on this machine")
    if not has_credentials():
        pytest.skip("SOLTEQ_USERNAME / SOLTEQ_PASSWORD not set")

    runner = AutomationRunner(name="Integration-Setup")
    app = start_solteq(runner)

    yield app

    try:
        app.close_patient_window()
    except Exception:
        pass
    try:
        app.close_solteq_tand()
    except Exception:
        pass


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------
class TestSolteqStartup:
    def test_app_is_running(self, solteq_app):
        assert solteq_app is not None


class TestPatientLookup:
    def test_open_patient_by_cpr(self, runner_with_summary, solteq_app):
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set in environment")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        assert runner_with_summary.completed_steps[-1].success is True
        solteq_app.close_patient_window()

    def test_open_patient_twice(self, runner_with_summary, solteq_app):
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set in environment")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        assert runner_with_summary.completed_steps[-1].success is True
        solteq_app.close_patient_window()

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        assert runner_with_summary.completed_steps[-1].success is True
        solteq_app.close_patient_window()

    def test_invalid_cpr_raises_business_error(self, runner_with_summary, solteq_app):
        from mbu_rpa_core.exceptions import BusinessError

        with pytest.raises(BusinessError):
            open_patient(runner_with_summary, solteq_app, "invalid")


class TestFullItemFlow:
    def test_complete_process_item_flow(self, runner_with_summary, solteq_app):
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set in environment")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)

        runner_with_summary.step(
            "Close patient window", solteq_app.close_patient_window
        )

        for step in runner_with_summary.completed_steps:
            assert step.success is True, f"Step '{step.step}' failed"
