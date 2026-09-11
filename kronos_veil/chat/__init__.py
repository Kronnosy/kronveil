"""
Chat provider layer for Kronos Veil.
Implements provider/adaptor architecture supporting Demo, Twitch, and YouTube Live.
"""

from kronos_veil.chat.aggregator import UnifiedChatProvider
from kronos_veil.chat.base import ChatMessage, ChatProvider, ChatStatus
from kronos_veil.chat.demo import DemoChatProvider
from kronos_veil.chat.emotes import EmoteManager
from kronos_veil.chat.filters import ChatFilterEngine
from kronos_veil.chat.hype import HypeDetector, HypeSpikeEvent
from kronos_veil.chat.kick import KickChatProvider
from kronos_veil.chat.questions import QuestionDeckManager, QuestionExtractor, QuestionItem
from kronos_veil.chat.twitch import TwitchChatProvider
from kronos_veil.chat.youtube import YouTubeChatProvider

__all__ = [
    "ChatFilterEngine",
    "ChatMessage",
    "ChatProvider",
    "ChatStatus",
    "DemoChatProvider",
    "EmoteManager",
    "HypeDetector",
    "HypeSpikeEvent",
    "KickChatProvider",
    "QuestionDeckManager",
    "QuestionExtractor",
    "QuestionItem",
    "TwitchChatProvider",
    "UnifiedChatProvider",
    "YouTubeChatProvider",
]

