"""
Local Demo Chat Provider for Kronos Veil.
Generates realistic streaming chat messages without requiring external accounts or network access.
"""

from __future__ import annotations

import random
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer

from kronos_veil.chat.base import ChatMessage, ChatProvider, ChatStatus

DEMO_USERS: List[tuple[str, str]] = [
    ("NeonViper", "#00e5ff"),
    ("CyberSamurai", "#ff007f"),
    ("GlitchFox", "#39ff14"),
    ("Valkyrie99", "#ff9100"),
    ("PixelKnight", "#b388ff"),
    ("AeroStream", "#00b0ff"),
    ("ShadowWalker", "#e040fb"),
    ("ChronoShift", "#ffd600"),
    ("SpecterOps", "#00e676"),
    ("NovaPrime", "#ff5252"),
]

DEMO_MESSAGES: List[str] = [
    "pogchamp!!",
    "What a crazy clutch play!",
    "Can you check your game audio? It sounds crisp!",
    "clip that right now lmao",
    "Let's goooo! W streamer",
    "How is this overlay invisible on stream? That's insane tech!",
    "he was right behind the corner haha",
    "gg wp, that was a legendary round",
    "sub hype in chat!",
    "What monitor refresh rate are you using?",
    "Is this game worth picking up?",
    "drop the sensitivity settings please!",
    "clean aim today",
    "10/10 gameplay",
    "Welcome new viewers!",
]


class DemoChatProvider(ChatProvider):
    """Generates simulated streaming chat messages on a variable timer."""

    def __init__(self, parent: Optional[QObject] = None, interval_range: tuple[float, float] = (2.5, 6.0)) -> None:
        super().__init__(parent)
        self.interval_range = interval_range
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._connected = False

    def connect_chat(self) -> None:
        if self._connected:
            return
        self._connected = True
        self.status = ChatStatus.CONNECTED
        self.status_changed.emit(ChatStatus.CONNECTED.value, "Local Demo Provider active.")
        self._schedule_next_message()

    def disconnect_chat(self) -> None:
        self._connected = False
        self._timer.stop()
        self.status = ChatStatus.DISCONNECTED
        self.status_changed.emit(ChatStatus.DISCONNECTED.value, "Local Demo Provider stopped.")

    def is_connected(self) -> bool:
        return self._connected

    def _schedule_next_message(self) -> None:
        if not self._connected:
            return
        delay_sec = random.uniform(*self.interval_range)
        self._timer.start(int(delay_sec * 1000))

    def _on_tick(self) -> None:
        if not self._connected:
            return
        self._timer.stop()
        msg = self.generate_random_message()
        self.message_received.emit(msg)
        self._schedule_next_message()

    def generate_random_message(self) -> ChatMessage:
        user, color = random.choice(DEMO_USERS)
        text = random.choice(DEMO_MESSAGES)
        return ChatMessage(
            username=user,
            message=text,
            color=color,
        )

    def send_manual_message(
        self,
        text: str,
        username: str = "TestUser",
        color: str = "#00d2be",
        is_test: bool = False,
        is_system: bool = False,
    ) -> ChatMessage:
        """Injects a specific message immediately into the chat pipeline."""
        msg = ChatMessage(
            username=username,
            message=text,
            color=color,
            is_test=is_test,
            is_system=is_system,
        )
        self.message_received.emit(msg)
        return msg
