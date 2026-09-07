"""
Twitch IRC Chat Provider for Kronos Veil.
Connects directly to Twitch IRC over SSL to receive live chat messages.
Supports anonymous read-only mode (justinfan) without requiring OAuth tokens or API keys.
"""

from __future__ import annotations

import logging
import random
import re
import socket
import ssl
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject

from kronos_veil.chat.base import ChatMessage, ChatProvider, ChatStatus

logger = logging.getLogger(__name__)

TWITCH_IRC_HOST = "irc.chat.twitch.tv"
TWITCH_IRC_PORT = 6697


class TwitchChatProvider(ChatProvider):
    """
    Connects to Twitch IRC using SSL sockets.
    Can operate anonymously with standard 'justinfan' credentials for public channels.
    """

    def __init__(
        self,
        channel: str = "",
        oauth_token: Optional[str] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.channel = channel.strip().lower().lstrip("#")
        self.oauth_token = oauth_token
        self._running = False
        self._socket: Optional[ssl.SSLSocket] = None
        self._thread: Optional[threading.Thread] = None

    def set_channel(self, channel: str) -> None:
        new_channel = channel.strip().lower().lstrip("#")
        if self.channel != new_channel:
            self.channel = new_channel
            if self.is_connected():
                # Reconnect to new channel
                self.disconnect_chat()
                self.connect_chat()

    def connect_chat(self) -> None:
        if not self.channel:
            self.status = ChatStatus.ERROR
            self.status_changed.emit(ChatStatus.ERROR.value, "No Twitch channel specified.")
            return

        if self._running:
            return

        self._running = True
        self.status = ChatStatus.CONNECTING
        self.status_changed.emit(ChatStatus.CONNECTING.value, f"Connecting to Twitch #{self.channel}...")

        self._thread = threading.Thread(target=self._connection_worker, daemon=True, name="KV-TwitchIRC")
        self._thread.start()

    def disconnect_chat(self) -> None:
        self._running = False
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

        self.status = ChatStatus.DISCONNECTED
        self.status_changed.emit(ChatStatus.DISCONNECTED.value, "Twitch chat disconnected.")

    def is_connected(self) -> bool:
        return self._running and self.status == ChatStatus.CONNECTED

    def _connection_worker(self) -> None:
        """Worker thread loop managing IRC SSL connection and incoming message parser."""
        while self._running:
            try:
                raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                raw_sock.settimeout(10.0)
                context = ssl.create_default_context()
                self._socket = context.wrap_socket(raw_sock, server_hostname=TWITCH_IRC_HOST)
                self._socket.connect((TWITCH_IRC_HOST, TWITCH_IRC_PORT))

                # Identify
                if self.oauth_token:
                    token = self.oauth_token if self.oauth_token.startswith("oauth:") else f"oauth:{self.oauth_token}"
                    nick = "oauth_user"
                else:
                    # Standard anonymous viewer
                    token = "SCHMOOPIIE"
                    nick = f"justinfan{random.randint(10000, 99999)}"

                self._send_raw(f"PASS {token}")
                self._send_raw(f"NICK {nick}")
                # Request IRC tags (colors, display names, badges)
                self._send_raw("CAP REQ :twitch.tv/tags twitch.tv/commands")
                self._send_raw(f"JOIN #{self.channel}")

                self.status = ChatStatus.CONNECTED
                self.status_changed.emit(ChatStatus.CONNECTED.value, f"Connected to #{self.channel}")
                logger.info("Successfully connected to Twitch IRC #{%s}", self.channel)

                buffer = ""
                self._socket.settimeout(300.0)  # Twitch PINGs roughly every 5 minutes

                while self._running:
                    try:
                        data = self._socket.recv(4096).decode("utf-8", errors="ignore")
                    except socket.timeout:
                        # Send PING if idle
                        self._send_raw("PING :tmi.twitch.tv")
                        continue

                    if not data:
                        break

                    buffer += data
                    lines = buffer.split("\r\n")
                    buffer = lines.pop()

                    for line in lines:
                        if not line:
                            continue
                        self._handle_irc_line(line)

            except Exception as e:
                if not self._running:
                    break
                logger.warning("Twitch connection interrupted: %s. Reconnecting in 5 seconds...", e)
                self.status = ChatStatus.CONNECTING
                self.status_changed.emit(ChatStatus.CONNECTING.value, f"Reconnecting to #{self.channel}...")
                time.sleep(5.0)

        self.status = ChatStatus.DISCONNECTED

    def _send_raw(self, message: str) -> None:
        if self._socket:
            try:
                self._socket.sendall(f"{message}\r\n".encode("utf-8"))
            except Exception as e:
                logger.error("Failed to send raw IRC message: %s", e)

    def _handle_irc_line(self, line: str) -> None:
        # Handle Keepalive
        if line.startswith("PING"):
            pong = line.replace("PING", "PONG", 1)
            self._send_raw(pong)
            return

        # Parse PRIVMSG: @tags :user!user@user.tmi.twitch.tv PRIVMSG #channel :message
        if "PRIVMSG" in line:
            try:
                tags_part = ""
                rest = line
                if line.startswith("@"):
                    tags_part, rest = line[1:].split(" ", 1)

                tags_dict = {}
                if tags_part:
                    for item in tags_part.split(";"):
                        if "=" in item:
                            k, v = item.split("=", 1)
                            tags_dict[k] = v

                # Match prefix and message content
                match = re.search(r":([^!]+)![^ ]+ PRIVMSG #[^ ]+ :(.*)", rest)
                if match:
                    raw_user = match.group(1)
                    message_text = match.group(2)

                    display_name = tags_dict.get("display-name") or raw_user
                    color = tags_dict.get("color")
                    if not color or not color.startswith("#"):
                        # Assign stable color derived from username hash
                        color = self._get_fallback_color(raw_user)

                    badges_raw = tags_dict.get("badges", "")
                    badges = [b.split("/")[0] for b in badges_raw.split(",") if b]

                    chat_msg = ChatMessage(
                        username=display_name,
                        message=message_text,
                        color=color,
                        badges=badges,
                    )
                    self.message_received.emit(chat_msg)
            except Exception as e:
                logger.debug("Failed parsing IRC line: %s (%s)", line, e)

    @staticmethod
    def _get_fallback_color(name: str) -> str:
        palette = [
            "#ff4500", "#00ff7f", "#1e90ff", "#ff69b4", "#00ffff",
            "#ffd700", "#ff1493", "#adff2f", "#ba55d3", "#00fa9a",
        ]
        val = sum(ord(c) for c in name)
        return palette[val % len(palette)]
