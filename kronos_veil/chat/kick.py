"""
Kick.com Live Chat Provider for Kronos Veil.
Connects directly to Kick's Pusher WebSocket cluster to receive real-time chat messages
without requiring API keys or OAuth authentication for public channels.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import urllib.request
from typing import Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Slot
from PySide6.QtWebSockets import QWebSocket

from kronos_veil.chat.base import ChatMessage, ChatProvider, ChatStatus

logger = logging.getLogger(__name__)

KICK_PUSHER_URL = (
    "wss://ws-us2.pusher.com/app/eb1862ac867114779e47"
    "?protocol=7&client=js&version=7.6.0&flash=false"
)


class KickChatProvider(ChatProvider):
    """
    Live Chat Provider for Kick.com streaming channels.
    Resolves channel slug to chatroom ID and listens on Pusher WebSocket.
    """

    def __init__(
        self,
        channel: str = "",
        chatroom_id: Optional[int] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.channel = channel.strip().lower()
        self.chatroom_id = chatroom_id
        self._ws: Optional[QWebSocket] = None
        self._subscribed = False

    def connect_chat(self) -> None:
        """Starts connection sequence for Kick chat."""
        if not self.channel and not self.chatroom_id:
            logger.warning("KickChatProvider: No channel or chatroom ID specified.")
            self.status = ChatStatus.ERROR
            self.status_changed.emit(self.status.value, "No Kick channel specified.")
            return

        self.status = ChatStatus.CONNECTING
        self.status_changed.emit(self.status.value, f"Connecting to Kick ({self.channel})...")

        # If chatroom ID is already numeric, proceed straight to websocket
        if self.chatroom_id:
            self._start_websocket()
        elif self.channel.isdigit():
            self.chatroom_id = int(self.channel)
            self._start_websocket()
        else:
            # Resolve channel slug in background
            thread = threading.Thread(target=self._resolve_chatroom_id, daemon=True)
            thread.start()

    def _resolve_chatroom_id(self) -> None:
        """Fetches chatroom ID for the given channel slug via Kick API."""
        try:
            url = f"https://kick.com/api/v2/channels/{self.channel}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
                chatroom = data.get("chatroom", {})
                resolved_id = chatroom.get("id")
                if resolved_id:
                    self.chatroom_id = int(resolved_id)
                    logger.info("Resolved Kick channel '%s' to chatroom ID %s", self.channel, self.chatroom_id)
        except Exception as exc:
            logger.warning("Could not resolve Kick chatroom ID via API (%s). Will attempt fallback.", exc)

        # Trigger websocket on Qt thread
        QTimer.singleShot(0, self._start_websocket)

    def _start_websocket(self) -> None:
        """Initializes and connects the QWebSocket instance."""
        if self._ws:
            self._ws.close()
            self._ws.deleteLater()

        self._ws = QWebSocket()
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_message)
        self._ws.errorOccurred.connect(self._on_error)

        logger.info("Opening Kick Pusher WebSocket connection...")
        self._ws.open(QUrl(KICK_PUSHER_URL))

    @Slot()
    def _on_connected(self) -> None:
        logger.info("Kick Pusher WebSocket connected.")
        self.status = ChatStatus.CONNECTED
        self.status_changed.emit(self.status.value, "Connected to Kick Pusher.")
        if self.chatroom_id:
            self._subscribe_to_chatroom(self.chatroom_id)

    def _subscribe_to_chatroom(self, chatroom_id: int) -> None:
        """Sends Pusher subscription payload for the target chatroom."""
        if not self._ws or self._subscribed:
            return

        payload = {
            "event": "pusher:subscribe",
            "data": {
                "auth": "",
                "channel": f"chatrooms.{chatroom_id}.v2",
            },
        }
        self._ws.sendTextMessage(json.dumps(payload))
        self._subscribed = True
        logger.info("Subscribed to Kick chatrooms.%s.v2", chatroom_id)

    @Slot(str)
    def _on_message(self, message: str) -> None:
        """Processes incoming Pusher WebSocket JSON frames."""
        try:
            frame = json.loads(message)
            event_name = frame.get("event", "")

            # Respond to Pusher keep-alive pings
            if event_name == "pusher:ping":
                if self._ws:
                    self._ws.sendTextMessage(json.dumps({"event": "pusher:pong", "data": {}}))
                return

            # If chatroom was resolved late and we haven't subscribed yet
            if not self._subscribed and self.chatroom_id:
                self._subscribe_to_chatroom(self.chatroom_id)

            # Chat message event
            if event_name == "App\\Events\\ChatMessageEvent":
                raw_data = frame.get("data", "{}")
                if isinstance(raw_data, str):
                    chat_data = json.loads(raw_data)
                else:
                    chat_data = raw_data

                content = chat_data.get("content", "")
                sender = chat_data.get("sender", {})
                username = sender.get("username", "Anonymous")
                identity = sender.get("identity", {})
                user_color = identity.get("color") or "#53fc18"  # Kick Signature Green default

                badges = []
                for b in identity.get("badges", []):
                    b_type = b.get("type")
                    if b_type:
                        badges.append(b_type)

                msg = ChatMessage(
                    username=username,
                    message=content,
                    color=user_color,
                    badges=badges,
                    platform="kick",
                )
                self.message_received.emit(msg)

        except Exception as exc:
            logger.debug("Error processing Kick WebSocket frame: %s", exc)

    @Slot()
    def _on_disconnected(self) -> None:
        logger.info("Kick Pusher WebSocket disconnected.")
        self._subscribed = False
        self.status = ChatStatus.DISCONNECTED
        self.status_changed.emit(self.status.value, "Disconnected from Kick.")

    @Slot(object)
    def _on_error(self, error: object) -> None:
        logger.error("Kick Pusher WebSocket error: %s", error)
        self.status = ChatStatus.ERROR
        self.status_changed.emit(self.status.value, f"Kick error: {error}")

    def disconnect_chat(self) -> None:
        """Closes the WebSocket connection gracefully."""
        self._subscribed = False
        if self._ws:
            self._ws.close()
            self._ws.deleteLater()
            self._ws = None
        self.status = ChatStatus.DISCONNECTED
        self.status_changed.emit(self.status.value, "Disconnected.")

    def is_connected(self) -> bool:
        return self.status == ChatStatus.CONNECTED
