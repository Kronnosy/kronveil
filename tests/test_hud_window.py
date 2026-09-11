"""
Unit tests for MiniHudWindow standalone HUD component.
"""

import pytest
from PySide6.QtWidgets import QApplication
from kronos_veil.config import ConfigManager
from kronos_veil.hud import MiniHudWindow
from kronos_veil.obs.client import OBSStreamStats
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager


def test_hud_window_initialization(qapp, tmp_path):
    cfg_file = tmp_path / "hud_test.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    hud = MiniHudWindow(cfg, cap, style)
    assert hud.objectName() == "KronosVeilMiniHud"
    assert hud.live_badge is not None
    assert hud.uptime_label is not None
    assert hud.bitrate_label is not None
    assert hud.frames_label is not None
    assert hud.viewers_label is not None
    hud.show()
    qapp.processEvents()
    hud.close()


def test_hud_window_locking_mode(qapp, tmp_path):
    cfg_file = tmp_path / "hud_test2.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    hud = MiniHudWindow(cfg, cap, style)

    # Lock HUD
    hud.set_locked(True)
    assert hud.is_locked() is True
    assert cfg.settings.hud_locked is True

    # Unlock HUD (Edit mode)
    hud.set_locked(False)
    assert hud.is_locked() is False
    assert cfg.settings.hud_locked is False

    hud.close()


def test_hud_window_stats_update(qapp, tmp_path):
    cfg_file = tmp_path / "hud_test3.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    hud = MiniHudWindow(cfg, cap, style)

    # 1. Test Live Stats
    live_stats = OBSStreamStats(
        is_connected=True,
        is_live=True,
        uptime="01:15:30",
        bitrate_kbps=6000,
        dropped_percent=0.0,
        has_warning=False,
    )
    hud.update_stats(live_stats)
    assert "LIVE" in hud.live_badge.text()
    assert "01:15:30" in hud.uptime_label.text()
    assert "6,000" in hud.bitrate_label.text()
    assert "0.0%" in hud.frames_label.text()

    # 2. Test Warning State (Severe frame drops)
    warning_stats = OBSStreamStats(
        is_connected=True,
        is_live=True,
        uptime="02:00:00",
        bitrate_kbps=4500,
        dropped_frames=120,
        dropped_percent=3.2,
        has_warning=True,
    )
    hud.update_stats(warning_stats)
    assert "120" in hud.frames_label.text()
    assert "3.2%" in hud.frames_label.text()

    # 3. Test Viewers
    hud.update_viewers(1450)
    assert "1,450" in hud.viewers_label.text()

    hud.close()
