"""
Unit tests for Capture-Protected Smart Q&A Deck Window.
Tests widget lifecycle, question card actions (answered/dismiss), locking/edit mode,
and capture protection / window flags.
"""

import pytest
from PySide6.QtWidgets import QApplication

from kronos_veil.chat.questions import QuestionDeckManager, QuestionItem
from kronos_veil.config import ConfigManager
from kronos_veil.question_deck import QuestionCardWidget, QuestionDeckWindow
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_question_card_widget(qapp):
    item = QuestionItem(
        id="q-101",
        author="TwitchFan",
        text="What crosshair code are you using?",
        platform="twitch",
        timestamp="15:30:00",
    )
    card = QuestionCardWidget(item)

    assert "TWITCH" in card.platform_badge.text() or "TWI" in card.platform_badge.text()
    assert "TwitchFan" in card.author_label.text()
    assert "crosshair" in card.text_label.text()
    assert card.answer_btn.isEnabled() is True

    # Test answered click signal
    answered_ids = []
    card.answered_clicked.connect(answered_ids.append)
    card.answer_btn.click()
    assert answered_ids == ["q-101"]

    # Test update item to answered
    item.is_answered = True
    card.update_item(item)
    assert card.answer_btn.isEnabled() is False
    assert "Done" in card.answer_btn.text()

    # Test dismiss click signal
    dismissed_ids = []
    card.dismiss_clicked.connect(dismissed_ids.append)
    card.dismiss_btn.click()
    assert dismissed_ids == ["q-101"]

    card.close()


def test_question_deck_window_lifecycle(qapp, tmp_path):
    cfg_file = tmp_path / "qa_test.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()
    style = WindowStyleManager()
    deck_mgr = QuestionDeckManager()

    deck_win = QuestionDeckWindow(cfg, cap, style, deck_mgr=deck_mgr)
    deck_win.show()
    qapp.processEvents()

    assert deck_win.isVisible() is True
    assert deck_win.is_locked() is False
    assert deck_win.count_badge.text() == "0"
    assert deck_win.empty_label.isVisible() is True

    # Add question through deck manager
    q1 = QuestionItem(id="q-1", author="ProPlayer", text="Are you streaming tomorrow?", platform="kick")
    deck_mgr.add_question(q1)
    qapp.processEvents()

    assert deck_win.count_badge.text() == "1"
    assert deck_win.empty_label.isVisible() is False
    assert "q-1" in deck_win._cards

    # Mark question answered
    deck_win._cards["q-1"].answer_btn.click()
    qapp.processEvents()
    assert q1.is_answered is True

    # Add second question
    q2 = QuestionItem(id="q-2", author="Viewer2", text="What is your DPI?", platform="youtube")
    deck_mgr.add_question(q2)
    qapp.processEvents()
    assert "q-2" in deck_win._cards

    # Dismiss second question
    deck_win._cards["q-2"].dismiss_btn.click()
    qapp.processEvents()
    assert q2.is_dismissed is True

    # Test Lock / Unlock
    mode_events = []
    deck_win.mode_changed.connect(mode_events.append)
    deck_win.set_locked(True)
    assert deck_win.is_locked() is True
    assert cfg.settings.qa_deck_locked is True
    assert len(mode_events) == 1 and mode_events[0] is True
    assert deck_win.edit_grip_label.isHidden() is True
    assert deck_win.lock_btn.isHidden() is True

    deck_win.set_locked(False)
    assert deck_win.is_locked() is False
    assert cfg.settings.qa_deck_locked is False

    # Test clear button
    deck_win.clear_btn.click()
    qapp.processEvents()
    assert deck_mgr.count() == 0
    assert len(deck_win._cards) == 0
    assert deck_win.count_badge.text() == "0"
    assert deck_win.empty_label.isVisible() is True

    deck_win.close()
