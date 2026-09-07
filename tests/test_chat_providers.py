"""Unit tests for chat providers and message structures."""

import pytest
from PySide6.QtCore import QCoreApplication
from kronos_veil.chat.base import ChatMessage, ChatStatus
from kronos_veil.chat.demo import DemoChatProvider
from kronos_veil.chat.twitch import TwitchChatProvider
from kronos_veil.chat.youtube import YouTubeChatProvider




def test_chat_message_creation():
    msg = ChatMessage(username="StreamerHero", message="Hello world!", color="#ff00ff")
    assert msg.username == "StreamerHero"
    assert msg.message == "Hello world!"
    assert msg.color == "#ff00ff"
    assert msg.timestamp is not None
    assert msg.is_system is False


def test_demo_provider_manual_message(qapp):
    provider = DemoChatProvider()
    received = []
    provider.message_received.connect(received.append)

    msg = provider.send_manual_message("Manual test line", username="Tester", color="#00ff00")
    assert len(received) == 1
    assert received[0].message == "Manual test line"
    assert received[0].username == "Tester"


def test_demo_provider_random_generation(qapp):
    provider = DemoChatProvider()
    msg = provider.generate_random_message()
    assert msg.username != ""
    assert msg.message != ""
    assert msg.color.startswith("#")


def test_twitch_irc_parsing(qapp):
    provider = TwitchChatProvider(channel="shroud")
    received = []
    provider.message_received.connect(received.append)

    # Simulated Twitch IRC line with badges and hex color
    line = "@badge-info=;badges=subscriber/12,premium/1;color=#1E90FF;display-name=GamerFan;emotes=;mod=0;room-id=123;subscriber=1;user-id=456 :gamerfan!gamerfan@gamerfan.tmi.twitch.tv PRIVMSG #shroud :Insane shot!"
    provider._handle_irc_line(line)

    assert len(received) == 1
    assert received[0].username == "GamerFan"
    assert received[0].message == "Insane shot!"
    assert received[0].color == "#1E90FF"
    assert "subscriber" in received[0].badges


def test_youtube_missing_credentials_status(qapp):
    provider = YouTubeChatProvider(video_id="")
    status_updates = []
    provider.status_changed.connect(lambda s, d: status_updates.append((s, d)))

    provider.connect_chat()
    assert len(status_updates) == 1
    assert status_updates[0][0] == ChatStatus.ERROR.value
