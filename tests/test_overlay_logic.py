"""Unit tests for Overlay UI logic, message list management, and modes."""

import pytest
from PySide6.QtWidgets import QApplication
from kronos_veil.chat.base import ChatMessage
from kronos_veil.config import ConfigManager
from kronos_veil.overlay import OverlayWindow
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager




@pytest.fixture
def overlay(qapp, tmp_path):
    cfg_file = tmp_path / "test_settings.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cfg.settings.max_messages = 5  # Small max for testing
    cap = CaptureProtectionManager()
    style = WindowStyleManager()
    win = OverlayWindow(cfg, cap, style)
    win.show()
    yield win
    win.close()


def test_overlay_initial_state(overlay):
    assert overlay.is_locked() is False
    assert overlay.is_click_through() is False
    assert overlay.is_capture_test_mode() is False


def test_overlay_mode_toggle(overlay):
    overlay.set_locked(True)
    assert overlay.is_locked() is True
    assert overlay.header_bar.isHidden() is True
    assert overlay.resize_grip_bar.isHidden() is True

    overlay.set_locked(False)
    assert overlay.is_locked() is False
    assert overlay.header_bar.isHidden() is False
    assert overlay.resize_grip_bar.isHidden() is False


def test_overlay_add_messages_and_cap(overlay):
    for i in range(10):
        msg = ChatMessage(username=f"User{i}", message=f"Message {i}")
        overlay.add_message(msg)

    # Should be capped at max_messages (5)
    assert len(overlay._messages) == 5
    assert overlay._messages[-1].msg.message == "Message 9"


def test_overlay_clear_chat(overlay):
    overlay.add_message(ChatMessage(username="U1", message="M1"))
    overlay.add_message(ChatMessage(username="U2", message="M2"))
    assert len(overlay._messages) == 2

    overlay.clear_chat()
    assert len(overlay._messages) == 0


def test_overlay_capture_test_mode(overlay):
    assert overlay.test_banner.isHidden() is True
    overlay.set_capture_test_mode(True)
    assert overlay.is_capture_test_mode() is True
    assert overlay.test_banner.isHidden() is False

    overlay.set_capture_test_mode(False)
    assert overlay.is_capture_test_mode() is False
    assert overlay.test_banner.isHidden() is True
