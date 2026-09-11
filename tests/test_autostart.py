"""Tests for Windows Auto-Start Registry Manager."""

import sys
from unittest.mock import MagicMock, patch

from kronos_veil.autostart import (
    get_application_command,
    is_autostart_enabled,
    is_autostart_supported,
    set_autostart,
)


def test_is_autostart_supported():
    supported = is_autostart_supported()
    if sys.platform == "win32":
        assert supported is True
    else:
        assert supported is False


def test_get_application_command_custom_and_default():
    cmd = get_application_command("C:\\test\\app.exe")
    assert "app.exe" in cmd

    def_cmd = get_application_command()
    assert len(def_cmd) > 0


def test_is_autostart_enabled_mocked():
    with patch("winreg.OpenKey") as mock_open:
        with patch("winreg.QueryValueEx", return_value=("cmd.exe", 1)):
            assert is_autostart_enabled("TestApp") is True

    with patch("winreg.OpenKey", side_effect=FileNotFoundError):
        assert is_autostart_enabled("TestApp") is False


def test_set_autostart_enable_and_disable_mocked():
    with patch("winreg.OpenKey"):
        with patch("winreg.SetValueEx") as mock_set:
            success = set_autostart(True, "TestApp", "C:\\test\\app.exe")
            assert success is True
            assert mock_set.called

        with patch("winreg.DeleteValue") as mock_del:
            success = set_autostart(False, "TestApp")
            assert success is True
            assert mock_del.called
