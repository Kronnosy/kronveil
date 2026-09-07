"""
Chat provider layer for Kronos Veil.
Implements provider/adaptor architecture supporting Demo, Twitch, and YouTube Live.
"""

from kronos_veil.chat.base import ChatMessage, ChatProvider, ChatStatus
from kronos_veil.chat.demo import DemoChatProvider
from kronos_veil.chat.twitch import TwitchChatProvider
from kronos_veil.chat.youtube import YouTubeChatProvider

__all__ = [
    "ChatMessage",
    "ChatProvider",
    "ChatStatus",
    "DemoChatProvider",
    "TwitchChatProvider",
    "YouTubeChatProvider",
]
