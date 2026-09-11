"""
Base abstractions and data structures for Kronos Veil chat providers.
"""

from __future__ import annotations

import time
import uuid
from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from PySide6.QtCore import QObject, Signal


@dataclass
class ChatMessage:
    """Represents a standardized chat message across all streaming platforms."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = "Anonymous"
    message: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    color: str = "#00d2be"  # Cyan/teal accent default
    badges: List[str] = field(default_factory=list)
    is_system: bool = False
    is_test: bool = False
    platform: str = "demo"  # "twitch", "kick", "youtube", "demo"


class ChatStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


class ChatProvider(QObject):
    """
    Abstract Base Class for Chat Providers.
    Uses Qt Signals for thread-safe cross-thread UI updates.
    """

    message_received = Signal(ChatMessage)
    status_changed = Signal(str, str)  # status: str, detail_message: str

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.status: ChatStatus = ChatStatus.DISCONNECTED

    @abstractmethod
    def connect_chat(self) -> None:
        """Establish connection to the chat service."""
        pass

    @abstractmethod
    def disconnect_chat(self) -> None:
        """Disconnect from the chat service."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Returns True if the provider is currently connected."""
        pass
