# tests/test_integration_initialization.py

"""Integration tests for initialization checks.

Runs the real initialization checks against the real database
and real Solteq Tand application. Requires:
    - Solteq Tand installed and credentials configured
    - Database connection strings in .env
    - A test patient CPR that has valid data

Run with: uv run pytest tests/ -v -m integration -p no:faulthandler
"""

import os
from contextlib import suppress

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.integration

# Guard imports — skip if uiautomation not available
try:
    from mbu_solteqtand_shared_components.database.db_handler import SolteqTandDatabase

    from src.core.automation_runner import AutomationRunner
    from src.core.patient_context import PatientContext
    from src.steps.initialization_checks import (
        check_administrative_note,
        check_contractor_in_edi_portal,
        check_extern_clinic,
        check_extern_clinic_deal,
        check_other_documents,
        check_primary_clinic,
        run_initialization_checks,
    )
    from src.steps.solteq_open_patient_journal import open_patient
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

    runner = AutomationRunner(name="Integration-Init-Setup")
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


@pytest.fixture
def ctx():
    """A PatientContext built from environment test data."""
    if not has_test_cpr():
        pytest.skip("TEST_PATIENT_CPR not set")
    return PatientContext(
        patient_cpr=TEST_PATIENT_CPR,
        patient_name=TEST_PATIENT_NAME,
        request_number="INTEGRATION-TEST",
        tandplejeplan=True,
        regionstilsagn=True,
    )


# ------------------------------------------------------------------
# Individual check tests
# ------------------------------------------------------------------
class TestCheckPrimaryClinicIntegration:
    def test_returns_data_for_known_patient(self, solteq_db, ctx):
        result = check_primary_clinic(solteq_db, ctx)

        assert isinstance(result, list)
        assert len(result) > 0
        assert "patientStatus" in result[0]
        assert "preferredDentalClinicName" in result[0]


class TestCheckExternClinicIntegration:
    def test_returns_data_for_known_patient(self, solteq_db, ctx):
        result = check_extern_clinic(solteq_db, ctx)

        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0].get("contractorId") is not None
        assert result[0].get("phoneNumber") is not None


class TestCheckExternClinicDealIntegration:
    def test_deal_exists_for_known_contractor(self, solteq_db, ctx):
        # First get the extern clinic to find the contractor ID
        extern_data = check_extern_clinic(solteq_db, ctx)
        contractor_id = extern_data[0]["contractorId"]

        # Then check the deal — should not raise
        check_extern_clinic_deal(solteq_db, contractor_id)


class TestCheckAdministrativeNoteIntegration:
    def test_returns_notes_for_known_patient(self, solteq_db, ctx):
        result = check_administrative_note(solteq_db, ctx)

        # Result can be empty if tandplejeplan is False or note exists
        assert isinstance(result, list)


class TestCheckOtherDocumentsIntegration:
    def test_check_completes_for_known_patient(self, solteq_db, ctx):
        # Should not raise for a valid test patient
        check_other_documents(solteq_db, ctx)


# ------------------------------------------------------------------
# EDI Portal check (requires GUI)
# ------------------------------------------------------------------
class TestCheckContractorInEdiPortalIntegration:
    def test_contractor_valid_in_edi_portal(
        self, runner_with_summary, solteq_app, solteq_db, ctx
    ):
        # First open the patient so EDI portal has context
        open_patient(runner_with_summary, solteq_app, ctx.patient_cpr)

        # Get extern clinic data from the database
        ctx.extern_clinic_data = check_extern_clinic(solteq_db, ctx)

        # Run the EDI portal check
        check_contractor_in_edi_portal(
            runner_with_summary, solteq_app, ctx, RPA_DB_CONN
        )

        # Verify steps completed
        step_names = [s.step for s in runner_with_summary.completed_steps]
        assert "Open EDI portal for contractor check" in step_names
        assert "Check contractor ID in EDI portal" in step_names
        assert "Close EDI portal" in step_names

        # Close patient window for next test
        solteq_app.close_patient_window()


# ------------------------------------------------------------------
# Full initialization flow
# ------------------------------------------------------------------
class TestRunInitializationChecksIntegration:
    def test_full_initialization_flow(
        self,
        runner_with_summary,
        solteq_app,
        solteq_db,
    ):
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set")

        # Open the patient first
        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)

        item_data = {
            "patient_cpr": TEST_PATIENT_CPR,
            "patient_name": TEST_PATIENT_NAME,
            "requestNumberServiceNow": "INTEGRATION-TEST",
            "tandplejeplan": True,
            "regionstilsagn": True,
        }

        ctx = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, item_data, RPA_DB_CONN
        )
        print("ctx: %s", ctx)

        # Verify the context was populated
        assert ctx.patient_cpr == TEST_PATIENT_CPR.replace("-", "")
        assert len(ctx.primary_clinic_data) > 0
        assert len(ctx.extern_clinic_data) > 0
        assert ctx.contractor_id is not None

        # Verify properties work
        assert ctx.patient_status is not None
        assert ctx.preferred_clinic_name is not None

        # Close patient window
        solteq_app.close_patient_window()

    def test_initialization_populates_all_context_fields(
        self,
        runner_with_summary,
        solteq_app,
        solteq_db,
    ):
        """Verify every field that later steps depend on is populated."""
        if not has_test_cpr():
            pytest.skip("TEST_PATIENT_CPR not set")

        open_patient(runner_with_summary, solteq_app, TEST_PATIENT_CPR)

        item_data = {
            "patient_cpr": TEST_PATIENT_CPR,
            "patient_name": TEST_PATIENT_NAME,
            "requestNumberServiceNow": "INTEGRATION-TEST-2",
            "tandplejeplan": True,
            "regionstilsagn": True,
        }

        ctx = run_initialization_checks(
            runner_with_summary, solteq_app, solteq_db, item_data, RPA_DB_CONN
        )

        # These are the fields that process steps will read from ctx
        fields_to_check = {
            "patient_cpr": ctx.patient_cpr,
            "patient_name": ctx.patient_name,
            "primary_clinic_data": ctx.primary_clinic_data,
            "extern_clinic_data": ctx.extern_clinic_data,
            "contractor_id": ctx.contractor_id,
            "clinic_phone_number": ctx.clinic_phone_number,
            "patient_status": ctx.patient_status,
            "preferred_clinic_name": ctx.preferred_clinic_name,
        }

        missing = [name for name, value in fields_to_check.items() if not value]
        assert not missing, f"These context fields were empty: {missing}"

        solteq_app.close_patient_window()
