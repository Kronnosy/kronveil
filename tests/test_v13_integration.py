"""
End-to-end integration test for Kronos Veil v1.3 Phase 3 components:
Verifies KronosVeilApp orchestration with Q&A Deck, Hype Spike Engine,
GSI / Clutch Manager, MiniHudWindow, OverlayWindow, and Web Companion.
"""

import time
import pytest
from PySide6.QtWidgets import QApplication

from kronos_veil.app import KronosVeilApp
from kronos_veil.chat.base import ChatMessage
from kronos_veil.gsi.models import GameState, MapState, PlayerState, RoundState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_v13_app_orchestration(qapp, tmp_path):
    cfg_file = tmp_path / "app_v13_test.json"

    app = KronosVeilApp(qapp, config_path=str(cfg_file))
    app.settings.gsi_enabled = False  # Keep background port closed for test
    app.settings.web_companion_enabled = False
    app.settings.qa_deck_enabled = True
    app.settings.clutch_mode_enabled = True
    app.settings.clutch_dim_opacity = 0.05
    app.settings.overlay_opacity = 0.90
    qapp.processEvents()

    try:
        # 1. Verify subsystem existence
        assert hasattr(app, "qa_deck")
        assert hasattr(app, "qa_deck_mgr")
        assert hasattr(app, "hype_detector")
        assert hasattr(app, "clutch_manager")
        assert hasattr(app, "gsi_server")

        # 2. Test chat message routing to Q&A Deck and Hype Detector
        question_msg = ChatMessage(
            username="StreamFan",
            message="Will you play competitive CS2 today?",
            platform="twitch",
        )
        app._on_message_received(question_msg)
        qapp.processEvents()

        assert app.qa_deck_mgr.count() == 1
        assert "StreamFan" in [q.author for q in app.qa_deck_mgr.get_all_questions()]
        assert app.qa_deck.count_badge.text() == "1"
        assert app.hype_detector.current_velocity > 0.0

        # 3. Test CS2 GSI state -> HUD updates
        gs = GameState(
            map=MapState(name="de_inferno", team_ct_score=9, team_t_score=6),
            player=PlayerState(activity="playing", health=15),  # <= 25 HP -> triggers clutch!
            round=RoundState(phase="live", bomb="planted"),
        )
        # Process through clutch manager (which evaluates trigger and dispatches to overlay & hud)
        app.clutch_manager.on_game_state(gs)
        app.hud.update_gsi_state(gs)
        qapp.processEvents()

        assert app.hud.cs2_badge.isVisible() is True
        assert app.hud.round_badge.isVisible() is True
        assert app.hud.bomb_badge.isVisible() is True
        assert "💣" in app.hud.bomb_badge.text()
        assert app.clutch_manager.is_clutch_active is True

        # Let opacity animation run
        start_t = time.time()
        while time.time() - start_t < 0.8:
            time.sleep(0.02)
            qapp.processEvents()
            if abs(app.overlay.windowOpacity() - 0.05) <= 0.08:
                break

        assert app.overlay.windowOpacity() == pytest.approx(0.05, abs=0.08)

        # 4. Round ends -> disengage clutch
        gs_over = GameState(
            map=MapState(name="de_inferno", team_ct_score=10, team_t_score=6),
            player=PlayerState(activity="playing", health=15),
            round=RoundState(phase="over", bomb="defused"),
        )
        app.clutch_manager.on_game_state(gs_over)
        app.hud.update_gsi_state(gs_over)
        qapp.processEvents()

        assert app.clutch_manager.is_clutch_active is False
        assert "DEFUSED" in app.hud.bomb_badge.text()

        start_t = time.time()
        while time.time() - start_t < 0.8:
            time.sleep(0.02)
            qapp.processEvents()
            if abs(app.overlay.windowOpacity() - 0.90) <= 0.08:
                break

        assert app.overlay.windowOpacity() == pytest.approx(0.90, abs=0.08)

        # 5. Toggle QA deck visibility
        app.qa_deck.show()
        qapp.processEvents()
        assert app.qa_deck.isVisible() is True

        app._toggle_qa_deck_visibility()
        qapp.processEvents()
        assert app.qa_deck.isVisible() is False

        app._toggle_qa_deck_visibility()
        qapp.processEvents()
        assert app.qa_deck.isVisible() is True

    finally:
        app.shutdown()
