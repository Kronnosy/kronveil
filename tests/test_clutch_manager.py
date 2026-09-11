"""
Unit tests for CS2 Clutch Mode Manager state transitions and auto-dimming logic.
"""

import pytest
from PySide6.QtCore import QCoreApplication

from kronos_veil.config import AppSettings
from kronos_veil.gsi.clutch_manager import ClutchManager, ClutchState
from kronos_veil.gsi.models import GameState, MapState, PlayerState, RoundState


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def create_mock_game_state(
    in_game: bool = True,
    alive: bool = True,
    health: int = 100,
    round_phase: str = "live",
    bomb: str = "",
) -> GameState:
    """Helper to generate targeted GameState fixtures."""
    return GameState(
        map=MapState(name="de_dust2" if in_game else "", mode="competitive"),
        player=PlayerState(
            activity="playing" if in_game else "menu",
            health=health if alive else 0,
        ),
        round=RoundState(phase=round_phase, bomb=bomb if bomb else None),
    )


def test_clutch_manager_initial_state(qapp):
    settings = AppSettings(overlay_opacity=0.9, clutch_dim_opacity=0.0)
    mgr = ClutchManager(settings=settings)

    assert mgr.state == ClutchState.IDLE
    assert not mgr.is_clutch_active
    assert mgr._current_opacity_target == 0.9


def test_clutch_trigger_low_health(qapp):
    settings = AppSettings(
        clutch_mode_enabled=True,
        overlay_opacity=0.95,
        clutch_dim_opacity=0.05,
        clutch_health_threshold=25,
    )
    mgr = ClutchManager(settings=settings)

    started_events = []
    opacity_events = []
    mgr.clutch_started.connect(started_events.append)
    mgr.opacity_target_changed.connect(opacity_events.append)

    # 1. Normal in-game combat at 100 HP
    mgr.on_game_state(create_mock_game_state(health=100, round_phase="live"))
    assert mgr.state == ClutchState.COMBAT
    assert not mgr.is_clutch_active
    assert len(started_events) == 0

    # 2. HP drops to 20 (<= 25) -> Clutch triggers!
    mgr.on_game_state(create_mock_game_state(health=20, round_phase="live"))
    assert mgr.state == ClutchState.CLUTCH
    assert mgr.is_clutch_active
    assert started_events == ["low_health"]
    assert opacity_events[-1] == 0.05

    # 3. Round ends -> Disengage
    ended_events = []
    mgr.clutch_ended.connect(ended_events.append)

    mgr.on_game_state(create_mock_game_state(health=20, round_phase="over"))
    assert mgr.state == ClutchState.ROUND_OVER
    assert not mgr.is_clutch_active
    assert ended_events == ["round_over"]
    assert opacity_events[-1] == 0.95


def test_clutch_trigger_bomb_planted_and_player_death(qapp):
    settings = AppSettings(
        clutch_mode_enabled=True,
        overlay_opacity=0.95,
        clutch_dim_opacity=0.0,
    )
    mgr = ClutchManager(settings=settings)

    started_events = []
    ended_events = []
    opacity_events = []
    mgr.clutch_started.connect(started_events.append)
    mgr.clutch_ended.connect(ended_events.append)
    mgr.opacity_target_changed.connect(opacity_events.append)

    # 1. Bomb is planted while player is alive at full HP
    mgr.on_game_state(create_mock_game_state(health=100, round_phase="live", bomb="planted"))
    assert mgr.state == ClutchState.CLUTCH
    assert mgr.is_clutch_active
    assert started_events == ["bomb_planted"]
    assert opacity_events[-1] == 0.0

    # 2. Player dies during the clutch
    mgr.on_game_state(create_mock_game_state(alive=False, health=0, round_phase="live", bomb="planted"))
    assert mgr.state == ClutchState.COMBAT
    assert not mgr.is_clutch_active
    assert ended_events == ["player_death"]
    assert opacity_events[-1] == 0.95


def test_clutch_disabled_setting_behavior(qapp):
    settings = AppSettings(clutch_mode_enabled=False)
    mgr = ClutchManager(settings=settings)

    started_events = []
    mgr.clutch_started.connect(started_events.append)

    # Try low health and bomb planted with clutch mode turned off
    mgr.on_game_state(create_mock_game_state(health=15, round_phase="live", bomb="planted"))
    assert mgr.state == ClutchState.IDLE
    assert not mgr.is_clutch_active
    assert len(started_events) == 0


def test_clutch_reset(qapp):
    settings = AppSettings(clutch_dim_opacity=0.0, overlay_opacity=0.95)
    mgr = ClutchManager(settings=settings)

    mgr.on_game_state(create_mock_game_state(health=10, round_phase="live"))
    assert mgr.state == ClutchState.CLUTCH

    mgr.reset()
    assert mgr.state == ClutchState.IDLE
    assert not mgr.is_clutch_active
    assert mgr._current_opacity_target == 0.95
