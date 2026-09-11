"""Unit tests for SettingsWindow, TrayManager, and end-to-end UI signal wiring."""

import pytest
from PySide6.QtWidgets import QApplication
from kronos_veil.config import ConfigManager
from kronos_veil.overlay import OverlayWindow
from kronos_veil.settings_window import SettingsWindow
from kronos_veil.tray import TrayManager, create_default_icon
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager


def test_tray_icon_generation(qapp):
    icon = create_default_icon(64)
    assert icon is not None
    assert not icon.isNull()


def test_tray_manager_initialization(qapp):
    tray = TrayManager()
    assert tray.tray_icon is not None
    assert tray.menu is not None
    assert len(tray.menu.actions()) >= 8

    # Test state update
    tray.update_states(locked=True, click_through=True, capture_protected=True)
    assert tray.act_clickthrough.isChecked() is True
    assert tray.act_capture.isChecked() is True
    assert tray.act_edit.isEnabled() is True
    assert tray.act_lock.isEnabled() is False


def test_settings_window_interactions(qapp, tmp_path):
    cfg_file = tmp_path / "settings.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()

    win = SettingsWindow(cfg, cap)
    win.show()

    # Verify initial GUI values match config
    assert win.overlay_opacity_slider.value() == int(cfg.settings.overlay_opacity * 100)
    assert win.font_spin.value() == cfg.settings.font_size
    assert win.lock_cb.isChecked() == cfg.settings.locked

    # Trigger UI updates
    win.overlay_opacity_slider.setValue(80)
    assert cfg.settings.overlay_opacity == 0.8

    win.font_spin.setValue(16)
    assert cfg.settings.font_size == 16

    win.lock_cb.setChecked(True)
    assert cfg.settings.locked is True

    # Test new Widgets & Profiles controls
    assert win.ed_enable_cb.isChecked() is True
    win.ed_enable_cb.setChecked(False)
    assert cfg.settings.event_deck_enabled is False

    assert win.auto_profile_cb.isChecked() is True
    win.auto_profile_cb.setChecked(False)
    assert cfg.settings.auto_profile_enabled is False

    win.close()

