"""Tests for Smart Chat Filters Engine."""

import time

from kronos_veil.chat.base import ChatMessage
from kronos_veil.chat.filters import ChatFilterEngine


def test_bot_command_detection():
    engine = ChatFilterEngine()

    assert engine.is_bot_command("!sens") is True
    assert engine.is_bot_command("/me is happy") is True
    assert engine.is_bot_command(".points") is True
    assert engine.is_bot_command("$gamble 100") is True

    assert engine.is_bot_command("Hello streamer!") is False
    assert engine.is_bot_command("great game! congrats!") is False
    assert engine.is_bot_command("") is False


def test_duplicate_spam_detection():
    engine = ChatFilterEngine(duplicate_window_sec=1.5)

    # First message: allowed
    assert engine.is_duplicate_spam("SpamUser", "gg wp") is False
    # Immediately repeated: duplicate
    assert engine.is_duplicate_spam("SpamUser", "gg wp") is True
    assert engine.is_duplicate_spam("SpamUser", "GG WP") is True

    # Different user: allowed
    assert engine.is_duplicate_spam("OtherUser", "gg wp") is False

    # Wait for window to expire
    time.sleep(1.6)
    assert engine.is_duplicate_spam("SpamUser", "gg wp") is False


def test_streamer_mention_detection():
    engine = ChatFilterEngine()

    assert engine.is_mention("Hey @Shroud what sensitivity do you use?", "Shroud") is True
    assert engine.is_mention("shroud is the best player", "shroud") is True
    assert engine.is_mention("hello everyone", "shroud") is False


def test_should_display_policy():
    engine = ChatFilterEngine(duplicate_window_sec=2.0)

    # System/test message always passes
    sys_msg = ChatMessage(message="!test", is_system=True)
    assert engine.should_display(sys_msg, filter_bot_commands=True) is True

    # Bot command message
    bot_msg = ChatMessage(username="viewer1", message="!discord")
    assert engine.should_display(bot_msg, filter_bot_commands=True) is False
    assert engine.should_display(bot_msg, filter_bot_commands=False) is True

    # Duplicate spam
    chat_msg1 = ChatMessage(username="viewer2", message="Clutch or kick")
    assert engine.should_display(chat_msg1, filter_duplicates=True) is True

    chat_msg2 = ChatMessage(username="viewer2", message="Clutch or kick")
    assert engine.should_display(chat_msg2, filter_duplicates=True) is False
