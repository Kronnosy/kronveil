"""Smart Chat Filters Engine for Kronos Veil.

Provides high-performance filtering for livestream chat feeds:
- Bot command suppression (!commands, /commands, .commands)
- Sliding-window duplicate spam reduction
- Streamer mention and VIP detection
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Deque, Optional, Tuple

from kronos_veil.chat.base import ChatMessage

logger = logging.getLogger("KronosVeil.ChatFilter")

# Common prefixes used for bot commands
COMMAND_PREFIXES: Tuple[str, ...] = ("!", "/", ".", "$", "?", "%", "~")


class ChatFilterEngine:
    """Evaluates incoming chat messages against streamer-configured filter rules."""

    def __init__(self, duplicate_window_sec: float = 3.0) -> None:
        self.duplicate_window_sec = duplicate_window_sec
        # Store (timestamp, username_lower, message_lower)
        self._history: Deque[Tuple[float, str, str]] = deque()

    def set_duplicate_window(self, window_sec: float) -> None:
        """Update duplicate time window threshold."""
        self.duplicate_window_sec = max(0.5, float(window_sec))

    def is_bot_command(self, text: str) -> bool:
        """Check if message is a bot command (e.g., !sens, !discord, /me)."""
        stripped = text.strip()
        if not stripped:
            return False
        return stripped.startswith(COMMAND_PREFIXES)

    def is_duplicate_spam(self, username: str, text: str) -> bool:
        """Check if the exact message was posted by the same user within the recent window."""
        now = time.time()
        user_norm = username.lower().strip()
        text_norm = text.lower().strip()

        # Prune old entries outside window
        while self._history and (now - self._history[0][0]) > self.duplicate_window_sec:
            self._history.popleft()

        # Check if already seen
        for entry_time, u, m in self._history:
            if u == user_norm and m == text_norm:
                return True

        # Record new entry
        self._history.append((now, user_norm, text_norm))
        return False

    def is_mention(self, text: str, streamer_name: str) -> bool:
        """Detect if message mentions the streamer."""
        if not streamer_name or not text:
            return False
        target = streamer_name.lower().strip()
        if not target:
            return False
        words = [w.lower().strip("@.,!?:;") for w in text.split()]
        return target in words

    def should_display(
        self,
        msg: ChatMessage,
        filter_bot_commands: bool = True,
        filter_duplicates: bool = True,
    ) -> bool:
        """Evaluate if the message should pass through to the overlay.

        System and test messages are always permitted.
        """
        if msg.is_system or msg.is_test:
            return True

        # Bot commands check
        if filter_bot_commands and self.is_bot_command(msg.message):
            logger.debug("Filtered bot command message: %s", msg.message)
            return False

        # Duplicate spam check
        if filter_duplicates and self.is_duplicate_spam(msg.username, msg.message):
            logger.debug("Filtered duplicate message from %s: %s", msg.username, msg.message)
            return False

        return True
