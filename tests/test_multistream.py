"""Tests for Unified Multistream Chat Provider."""

from unittest.mock import MagicMock

from kronos_veil.chat.aggregator import UnifiedChatProvider
from kronos_veil.chat.base import ChatMessage, ChatStatus
from kronos_veil.config import AppSettings


def test_unified_chat_provider_initialization():
    settings = AppSettings()
    settings.multistream_enabled = False
    provider = UnifiedChatProvider(settings)

    provider.setup_providers()
    assert len(provider.providers) == 1
    assert "demo" in provider.providers


def test_unified_chat_provider_multistream_setup():
    settings = AppSettings()
    settings.multistream_enabled = True
    settings.multistream_twitch = True
    settings.twitch_channel = "shroud"
    settings.multistream_kick = True
    settings.kick_channel = "xqc"
    settings.multistream_youtube = True
    settings.youtube_video_id = "test_vid"

    provider = UnifiedChatProvider(settings)
    provider.setup_providers()

    assert "twitch" in provider.providers
    assert "kick" in provider.providers
    assert "youtube" in provider.providers
    assert len(provider.providers) == 3


def test_unified_chat_message_forwarding():
    settings = AppSettings()
    settings.multistream_enabled = True
    settings.multistream_twitch = True
    settings.twitch_channel = "testchannel"

    provider = UnifiedChatProvider(settings)
    provider.setup_providers()

    received_messages = []
    provider.message_received.connect(lambda msg: received_messages.append(msg))

    # Send test message through aggregator
    provider.send_test_message(username="TwitchViewer", text="Awesome stream!", platform="twitch")

    assert len(received_messages) == 1
    assert received_messages[0].username == "TwitchViewer"
    assert received_messages[0].platform == "twitch"
    assert received_messages[0].message == "Awesome stream!"


def test_unified_status_aggregation():
    settings = AppSettings()
    settings.multistream_enabled = True
    provider = UnifiedChatProvider(settings)
    provider.setup_providers()

    status_events = []
    provider.status_changed.connect(lambda st, det: status_events.append((st, det)))

    provider._on_child_status("twitch", "CONNECTED", "Twitch SSL connected")
    assert provider.status == ChatStatus.CONNECTED
    assert len(status_events) > 0
    assert "Multistream (twitch)" in status_events[-1][1]
