"""
Unit tests for MiniHudWindow CS2 GSI, bomb timer countdown, and hype indicator rendering.
"""

import time
import pytest
from PySide6.QtWidgets import QApplication

from kronos_veil.config import ConfigManager
from kronos_veil.gsi.models import GameState, MapState, PlayerState, RoundState
from kronos_veil.hud import MiniHudWindow
from kronos_veil.toast import ToastNotification, ToastWindow
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_hud_gsi_state_rendering(qapp, tmp_path):
    cfg_file = tmp_path / "hud_gsi.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    hud = MiniHudWindow(cfg, cap, style)
    hud.show()
    qapp.processEvents()

    # Initially CS2 badges should be hidden
    assert hud.cs2_badge.isHidden() is True
    assert hud.round_badge.isHidden() is True
    assert hud.bomb_badge.isHidden() is True

    # Ingest GameState: in match, bomb planted
    gs = GameState(
        map=MapState(name="de_mirage", team_ct_score=7, team_t_score=8),
        player=PlayerState(activity="playing", health=80),
        round=RoundState(phase="live", bomb="planted"),
    )
    hud.update_gsi_state(gs)
    qapp.processEvents()

    assert hud.cs2_badge.isVisible() is True
    assert hud.round_badge.isVisible() is True
    assert "T 8 - 7 CT" in hud.round_badge.text()
    assert hud.bomb_badge.isVisible() is True
    assert "💣" in hud.bomb_badge.text()
    assert hud._bomb_timer.isActive() is True

    # Test bomb ticking
    time.sleep(0.15)
    qapp.processEvents()
    assert hud._bomb_remaining < 40.0

    # Ingest defused state
    gs_defused = GameState(
        map=MapState(name="de_mirage", team_ct_score=7, team_t_score=8),
        player=PlayerState(activity="playing", health=80),
        round=RoundState(phase="over", bomb="defused"),
    )
    hud.update_gsi_state(gs_defused)
    qapp.processEvents()
    assert "DEFUSED" in hud.bomb_badge.text()
    assert hud._bomb_timer.isActive() is False

    # Ingest out of game state
    gs_menu = GameState(
        player=PlayerState(activity="menu", health=0),
    )
    hud.update_gsi_state(gs_menu)
    qapp.processEvents()
    assert hud.cs2_badge.isHidden() is True
    assert hud.round_badge.isHidden() is True
    assert hud.bomb_badge.isHidden() is True

    hud.close()


def test_hud_hype_indicator_and_toast(qapp, tmp_path):
    cfg_file = tmp_path / "hud_hype.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    hud = MiniHudWindow(cfg, cap, style)
    toast = ToastNotification(cfg, cap, style)
    hud.show()
    toast.show()
    qapp.processEvents()

    # 1. Hype below threshold -> badge hidden
    hud.update_hype(0.4, is_spike=False)
    assert hud.hype_badge.isHidden() is True

    # 2. Hype active -> badge shown
    hud.update_hype(2.5, is_spike=False)
    assert hud.hype_badge.isVisible() is True
    assert "2.5/s" in hud.hype_badge.text()

    # 3. Hype spike -> badge colored in red + toast notification
    hud.update_hype(4.8, is_spike=True)
    assert hud.hype_badge.isVisible() is True
    assert "4.8/s" in hud.hype_badge.text()

    toast.show_toast(
        title="🔥 HYPE SPIKE!",
        message="Hype velocity reached 4.8 msgs/s!",
        icon="🔥",
        level="hype",
    )
    qapp.processEvents()
    assert toast.isVisible() is True
    assert "HYPE SPIKE" in toast.title_label.text()
    assert toast.icon_label.text() == "🔥"

    hud.close()
    toast.close()
