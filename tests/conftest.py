"""Shared PySide6 test fixtures."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication instance for all tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
