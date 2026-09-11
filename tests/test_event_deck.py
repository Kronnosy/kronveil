"""
Unit tests for Stream Events Deck and EventService.
"""

import pytest
from kronos_veil.config import ConfigManager
from kronos_veil.event_deck import (
    EventDeckWindow,
    EventService,
    GoalProgress,
    StreamEvent,
)
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager


def test_stream_event_formatting():
    ev_follow = StreamEvent(event_type="follower", username="Valkyrie")
    assert "Follow" in ev_follow.display_text()
    assert "Valkyrie" in ev_follow.display_text()

    ev_sub = StreamEvent(event_type="sub", username="Krom")
    assert "Sub" in ev_sub.display_text()

    ev_bits = StreamEvent(event_type="bits", username="Gamer", amount="500")
    assert "500" in ev_bits.display_text()

    ev_tip = StreamEvent(event_type="tip", username="Supporter", amount="20.00")
    assert "$20.00" in ev_tip.display_text()


def test_goal_progress():
    goal = GoalProgress(title="Sub Goal", current=15, target=20)
    assert goal.percentage == 75

    zero_target = GoalProgress(target=0)
    assert zero_target.percentage == 100


def test_event_deck_window_lifecycle(qapp, tmp_path):
    cfg_file = tmp_path / "settings.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    deck = EventDeckWindow(cfg, cap, style)
    deck.show()

    assert deck.isVisible() is True
    assert deck.is_locked() is False

    # Simulate an incoming event
    received_events = []
    deck.event_service.event_received.connect(lambda ev: received_events.append(ev))
    deck.event_service.simulate_event("sub", "PrimeUser")

    assert len(received_events) == 1
    assert "PrimeUser" in deck.event_chip.text()

    # Toggle lock mode
    deck.set_locked(True)
    assert deck.is_locked() is True
    assert deck.edit_grip_label.isHidden() is True

    deck.close()
