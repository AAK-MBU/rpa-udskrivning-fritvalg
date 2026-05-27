# tests/conftest.py

import io
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.core.automation_runner import AutomationRunner


@pytest.fixture
def runner():
    """A fresh AutomationRunner for each test."""
    return AutomationRunner(name="Test-Runner")


@pytest.fixture
def mock_app():
    """A mock SolteqTandApp with all methods stubbed."""
    app = MagicMock()
    app.start_application.return_value = None
    app.login.return_value = None
    app.open_patient.return_value = None
    app.close_patient_window.return_value = None
    app.close_solteq_tand.return_value = None
    return app


@pytest.fixture(autouse=True)
def disable_screenshots():
    """Prevent actual screenshot capture during tests."""
    with patch("src.core.automation_runner.take_screenshot", return_value=None):
        yield


@pytest.fixture
def runner_with_summary():
    """A runner that prints its summary after the test finishes."""
    r = AutomationRunner(name="Integration-Test")
    yield r
    if r.completed_steps:
        # Temporarily restore stdout to print the summary
        import sys

        real_stdout = sys.__stdout__
        real_stdout.write("\n" + r.summary() + "\n")
        real_stdout.flush()


@pytest.fixture(autouse=True)
def suppress_uiautomation_prints(request):
    """Suppress all print() noise from uiautomation during integration tests.

    The uiautomation library uses print() extensively for debug output,
    which clutters the pytest output. This fixture redirects stdout to
    /dev/null during integration tests only.
    """
    if request.node.get_closest_marker("integration"):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        yield
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    else:
        yield
