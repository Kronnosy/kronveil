"""
Hype Spike & OBS Auto-Clip Engine for Kronos Veil.
Tracks rolling chat message velocity and emote intensity (KEKW, Pog, LUL, etc.)
over a sliding time window, detects hype spikes against user-configured thresholds,
enforces cooldown periods, and triggers automated OBS Studio stream markers and replay clips.
"""

from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import QObject, Signal, Slot

from kronos_veil.chat.base import ChatMessage, ChatProvider
from kronos_veil.chat.emotes import POPULAR_EMOTES
from kronos_veil.config import AppSettings
from kronos_veil.obs.client import OBSWebSocketClient

logger = logging.getLogger("KronosVeil.HypeDetector")

# Default weights assigned to popular high-energy hype reaction emotes
DEFAULT_HYPE_EMOTES: Dict[str, float] = {
    "KEKW": 2.0,
    "LUL": 1.5,
    "Pog": 2.0,
    "PogChamp": 2.0,
    "OMEGALUL": 2.5,
    "monkaW": 1.5,
    "monkaS": 1.2,
    "Clap": 1.2,
    "EZ": 1.2,
    "catJAM": 1.2,
    "GIGACHAD": 2.0,
    "pepeLaugh": 1.5,
    "WutFace": 1.2,
    "BibleThump": 1.2,
    "Kreygasm": 1.5,
    "Copium": 1.2,
    "AYAYA": 1.2,
    "widepeepoHappy": 1.2,
    "Sadge": 1.0,
    "Kappa": 1.0,
}


@dataclass
class HypeSpikeEvent:
    """Represents a hype spike triggered by chat velocity or manual simulation."""

    velocity: float
    threshold: float
    message_count: int = 0
    emote_count: int = 0
    top_emotes: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    auto_clipped: bool = False

    @property
    def clip_triggered(self) -> bool:
        """Alias for auto_clipped."""
        return self.auto_clipped


@dataclass
class _WindowEntry:
    timestamp: float
    score: float
    message_text: str
    emotes: List[str]


