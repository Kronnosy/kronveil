"""Unified Multistream Chat Provider for Kronos Veil.

Aggregates multiple chat feeds (Twitch, Kick, YouTube, Demo) into a single,
synchronized stream with platform tagging and lifecycle orchestration.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Slot

from kronos_veil.chat.base import ChatMessage, ChatProvider, ChatStatus
from kronos_veil.chat.demo import DemoChatProvider
from kronos_veil.chat.kick import KickChatProvider
from kronos_veil.chat.twitch import TwitchChatProvider
from kronos_veil.chat.youtube import YouTubeChatProvider
from kronos_veil.config import AppSettings

logger = logging.getLogger("KronosVeil.UnifiedChat")


class UnifiedChatProvider(ChatProvider):
    """Orchestrates multiple concurrent chat providers and unifies their feeds."""

    def __init__(self, settings: AppSettings, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.providers: Dict[str, ChatProvider] = {}
        self._provider_statuses: Dict[str, ChatStatus] = {}

    def setup_providers(self) -> None:
        """Instantiate configured providers based on application settings."""
        self.disconnect_chat()
        self.providers.clear()
        self._provider_statuses.clear()

        # Check which providers should be active
        if not self.settings.multistream_enabled:
            # Single provider mode (legacy/default)
            p_type = self.settings.chat_provider
            if p_type == "twitch":
                self._add_provider("twitch", TwitchChatProvider(self.settings.twitch_channel))
            elif p_type == "kick":
                self._add_provider("kick", KickChatProvider(self.settings.kick_channel))
            elif p_type == "youtube":
                self._add_provider("youtube", YouTubeChatProvider(self.settings.youtube_video_id))
            else:
                self._add_provider("demo", DemoChatProvider())
            return

        # Multistream Mode: activate any selected platform that has a channel configured
        has_any = False
        if self.settings.multistream_twitch:
            ch = self.settings.twitch_channel.strip()
            self._add_provider("twitch", TwitchChatProvider(ch))
            has_any = True

        if self.settings.multistream_kick:
            kch = self.settings.kick_channel.strip()
            self._add_provider("kick", KickChatProvider(kch))
            has_any = True

        if self.settings.multistream_youtube:
            vid = self.settings.youtube_video_id.strip()
            self._add_provider("youtube", YouTubeChatProvider(vid))
            has_any = True

        if not has_any:
            # Fallback to demo if nothing configured in multistream
            self._add_provider("demo", DemoChatProvider())

    def _add_provider(self, key: str, provider: ChatProvider) -> None:
        """Register a child provider and bind its signals."""
        self.providers[key] = provider
        self._provider_statuses[key] = ChatStatus.DISCONNECTED

        provider.message_received.connect(self._on_child_message)
        provider.status_changed.connect(lambda st, det, k=key: self._on_child_status(k, st, det))

    @Slot(ChatMessage)
    def _on_child_message(self, msg: ChatMessage) -> None:
        """Forward child message to unified listener."""
        self.message_received.emit(msg)

    def _on_child_status(self, key: str, status_str: str, detail: str) -> None:
        """Aggregate status across all active child providers."""
        try:
            self._provider_statuses[key] = ChatStatus(status_str)
        except ValueError:
            self._provider_statuses[key] = ChatStatus.ERROR

        # Derive overall status
        statuses = list(self._provider_statuses.values())
        if any(s == ChatStatus.CONNECTED for s in statuses):
            self.status = ChatStatus.CONNECTED
        elif any(s == ChatStatus.CONNECTING for s in statuses):
            self.status = ChatStatus.CONNECTING
        elif any(s == ChatStatus.ERROR for s in statuses):
            self.status = ChatStatus.ERROR
        else:
            self.status = ChatStatus.DISCONNECTED

        active_connected = [k for k, st in self._provider_statuses.items() if st == ChatStatus.CONNECTED]
        summary = f"Multistream ({', '.join(active_connected)})" if active_connected else detail
        self.status_changed.emit(self.status.value, summary)

    def connect_chat(self) -> None:
        """Connect all registered providers."""
        if not self.providers:
            self.setup_providers()

        for key, p in self.providers.items():
            try:
                p.connect_chat()
            except Exception as exc:
                logger.error("Failed to connect %s chat: %s", key, exc)

    def disconnect_chat(self) -> None:
        """Disconnect all child providers."""
        for key, p in list(self.providers.items()):
            try:
                p.disconnect_chat()
            except Exception as exc:
                logger.debug("Error disconnecting %s provider: %s", key, exc)
        self.status = ChatStatus.DISCONNECTED
        self.status_changed.emit(ChatStatus.DISCONNECTED.value, "All chats disconnected")

    def send_test_message(
        self,
        username: str = "TestViewer",
        text: str = "Hello from unified multistream! Pog",
        platform: str = "twitch",
    ) -> None:
        """Inject a test message across the unified pipeline."""
        msg = ChatMessage(
            username=username,
            message=text,
            platform=platform,
            is_test=True,
        )
        self.message_received.emit(msg)
