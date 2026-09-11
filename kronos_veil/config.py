"""
Configuration management for Kronos Veil.
Handles settings persistence, validation, safe fallbacks, and multi-monitor recovery.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AppSettings:
    # Overlay Window Geometry
    overlay_x: int = 60
    overlay_y: int = 100
    overlay_width: int = 380
    overlay_height: int = 520

    # Appearance & Styling
    overlay_opacity: float = 0.95
    background_opacity: float = 0.65
    font_size: int = 14
    message_spacing: int = 6
    text_shadow: bool = True
    max_messages: int = 50
    message_lifetime_sec: int = 30  # 0 means messages never expire
    fade_duration_sec: float = 1.5
    show_timestamps: bool = True
    show_usernames: bool = True
    emotes_enabled: bool = True

    # Theme & Visual Style
    chat_style: str = "card"  # "card", "bubble", "clean"
    theme_preset: str = "cyberpunk"  # "cyberpunk", "stealth", "glass", "neon", "retro"
    font_family: str = "Segoe UI"
    accent_color: str = "#00e5ff"
    card_opacity: float = 0.75
    card_radius: int = 6
    streamer_name: str = ""
    highlight_mentions: bool = True

    # Operational Modes
    locked: bool = False
    click_through: bool = False
    capture_protection: bool = True

    # Global Hotkeys
    hotkey_toggle_lock: str = "Ctrl+Shift+F10"
    hotkey_toggle_clickthrough: str = "Ctrl+Shift+F11"
    hotkey_peek: str = "Ctrl+Shift+F9"

    # Chat Providers
    chat_provider: str = "demo"  # "demo", "twitch", "youtube", "kick"
    twitch_channel: str = ""
    youtube_video_id: str = ""
    kick_channel: str = ""

    # OBS WebSocket v5 & HUD
    obs_enabled: bool = False
    obs_host: str = "localhost"
    obs_port: int = 4455
    obs_password: str = ""
    hud_enabled: bool = True
    hud_x: int = 60
    hud_y: int = 30
    hud_locked: bool = False
    hud_layout: str = "horizontal"  # "horizontal", "compact", "vertical"
    toast_enabled: bool = True
    toast_duration_sec: float = 4.0

    # Modular Window: Stream Events Deck
    event_deck_enabled: bool = True
    event_deck_x: int = 60
    event_deck_y: int = 80
    event_deck_width: int = 500
    event_deck_height: int = 42
    event_deck_locked: bool = False
    streamelements_jwt: str = ""

    # Per-Game Profiles & Auto-Switching
    auto_profile_enabled: bool = True
    active_profile: str = "Default"
    profiles: list = field(default_factory=list)

    # Multistream Unified Chat & Aggregator
    multistream_enabled: bool = False
    multistream_twitch: bool = True
    multistream_kick: bool = False
    multistream_youtube: bool = False

    # Smart Chat Filters
    filter_bot_commands: bool = True
    filter_duplicates: bool = True
    filter_duplicate_window_sec: float = 3.0

    # Mobile LAN Web Companion (Stream Deck)
    web_companion_enabled: bool = True
    web_companion_port: int = 8989
    web_companion_pin: str = "7749"

    # Game State Integration (GSI) & Clutch Mode
    gsi_enabled: bool = False
    gsi_port: int = 31337
    gsi_auth_token: str = ""
    clutch_mode_enabled: bool = True
    clutch_dim_opacity: float = 0.0
    clutch_health_threshold: int = 25

    # Hype Spike & OBS Auto-Clip Engine
    hype_detector_enabled: bool = True
    hype_window_seconds: int = 15
    hype_threshold_rate: float = 3.5
    hype_auto_clip: bool = False
    hype_cooldown_seconds: int = 60

    # Smart Q&A Question Deck
    qa_deck_enabled: bool = False
    qa_deck_x: int = 60
    qa_deck_y: int = 140
    qa_deck_width: int = 440
    qa_deck_height: int = 300
    qa_deck_locked: bool = False
    qa_max_items: int = 20
    qa_auto_expire_seconds: int = 300

    # Hybrid Auth & Advanced Credentials
    twitch_oauth_token: str = ""

    # System & Lifecycle
    launch_on_startup: bool = False
    debug_mode: bool = False
    first_launch: bool = True

    def validate(self) -> None:
        """Sanitize and clamp settings to safe operational bounds."""
        self.overlay_width = max(200, min(self.overlay_width, 3840))
        self.overlay_height = max(150, min(self.overlay_height, 2160))
        self.overlay_opacity = max(0.1, min(float(self.overlay_opacity), 1.0))
        self.background_opacity = max(0.0, min(float(self.background_opacity), 1.0))
        self.font_size = max(8, min(int(self.font_size), 36))
        self.message_spacing = max(1, min(int(self.message_spacing), 30))
        self.max_messages = max(5, min(int(self.max_messages), 200))
        self.message_lifetime_sec = max(0, min(int(self.message_lifetime_sec), 3600))
        self.fade_duration_sec = max(0.1, min(float(self.fade_duration_sec), 10.0))
        self.obs_port = max(1, min(int(self.obs_port), 65535))
        self.card_opacity = max(0.0, min(float(self.card_opacity), 1.0))
        self.card_radius = max(0, min(int(self.card_radius), 24))
        self.toast_duration_sec = max(1.0, min(float(self.toast_duration_sec), 15.0))
        self.event_deck_width = max(200, min(getattr(self, "event_deck_width", 500), 3840))
        self.event_deck_height = max(30, min(getattr(self, "event_deck_height", 42), 1080))
        self.web_companion_port = max(1024, min(int(getattr(self, "web_companion_port", 8989)), 65535))
        self.filter_duplicate_window_sec = max(0.5, min(float(getattr(self, "filter_duplicate_window_sec", 3.0)), 30.0))

        # GSI & Clutch Validation
        self.gsi_port = max(1024, min(int(getattr(self, "gsi_port", 31337)), 65535))
        self.clutch_dim_opacity = max(0.0, min(float(getattr(self, "clutch_dim_opacity", 0.0)), 1.0))
        self.clutch_health_threshold = max(1, min(int(getattr(self, "clutch_health_threshold", 25)), 100))

        # Hype Spike Validation
        self.hype_window_seconds = max(3, min(int(getattr(self, "hype_window_seconds", 15)), 120))
        self.hype_threshold_rate = max(0.5, min(float(getattr(self, "hype_threshold_rate", 3.5)), 100.0))
        self.hype_cooldown_seconds = max(5, min(int(getattr(self, "hype_cooldown_seconds", 60)), 600))

        # Q&A Deck Validation
        self.qa_deck_width = max(200, min(getattr(self, "qa_deck_width", 440), 3840))
        self.qa_deck_height = max(100, min(getattr(self, "qa_deck_height", 300), 2160))
        self.qa_max_items = max(5, min(int(getattr(self, "qa_max_items", 20)), 100))
        self.qa_auto_expire_seconds = max(30, min(int(getattr(self, "qa_auto_expire_seconds", 300)), 3600))

        valid_styles = {"card", "bubble", "clean"}
        if self.chat_style not in valid_styles:
            self.chat_style = "card"

        valid_presets = {"cyberpunk", "stealth", "glass", "neon", "retro"}
        if self.theme_preset not in valid_presets:
            self.theme_preset = "cyberpunk"

        valid_hud_layouts = {"horizontal", "compact", "vertical"}
        if self.hud_layout not in valid_hud_layouts:
            self.hud_layout = "horizontal"

        valid_providers = {"demo", "twitch", "youtube", "kick"}
        if self.chat_provider not in valid_providers:
            self.chat_provider = "demo"



class ConfigManager:
    """Manages reading, writing, and validating Kronos Veil settings."""

    DEFAULT_FILENAME = "settings.json"

    def __init__(self, custom_path: Optional[Path | str] = None) -> None:
        if custom_path:
            self.config_path = Path(custom_path)
        else:
            self.config_path = self.get_default_config_path()
        self.settings = AppSettings()
        self.load()

    @staticmethod
    def get_default_config_path() -> Path:
        """Determines the standard persistent configuration file path on Windows."""
        appdata = os.getenv("APPDATA")
        if appdata:
            base_dir = Path(appdata) / "KronosVeil"
        else:
            base_dir = Path.home() / ".kronos_veil"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / ConfigManager.DEFAULT_FILENAME

    def load(self) -> AppSettings:
        """Loads settings from JSON with graceful fallback on corruption or missing keys."""
        if not self.config_path.exists():
            logger.info("Config file does not exist at %s. Using default settings.", self.config_path)
            self.settings = AppSettings()
            return self.settings

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.warning("Config content at %s is not a dictionary. Falling back to defaults.", self.config_path)
                self.settings = AppSettings()
                return self.settings

            valid_keys = set(AppSettings.__dataclass_fields__.keys())
            filtered_data = {k: v for k, v in data.items() if k in valid_keys}
            self.settings = AppSettings(**filtered_data)
            self.settings.validate()
            logger.debug("Successfully loaded configuration from %s", self.config_path)
        except Exception as e:
            logger.error("Failed to load configuration file at %s: %s. Using default settings.", self.config_path, e)
            self.settings = AppSettings()

        return self.settings

    def save(self) -> bool:
        """Persists current settings to disk safely."""
        try:
            self.settings.validate()
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self.settings), f, indent=2)
            temp_path.replace(self.config_path)
            logger.debug("Configuration saved to %s", self.config_path)
            return True
        except Exception as e:
            logger.error("Failed to save configuration to %s: %s", self.config_path, e)
            return False

    def sanitize_coordinates(
        self,
        screens: list[tuple[int, int, int, int]] | None = None,
        default_x: int = 60,
        default_y: int = 100,
    ) -> tuple[int, int]:
        """
        Ensures the overlay's (x, y) coordinates reside within the visible area of
        at least one connected monitor. If off-screen, repositions to a visible safe position.

        screens parameter: list of (x, y, width, height) rects.
        """
        x = self.settings.overlay_x
        y = self.settings.overlay_y
        w = self.settings.overlay_width
        h = self.settings.overlay_height

        if not screens:
            return x, y

        # Check if at least a 50x50 area of the window intersects any screen
        is_visible = False
        min_overlap = 50
        for sx, sy, sw, sh in screens:
            overlap_x = max(0, min(x + w, sx + sw) - max(x, sx))
            overlap_y = max(0, min(y + h, sy + sh) - max(y, sy))
            if overlap_x >= min_overlap and overlap_y >= min_overlap:
                is_visible = True
                break

        if not is_visible:
            # Fall back to top-left of primary screen (first screen)
            primary_x, primary_y, primary_w, primary_h = screens[0]
            safe_x = primary_x + default_x
            safe_y = primary_y + default_y
            logger.warning(
                "Overlay position (%d, %d) is off-screen. Repositioning to primary screen (%d, %d).",
                x, y, safe_x, safe_y
            )
            self.settings.overlay_x = safe_x
            self.settings.overlay_y = safe_y
            self.save()

        # Also sanitize HUD coordinates
        hx = self.settings.hud_x
        hy = self.settings.hud_y
        hud_visible = False
        for sx, sy, sw, sh in screens:
            if sx <= hx <= sx + sw - 100 and sy <= hy <= sy + sh - 30:
                hud_visible = True
                break
        if not hud_visible:
            primary_x, primary_y, _, _ = screens[0]
            self.settings.hud_x = primary_x + 60
            self.settings.hud_y = primary_y + 30
            self.save()

        # Sanitize Event Deck coordinates
        ed_x = getattr(self.settings, "event_deck_x", 60)
        ed_y = getattr(self.settings, "event_deck_y", 80)
        ed_visible = any(sx <= ed_x <= sx + sw - 100 and sy <= ed_y <= sy + sh - 30 for sx, sy, sw, sh in screens)
        if not ed_visible:
            primary_x, primary_y, _, _ = screens[0]
            self.settings.event_deck_x = primary_x + 60
            self.settings.event_deck_y = primary_y + 80
            self.save()

        return self.settings.overlay_x, self.settings.overlay_y


