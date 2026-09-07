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

    # Operational Modes
    locked: bool = False
    click_through: bool = False
    capture_protection: bool = True

    # Global Hotkeys
    hotkey_toggle_lock: str = "Ctrl+Shift+F10"
    hotkey_toggle_clickthrough: str = "Ctrl+Shift+F11"
    hotkey_peek: str = "Ctrl+Shift+F9"

    # Chat Providers
    chat_provider: str = "demo"  # "demo", "twitch", "youtube"
    twitch_channel: str = ""
    youtube_video_id: str = ""

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

        valid_providers = {"demo", "twitch", "youtube"}
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
            return safe_x, safe_y

        return x, y