class HypeDetector(QObject):
    """
    Real-time sliding window chat analyzer detecting momentum spikes and triggering clips.
    """

    hype_spike_detected = Signal(HypeSpikeEvent)
    velocity_updated = Signal(float)

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        obs_client: Optional[OBSWebSocketClient] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings or AppSettings()
        self._obs_client = obs_client

        self.emote_weights: Dict[str, float] = dict(DEFAULT_HYPE_EMOTES)
        self.base_message_weight: float = 1.0
        self.default_emote_weight: float = 1.0

        self._window: Deque[_WindowEntry] = collections.deque()
        self._last_spike_time: float = 0.0

        # Virtual time support for deterministic unit testing
        self._simulated_time: bool = False
        self._virtual_time: float = 0.0

    @property
    def obs_client(self) -> Optional[OBSWebSocketClient]:
        """Returns attached OBS client, if any."""
        return self._obs_client

    @obs_client.setter
    def obs_client(self, client: Optional[OBSWebSocketClient]) -> None:
        self._obs_client = client

    def attach_obs_client(self, client: OBSWebSocketClient) -> None:
        """Attaches an OBS WebSocket client for clip triggering."""
        self._obs_client = client

    def attach_chat_provider(self, provider: ChatProvider) -> None:
        """Subscribes to a chat provider's message_received signal."""
        provider.message_received.connect(self.on_message)

    def update_settings(self, settings: AppSettings) -> None:
        """Updates internal configuration reference."""
        self.settings = settings

    def register_emote(self, emote_name: str, weight: float = 1.5) -> None:
        """Registers a custom emote token with a specific hype weight."""
        self.emote_weights[emote_name] = weight

    @property
    def threshold(self) -> float:
        """Current spike threshold rate from settings."""
        return float(self.settings.hype_threshold_rate)

    @property
    def window_seconds(self) -> int:
        """Current sliding window duration in seconds."""
        return int(self.settings.hype_window_seconds)

    @property
    def cooldown_seconds(self) -> int:
        """Current rate limit cooldown in seconds."""
        return int(self.settings.hype_cooldown_seconds)

    def _get_current_time(self, timestamp: Optional[float] = None) -> float:
        """Resolves current timestamp, respecting simulated time for unit testing."""
        if timestamp is not None:
            self._simulated_time = True
            self._virtual_time = max(self._virtual_time, timestamp)
            return timestamp
        if self._simulated_time:
            return self._virtual_time
        return time.time()

    def _prune_window(self, now: Optional[float] = None) -> None:
        """Evicts expired messages outside the rolling sliding window."""
        current_time = self._get_current_time(now)
        window_sec = max(1.0, float(self.settings.hype_window_seconds))
        cutoff = current_time - window_sec
        while self._window and self._window[0].timestamp < cutoff:
            self._window.popleft()

    def get_velocity(self, now: Optional[float] = None) -> float:
        """Calculates current velocity (weighted score / window_seconds) at a given time."""
        current_time = self._get_current_time(now)
        self._prune_window(current_time)
        if not self._window:
            return 0.0
        window_sec = max(1.0, float(self.settings.hype_window_seconds))
        total_score = sum(entry.score for entry in self._window)
        return total_score / window_sec

    @property
    def current_velocity(self) -> float:
        """Current hype velocity (msgs/sec or weighted points/sec) in the active sliding window."""
        return self.get_velocity()

    def get_cooldown_remaining(self, now: Optional[float] = None) -> float:
        """Returns remaining cooldown time before another spike can trigger."""
        if self._last_spike_time <= 0.0:
            return 0.0
        current_time = self._get_current_time(now)
        elapsed = current_time - self._last_spike_time
        cooldown = float(self.settings.hype_cooldown_seconds)
        remaining = cooldown - elapsed
        return max(0.0, remaining)

    @property
    def cooldown_remaining(self) -> float:
        """Number of seconds remaining in the rate-limiting cooldown period."""
        return self.get_cooldown_remaining()

    @property
    def is_on_cooldown(self) -> bool:
        """True if the detector is currently within the cooldown period after a spike."""
        return self.cooldown_remaining > 0.0

    def _extract_emotes(self, text: str) -> Tuple[List[str], float]:
        """
        Parses text for known hype emotes, returning (detected_emotes_list, total_emote_score).
        Supports case-insensitive fallback matching.
        """
        if not text:
            return [], 0.0

        tokens = text.split()
        detected: List[str] = []
        score: float = 0.0

        upper_map = {k.upper(): (k, v) for k, v in self.emote_weights.items()}

        for token in tokens:
            cleaned = token.strip(".,!?:;\"'()[]{}~`")
            if not cleaned:
                continue

            if cleaned in self.emote_weights:
                detected.append(cleaned)
                score += self.emote_weights[cleaned]
            elif cleaned.upper() in upper_map:
                canonical, weight = upper_map[cleaned.upper()]
                detected.append(canonical)
                score += weight
            elif cleaned in POPULAR_EMOTES:
                detected.append(cleaned)
                score += self.default_emote_weight

        return detected, score

    @Slot(object)
    def on_message(self, message: Union[ChatMessage, str]) -> None:
        """Qt Slot for handling incoming messages from ChatProvider or direct calls."""
        self.process_message(message)

    def process_message(
        self,
        message: Union[ChatMessage, str],
        timestamp: Optional[float] = None,
    ) -> float:
        """
        Ingests an incoming chat message, updates rolling velocity and emote intensity,
        and triggers a hype spike event (plus OBS auto-clip) if the threshold is met
        and cooldown has expired.

        Returns the updated current velocity.
        """
        if not getattr(self.settings, "hype_detector_enabled", True):
            return 0.0

        if isinstance(message, ChatMessage):
            if message.is_system:
                return self.current_velocity
            text = message.message
        elif isinstance(message, str):
            text = message
        else:
            return self.current_velocity

        if not text or not text.strip():
            return self.current_velocity

        now = self._get_current_time(timestamp)
        self._prune_window(now)

        detected_emotes, emote_score = self._extract_emotes(text)
        total_msg_score = self.base_message_weight + emote_score

        entry = _WindowEntry(
            timestamp=now,
            score=total_msg_score,
            message_text=text,
            emotes=detected_emotes,
        )
        self._window.append(entry)

        # Compute velocity = weighted score / window_seconds
        window_sec = max(1.0, float(self.settings.hype_window_seconds))
        total_score = sum(e.score for e in self._window)
        velocity = total_score / window_sec

        self.velocity_updated.emit(velocity)

        # Check threshold and cooldown
        threshold = float(self.settings.hype_threshold_rate)
        if velocity >= threshold:
            if not self.is_on_cooldown:
                self._last_spike_time = now

                # Gather top emotes
                all_emotes = [em for e in self._window for em in e.emotes]
                top_emotes = [em for em, _ in collections.Counter(all_emotes).most_common(5)]
                total_emotes = len(all_emotes)

                auto_clipped = False
                if getattr(self.settings, "hype_auto_clip", False):
                    desc = f"Hype Spike ({velocity:.1f} msgs/s)"
                    auto_clipped = self._trigger_auto_clip(desc)

                event = HypeSpikeEvent(
                    velocity=velocity,
                    threshold=threshold,
                    message_count=len(self._window),
                    emote_count=total_emotes,
                    top_emotes=top_emotes,
                    timestamp=now,
                    auto_clipped=auto_clipped,
                )
                logger.info(
                    "Hype spike detected! Velocity=%.2f >= Threshold=%.2f (msgs=%d, emotes=%d, clipped=%s)",
                    velocity,
                    threshold,
                    len(self._window),
                    total_emotes,
                    auto_clipped,
                )
                self.hype_spike_detected.emit(event)
            else:
                logger.debug(
                    "Hype spike rate-limited (%.2f >= %.2f): %.1fs remaining on cooldown",
                    velocity,
                    threshold,
                    self.cooldown_remaining,
                )

        return velocity

    def _trigger_auto_clip(self, description: str = "Hype Spike") -> bool:
        """Invokes OBS stream marker and replay buffer save if client is attached."""
        if not self._obs_client:
            logger.debug("Auto-clip skipped: No OBS client attached.")
            return False

        try:
            logger.info("Triggering OBS auto-clip: %s", description)
            self._obs_client.create_stream_marker(description)
            self._obs_client.save_replay_buffer()
            return True
        except Exception as exc:
            logger.error("Failed triggering OBS auto-clip: %s", exc)
            return False

    def simulate_spike(
        self,
        velocity: Optional[float] = None,
        force: bool = True,
    ) -> Optional[HypeSpikeEvent]:
        """
        Simulates a hype spike event. Used for previewing overlay alerts,
        testing OBS auto-clip, and UI testing.
        """
        target_velocity = (
            float(velocity)
            if velocity is not None
            else max(float(self.settings.hype_threshold_rate) * 1.5, 5.0)
        )
        now = self._get_current_time()

        if not force and self.is_on_cooldown:
            logger.info("simulate_spike blocked: on cooldown (%.1fs remaining)", self.cooldown_remaining)
            return None

        window_sec = max(1.0, float(self.settings.hype_window_seconds))
        total_score_needed = target_velocity * window_sec

        # Populate sliding window with synthetic entries matching target velocity
        self._window.clear()
        num_msgs = max(5, int(target_velocity * 2))
        score_per_msg = total_score_needed / num_msgs
        synthetic_emotes = ["KEKW", "Pog", "LUL", "OMEGALUL"]

        for i in range(num_msgs):
            self._window.append(
                _WindowEntry(
                    timestamp=now - (i * 0.05),
                    score=score_per_msg,
                    message_text="Simulated hype burst KEKW Pog",
                    emotes=synthetic_emotes,
                )
            )

        self._last_spike_time = now

        auto_clipped = False
        if getattr(self.settings, "hype_auto_clip", False):
            desc = f"Simulated Hype Spike ({target_velocity:.1f} msgs/s)"
            auto_clipped = self._trigger_auto_clip(desc)

        event = HypeSpikeEvent(
            velocity=target_velocity,
            threshold=float(self.settings.hype_threshold_rate),
            message_count=len(self._window),
            emote_count=len(self._window) * len(synthetic_emotes),
            top_emotes=synthetic_emotes,
            timestamp=now,
            auto_clipped=auto_clipped,
        )

        self.velocity_updated.emit(target_velocity)
        self.hype_spike_detected.emit(event)
        return event

    def reset(self) -> None:
        """Resets the detector state, clears the sliding window, and clears cooldown."""
        self._window.clear()
        self._last_spike_time = 0.0
        self._simulated_time = False
        self._virtual_time = 0.0
        self.velocity_updated.emit(0.0)
