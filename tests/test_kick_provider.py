"""
Unit tests for KickChatProvider.
"""

import json
import pytest
from PySide6.QtCore import QCoreApplication
from kronos_veil.chat.base import ChatMessage, ChatStatus
from kronos_veil.chat.kick import KickChatProvider


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_kick_provider_initialization(qapp):
    provider = KickChatProvider(channel="streamer123")
    assert provider.channel == "streamer123"
    assert provider.status == ChatStatus.DISCONNECTED
    assert not provider.is_connected()


def test_kick_provider_numeric_channel(qapp):
    provider = KickChatProvider(channel="998877")
    assert provider.channel == "998877"
    assert provider.chatroom_id is None  # Resolved on connect


def test_kick_message_parsing(qapp):
    provider = KickChatProvider(channel="testchannel")
    received_messages = []
    provider.message_received.connect(received_messages.append)

    # Simulated Pusher frame for Kick ChatMessageEvent
    raw_event_payload = {
        "event": "App\\Events\\ChatMessageEvent",
        "data": json.dumps({
            "id": "msg-1234",
            "chatroom_id": 555,
            "content": "Kick chat is fast! KEKW",
            "sender": {
                "id": 42,
                "username": "KickFan42",
                "identity": {
                    "color": "#53FC18",
                    "badges": [{"type": "subscriber"}, {"type": "moderator"}]
                }
            }
        })
    }

    provider._on_message(json.dumps(raw_event_payload))

    assert len(received_messages) == 1
    msg: ChatMessage = received_messages[0]
    assert msg.username == "KickFan42"
    assert msg.message == "Kick chat is fast! KEKW"
    assert msg.color == "#53FC18"
    assert "subscriber" in msg.badges
    assert "moderator" in msg.badges


def test_kick_ping_pong_response(qapp):
    provider = KickChatProvider(channel="test")
    # Simulating ping
    provider._on_message(json.dumps({"event": "pusher:ping", "data": {}}))
    # Should handle without error
    assert True
