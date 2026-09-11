"""
YouTube Live Chat Provider for Kronos Veil.
Implements connection to YouTube Data API v3 liveChatMessages endpoint.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

from PySide6.QtCore import QObject

from kronos_veil.chat.base import ChatMessage, ChatProvider, ChatStatus

logger = logging.getLogger(__name__)


class YouTubeChatProvider(ChatProvider):
    """
    Architecture-ready provider for YouTube Live Chat streams.
    Polls liveChatMessages endpoint when API key and Video ID or LiveChatId are supplied.
    """

    def __init__(
        self,
        video_id: str = "",
        api_key: Optional[str] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.video_id = video_id.strip()
        self.api_key = api_key.strip() if api_key else ""
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._live_chat_id: Optional[str] = None

    def configure(self, video_id: str, api_key: Optional[str] = None) -> None:
        self.video_id = video_id.strip()
        if api_key is not None:
            self.api_key = api_key.strip()

    def connect_chat(self) -> None:
        if not self.video_id:
            self.status = ChatStatus.ERROR
            self.status_changed.emit(ChatStatus.ERROR.value, "No YouTube Video ID specified.")
            return

        if not self.api_key:
            self.status = ChatStatus.ERROR
            self.status_changed.emit(
                ChatStatus.ERROR.value,
                "YouTube Data API v3 key required for YouTube Live Chat. Please provide key in settings."
            )
            return

        if self._running:
            return

        self._running = True
        self.status = ChatStatus.CONNECTING
        self.status_changed.emit(ChatStatus.CONNECTING.value, f"Resolving live stream for {self.video_id}...")

        self._thread = threading.Thread(target=self._poll_worker, daemon=True, name="KV-YouTubeChat")
        self._thread.start()

    def disconnect_chat(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self.status = ChatStatus.DISCONNECTED
        self.status_changed.emit(ChatStatus.DISCONNECTED.value, "YouTube Live Chat disconnected.")

    def is_connected(self) -> bool:
        return self._running and self.status == ChatStatus.CONNECTED

    def _resolve_live_chat_id(self) -> Optional[str]:
        """Resolves active liveChatId from videoId via videos.list API."""
        try:
            params = urllib.parse.urlencode({
                "part": "liveStreamingDetails",
                "id": self.video_id,
                "key": self.api_key,
            })
            url = f"https://www.googleapis.com/youtube/v3/videos?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "KronosVeil/1.0"})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items = data.get("items", [])
            if not items:
                logger.error("No video found for ID %s", self.video_id)
                return None

            details = items[0].get("liveStreamingDetails", {})
            chat_id = details.get("activeLiveChatId")
            if not chat_id:
                logger.error("Video %s is not an active live broadcast or chat is disabled.", self.video_id)
                return None
            return chat_id
        except Exception as e:
            logger.error("Failed resolving YouTube liveChatId: %s", e)
            return None

    def _poll_worker(self) -> None:
        """Worker thread polling YouTube live chat messages."""
        self._live_chat_id = self._resolve_live_chat_id()
        if not self._live_chat_id:
            self.status = ChatStatus.ERROR
            self.status_changed.emit(ChatStatus.ERROR.value, "Could not find active live chat for this video.")
            self._running = False
            return

        self.status = ChatStatus.CONNECTED
        self.status_changed.emit(ChatStatus.CONNECTED.value, f"Connected to YouTube Chat ({self.video_id})")

        next_page_token = None
        poll_interval_sec = 5.0

        while self._running:
            try:
                query_params = {
                    "liveChatId": self._live_chat_id,
                    "part": "snippet,authorDetails",
                    "key": self.api_key,
                }
                if next_page_token:
                    query_params["pageToken"] = next_page_token

                url = f"https://www.googleapis.com/youtube/v3/liveChat/messages?{urllib.parse.urlencode(query_params)}"
                req = urllib.request.Request(url, headers={"User-Agent": "KronosVeil/1.0"})

                with urllib.request.urlopen(req, timeout=10.0) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))

                poll_interval_ms = payload.get("pollingIntervalMillis", 5000)
                poll_interval_sec = max(2.0, poll_interval_ms / 1000.0)
                next_page_token = payload.get("nextPageToken")

                for item in payload.get("items", []):
                    snippet = item.get("snippet", {})
                    author = item.get("authorDetails", {})

                    user_name = author.get("displayName", "Viewer")
                    msg_text = snippet.get("displayMessage", "")

                    color = "#ff4444" if author.get("isChatOwner") else "#00bcd4"
                    if author.get("isChatModerator"):
                        color = "#4caf50"

                    msg = ChatMessage(
                        id=item.get("id"),
                        username=user_name,
                        message=msg_text,
                        color=color,
                        platform="youtube",
                    )
                    self.message_received.emit(msg)

            except Exception as e:
                logger.warning("YouTube polling error: %s", e)
                if not self._running:
                    break
                time.sleep(5.0)

            # Wait for next poll
            step = 0.5
            waited = 0.0
            while self._running and waited < poll_interval_sec:
                time.sleep(step)
                waited += step

        self.status = ChatStatus.DISCONNECTED
