"""Unit tests for Win32 capture protection logic and error handling."""

import sys
from unittest.mock import MagicMock
import pytest
from kronos_veil.windows.capture_protection import (
    CaptureProtectionManager,
    CaptureProtectionStatus,
    WDA_EXCLUDEFROMCAPTURE,
    WDA_NONE,
)


def test_capture_protection_init():
    mgr = CaptureProtectionManager()
    if sys.platform == "win32":
        assert mgr.status == CaptureProtectionStatus.DISABLED
        assert mgr.is_os_supported() is True or mgr.is_os_supported() is False
    else:
        assert mgr.status == CaptureProtectionStatus.UNSUPPORTED


def test_invalid_hwnd_handling():
    mgr = CaptureProtectionManager()
    status, msg = mgr.set_protection(0, enable=True)
    assert status == CaptureProtectionStatus.FAILED
    assert "Invalid window handle" in msg


def test_capture_protection_mocked_success():
    mgr = CaptureProtectionManager()
    mock_set = MagicMock(return_value=1)

    mgr._set_affinity_func = mock_set
    # Mock get_affinity to return WDA_EXCLUDEFROMCAPTURE
    mgr.get_affinity = MagicMock(return_value=WDA_EXCLUDEFROMCAPTURE)

    status, msg = mgr.set_protection(12345, enable=True)
    assert status == CaptureProtectionStatus.ACTIVE
    assert mock_set.call_count == 1
    call_hwnd, call_affinity = mock_set.call_args[0]
    assert (hasattr(call_hwnd, "value") and call_hwnd.value == 12345) or call_hwnd == 12345
    assert call_affinity == WDA_EXCLUDEFROMCAPTURE


def test_capture_protection_disabled():
    mgr = CaptureProtectionManager()
    mock_set = MagicMock(return_value=1)
    mgr._set_affinity_func = mock_set

    status, msg = mgr.set_protection(12345, enable=False)
    assert status == CaptureProtectionStatus.DISABLED
    assert mock_set.call_count == 1
    call_hwnd, call_affinity = mock_set.call_args[0]
    assert (hasattr(call_hwnd, "value") and call_hwnd.value == 12345) or call_hwnd == 12345
    assert call_affinity == WDA_NONE
