# tests/test_integration_update_patient_info.py

"""Integration tests for update_patient_info.

Runs against the real Solteq Tand application. Tests each part
of the update individually, then a full flow test at the end.

Run with: uv run pytest tests/test_integration_update_patient_info.py -v -m integration -p no:faulthandler
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.integration

# Guard imports
try:
    from contextlib import suppress

    from mbu_solteqtand_shared_components.database.db_handler import SolteqTandDatabase

    from src.core.automation_runner import AutomationRunner
    from src.steps.initialization_checks import run_initialization_checks
    from src.steps.solteq_open_patient_journal import open_patient
    from src.steps.solteq_start_app import SOLTEQ_TAND_APP_PATH, start_solteq
    from src.steps.update_patient_info import (
        DEFAULT_CLINIC_NAME,
        DEFAULT_CLINICIAN_NAME,
        update_patient_info,
    )

    HAS_DEPENDENCIES = True
except ImportError as e:
    print(f"IMPORT FAILED: {e}")
    HAS_DEPENDENCIES = False

if not HAS_DEPENDENCIES:
    pytest.skip(
        "Solteq dependencies not available (uiautomation not installed)",
        allow_module_level=True,
    )

# ------------------------------------------------------------------
# Test data from environment
# ------------------------------------------------------------------
TEST_PATIENT_CPR = os.getenv("TEST_PATIENT_CPR", "")
TEST_PATIENT_NAME = os.getenv("TEST_PATIENT_NAME", "")
SOLTEQ_DB_CONN = os.getenv("SOLTEQ_TAND_DB_CONNSTR", "")
RPA_DB_CONN = os.getenv("RPA_DB_CONNSTR", "")


def has_solteq_installed() -> bool:
    return os.path.exists(SOLTEQ_TAND_APP_PATH)


def has_credentials() -> bool:
    return bool(os.getenv("SOLTEQ_USERNAME") and os.getenv("SOLTEQ_PASSWORD"))


def has_test_cpr() -> bool:
    return bool(TEST_PATIENT_CPR)


def has_db_connections() -> bool:
    return bool(SOLTEQ_DB_CONN and RPA_DB_CONN)


def make_item_data() -> dict:
    return {
        "patient_cpr": TEST_PATIENT_CPR,
        "patient_name": TEST_PATIENT_NAME,
        "requestNumberServiceNow": "INTEGRATION-UPDATE-TEST",
        "tandplejeplan": True,
        "regionstilsagn": True,
    }


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

    runner = AutomationRunner(name="Integration-UpdatePatient-Setup")
    app = start_solteq(runner)

    yield app

    with suppress(Exception):
        app.close_patient_window()
    with suppress(Exception):
        app.close_solteq_tand()


@pytest.fixture(scope="module")
def solteq_db():
    """Create a SolteqTandDatabase instance for the test module."""
    if not has_db_connections():
        pytest.skip("SOLTEQ_TAND_DB_CONNSTR not set")
    return SolteqTandDatabase(SOLTEQ_DB_CONN)


@pytest.fixture(autouse=True)
def close_patient_window_after_each_test(solteq_app):
    """Always close the patient window after each test, even on failure."""
    yield
    with suppress(Exception):
        solteq_app.close_patient_window()


# ------------------------------------------------------------------
# Tests — individual parts
# ------------------------------------------------------------------
class TestDischargeFilename:
    def test_filename_set_for_under_16(
        self, runner_with_summary, solteq_app, solteq_db
    ):
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        ctx = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, make_item_data(), RPA_DB_CONN
        )

        update_patient_info(runner_with_summary, solteq_app, ctx)

        assert ctx.discharge_document_filename != ""
        if ctx.is_under_16:
            assert "0-15" in ctx.discharge_document_filename
        else:
            assert "16" in ctx.discharge_document_filename

        solteq_app.close_patient_window()

    def test_filename_is_valid_option(self, runner_with_summary, solteq_app, solteq_db):
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        ctx = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, make_item_data(), RPA_DB_CONN
        )

        update_patient_info(runner_with_summary, solteq_app, ctx)

        valid_filenames = [
            "Udskrivning til privat praksis 0-15 år",
            "Udskrivning til privat praksis fra 16 år",
        ]
        assert ctx.discharge_document_filename in valid_filenames

        solteq_app.close_patient_window()


class TestUpdateStatus:
    def test_status_updated_successfully(
        self, runner_with_summary, solteq_app, solteq_db
    ):
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        ctx = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, make_item_data(), RPA_DB_CONN
        )

        update_patient_info(runner_with_summary, solteq_app, ctx)

        # If status needed updating, there should be an "Update patient status" step
        step_names = [s.step for s in runner_with_summary.completed_steps]
        if ctx.patient_status != (
            "Frit valg 0-15 år" if ctx.is_under_16 else "Frit valg fra 16 år"
        ):
            assert "Update patient status" in step_names

        for step in runner_with_summary.completed_steps:
            assert step.success is True, f"Step '{step.step}' failed"

        solteq_app.close_patient_window()


class TestUpdateClinic:
    def test_clinic_updated_successfully(
        self, runner_with_summary, solteq_app, solteq_db
    ):
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        ctx = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, make_item_data(), RPA_DB_CONN
        )

        update_patient_info(runner_with_summary, solteq_app, ctx)

        step_names = [s.step for s in runner_with_summary.completed_steps]
        if ctx.preferred_clinic_name != DEFAULT_CLINIC_NAME:
            assert "Change primary clinic" in step_names

        for step in runner_with_summary.completed_steps:
            assert step.success is True, f"Step '{step.step}' failed"

        solteq_app.close_patient_window()


class TestUpdateDentist:
    def test_dentist_updated_successfully(
        self, runner_with_summary, solteq_app, solteq_db
    ):
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        ctx = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, make_item_data(), RPA_DB_CONN
        )

        update_patient_info(runner_with_summary, solteq_app, ctx)

        step_names = [s.step for s in runner_with_summary.completed_steps]
        if ctx.clinician_name != DEFAULT_CLINICIAN_NAME:
            assert "Change primary dentist" in step_names

        for step in runner_with_summary.completed_steps:
            assert step.success is True, f"Step '{step.step}' failed"

        solteq_app.close_patient_window()


class TestIdempotency:
    def test_update_twice_does_not_fail(
        self, runner_with_summary, solteq_app, solteq_db
    ):
        """Running update twice should not fail — second run skips GUI updates."""
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set")

        # First run
        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        ctx = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, make_item_data(), RPA_DB_CONN
        )
        update_patient_info(runner_with_summary, solteq_app, ctx)
        solteq_app.close_patient_window()

        steps_after_first = len(runner_with_summary.completed_steps)

        # Second run — values should already match defaults
        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)
        ctx2 = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, make_item_data(), RPA_DB_CONN
        )
        update_patient_info(runner_with_summary, solteq_app, ctx2)
        solteq_app.close_patient_window()

        steps_after_second = len(runner_with_summary.completed_steps)

        for step in runner_with_summary.completed_steps:
            assert step.success is True, f"Step '{step.step}' failed"

        # Second run should skip GUI updates since values already match
        assert steps_after_second < steps_after_first


# ------------------------------------------------------------------
# Full flow
# ------------------------------------------------------------------
class TestFullUpdateFlow:
    def test_complete_update_patient_flow(
        self, runner_with_summary, solteq_app, solteq_db
    ):
        """Full flow: open patient → init → update info → close."""
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)

        ctx = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, make_item_data(), RPA_DB_CONN
        )

        update_patient_info(runner_with_summary, solteq_app, ctx)

        runner_with_summary.step(
            "Close patient window", solteq_app.close_patient_window
        )

        # Verify everything succeeded
        for step in runner_with_summary.completed_steps:
            assert step.success is True, f"Step '{step.step}' failed"

        # Verify context was fully populated
        assert ctx.discharge_document_filename != ""
        assert ctx.patient_cpr == TEST_PATIENT_CPR.replace("-", "")
