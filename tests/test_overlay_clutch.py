"""
Unit tests for OverlayWindow clutch mode opacity animation and transitions.
"""

import time
import pytest
from PySide6.QtWidgets import QApplication

from kronos_veil.config import ConfigManager
from kronos_veil.gsi.clutch_manager import ClutchManager
from kronos_veil.overlay import OverlayWindow
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_overlay_clutch_opacity_animation(qapp, tmp_path):
    cfg_file = tmp_path / "overlay_clutch.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cfg.settings.overlay_opacity = 0.90
    cfg.settings.clutch_dim_opacity = 0.0

    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    overlay = OverlayWindow(cfg, cap, style)
    overlay.show()
    qapp.processEvents()

    assert overlay.windowOpacity() == pytest.approx(0.90, abs=0.01)

    # Animate down to clutch dim opacity (0.0) with short duration for test
    overlay.animate_clutch_opacity(0.0, duration_ms=100)
    assert overlay._is_clutch_dimmed is True

    # Process events to let animation run
    for _ in range(15):
        time.sleep(0.02)
        qapp.processEvents()

    assert overlay.windowOpacity() == pytest.approx(0.0, abs=0.05)

    # Animate back up to normal opacity (0.90)
    overlay.on_clutch_opacity_changed(0.90)
    assert overlay._is_clutch_dimmed is False

    for _ in range(15):
        time.sleep(0.02)
        qapp.processEvents()

    assert overlay.windowOpacity() == pytest.approx(0.90, abs=0.05)

    overlay.close()


def test_overlay_clutch_manager_signal_integration(qapp, tmp_path):
    cfg_file = tmp_path / "clutch_integration.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cfg.settings.overlay_opacity = 0.85
    cfg.settings.clutch_dim_opacity = 0.10

    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    overlay = OverlayWindow(cfg, cap, style)
    overlay.show()
    qapp.processEvents()

    clutch_mgr = ClutchManager(settings=cfg.settings)
    clutch_mgr.opacity_target_changed.connect(overlay.on_clutch_opacity_changed)

    # Engage clutch manually via manager
    clutch_mgr._engage_clutch("low_health")
    assert overlay._clutch_anim is not None

    for _ in range(15):
        time.sleep(0.02)
        qapp.processEvents()

    assert overlay.windowOpacity() == pytest.approx(0.10, abs=0.05)

    # Disengage clutch
    clutch_mgr._disengage_clutch("round_over")
    for _ in range(15):
        time.sleep(0.02)
        qapp.processEvents()

    assert overlay.windowOpacity() == pytest.approx(0.85, abs=0.05)

    overlay.close()
