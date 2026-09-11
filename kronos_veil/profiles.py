"""
Per-Game Auto-Switching Profiles for Kronos Veil.
Detects active foreground game processes via Win32 ctypes and switches
window geometries, themes, and HUD configurations automatically.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass, field
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger(__name__)


@dataclass
class GameProfile:
    """Stores window layouts and appearance configurations for a specific game."""
    name: str
    process_names: List[str] = field(default_factory=list)  # e.g. ["cs2.exe", "valorant.exe"]
    window_titles: List[str] = field(default_factory=list)  # e.g. ["VALORANT"]

    # Overlay Geometry & Styling
    overlay_x: int = 60
    overlay_y: int = 100
    overlay_width: int = 380
    overlay_height: int = 520
    overlay_opacity: float = 0.95
    background_opacity: float = 0.65
    theme_preset: str = "cyberpunk"
    chat_style: str = "card"
    font_size: int = 14

    # Modular Windows Geometries
    hud_x: int = 60
    hud_y: int = 30
    event_deck_x: int = 60
    event_deck_y: int = 80

    def matches(self, process_name: str, window_title: str) -> bool:
        """Determines if the given executable or window title matches this profile."""
        proc_lower = process_name.lower().strip()
        title_lower = window_title.lower().strip()

        for target in self.process_names:
            if target.lower().strip() and target.lower().strip() in proc_lower:
                return True

        for target_title in self.window_titles:
            if target_title.lower().strip() and target_title.lower().strip() in title_lower:
                return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GameProfile:
        valid_fields = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


def get_default_preset_profiles() -> List[GameProfile]:
    """Returns curated ready-to-use profiles for popular competitive games."""
    return [
        GameProfile(
            name="Default",
            process_names=[],
            window_titles=[],
            overlay_x=60,
            overlay_y=100,
            overlay_width=380,
            overlay_height=520,
            hud_x=60,
            hud_y=30,
            event_deck_x=60,
            event_deck_y=80,
            theme_preset="cyberpunk",
        ),
        GameProfile(
            name="Valorant",
            process_names=["valorant-win64-shipping.exe", "valorant.exe"],
            window_titles=["valorant"],
            # Shift overlay to middle right to avoid radar (top-left) and abilities (bottom)
            overlay_x=1480,
            overlay_y=280,
            overlay_width=400,
            overlay_height=500,
            hud_x=1480,
            hud_y=30,
            event_deck_x=1480,
            event_deck_y=80,
            theme_preset="neon",
        ),
        GameProfile(
            name="League of Legends",
            process_names=["league of legends.exe"],
            window_titles=["league of legends (tm) client"],
            # Shift overlay to top left to avoid minimap (bottom-right) and hero bars (bottom-center)
            overlay_x=60,
            overlay_y=120,
            overlay_width=360,
            overlay_height=480,
            hud_x=60,
            hud_y=30,
            event_deck_x=60,
            event_deck_y=75,
            theme_preset="glass",
        ),
        GameProfile(
            name="Counter-Strike 2",
            process_names=["cs2.exe"],
            window_titles=["counter-strike 2"],
            # Shift overlay to lower left, away from top radar and scoreboard
            overlay_x=60,
            overlay_y=360,
            overlay_width=380,
            overlay_height=480,
            hud_x=60,
            hud_y=30,
            event_deck_x=60,
            event_deck_y=80,
            theme_preset="stealth",
        ),
    ]


def detect_foreground_window() -> Tuple[str, str]:
    """
    Queries the currently focused foreground window using Windows User32/Kernel32 ctypes.
    Returns: (process_name, window_title), e.g. ('cs2.exe', 'Counter-Strike 2')
    """
    if sys.platform != "win32":
        return "", ""

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "", ""

        # Window title
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value

        # Process ID
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return "", title

        # Query process image path
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        exe_name = ""
        if h_proc:
            try:
                buf_size = wintypes.DWORD(1024)
                img_buf = ctypes.create_unicode_buffer(1024)
                if hasattr(kernel32, "QueryFullProcessImageNameW"):
                    if kernel32.QueryFullProcessImageNameW(h_proc, 0, img_buf, ctypes.byref(buf_size)):
                        full_path = img_buf.value
                        exe_name = os.path.basename(full_path)
            finally:
                kernel32.CloseHandle(h_proc)

        return exe_name, title
    except Exception as e:
        logger.debug("Error detecting foreground window: %s", e)
        return "", ""


class ProfileManager(QObject):
    """
    Orchestrates per-game profiles and monitors foreground window changes
    to automatically adapt Kronos Veil layout.
    """

    profile_applied = Signal(GameProfile)
    profiles_changed = Signal()
    active_window_detected = Signal(str, str)  # (exe_name, title)

    def __init__(self, profiles_data: Optional[List[Dict[str, Any]]] = None) -> None:
        super().__init__()
        self.profiles: Dict[str, GameProfile] = {}
        self.active_profile_name: str = "Default"
        self.auto_switch_enabled: bool = True

        self._init_profiles(profiles_data)

        # Background polling timer for active window (checks every 1.5 seconds)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._check_foreground_window)
        self._last_detected_exe: str = ""

    def _init_profiles(self, profiles_data: Optional[List[Dict[str, Any]]]) -> None:
        """Initializes profiles dictionary from provided config or defaults."""
        presets = get_default_preset_profiles()
        for p in presets:
            self.profiles[p.name] = p

        if profiles_data:
            for item in profiles_data:
                try:
                    prof = GameProfile.from_dict(item)
                    self.profiles[prof.name] = prof
                except Exception as e:
                    logger.warning("Failed to parse profile dict: %s", e)

        if "Default" not in self.profiles:
            self.profiles["Default"] = presets[0]

    def start_monitoring(self, interval_ms: int = 1500) -> None:
        """Starts monitoring active window focus for auto-switching."""
        if not self._poll_timer.isActive():
            self._poll_timer.start(interval_ms)
            logger.info("ProfileManager foreground monitoring started (interval: %dms)", interval_ms)

    def stop_monitoring(self) -> None:
        """Stops active window monitoring."""
        if self._poll_timer.isActive():
            self._poll_timer.stop()

    def get_profile(self, name: str) -> Optional[GameProfile]:
        return self.profiles.get(name)

    def get_all_profiles(self) -> List[GameProfile]:
        return list(self.profiles.values())

    def add_or_update_profile(self, profile: GameProfile) -> None:
        self.profiles[profile.name] = profile
        self.profiles_changed.emit()

    def delete_profile(self, name: str) -> bool:
        if name == "Default":
            logger.warning("Cannot delete Default profile.")
            return False
        if name in self.profiles:
            del self.profiles[name]
            if self.active_profile_name == name:
                self.apply_profile("Default")
            self.profiles_changed.emit()
            return True
        return False

    def apply_profile(self, name: str) -> bool:
        """Manually switches active profile and emits profile_applied."""
        profile = self.profiles.get(name)
        if not profile:
            logger.warning("Profile '%s' not found.", name)
            return False

        self.active_profile_name = name
        logger.info("Applying game profile: %s", name)
        self.profile_applied.emit(profile)
        return True

    def export_data(self) -> List[Dict[str, Any]]:
        """Exports profile list for JSON persistence."""
        return [p.to_dict() for p in self.profiles.values()]

    def _check_foreground_window(self) -> None:
        """Timer callback that detects foreground app and triggers profile switch if matched."""
        if not self.auto_switch_enabled:
            return

        exe_name, title = detect_foreground_window()
        if not exe_name:
            return

        self.active_window_detected.emit(exe_name, title)

        # Skip if Kronos Veil or explorer itself is in foreground
        ignore_list = {"python.exe", "kronosveil.exe", "explorer.exe", "cmd.exe", "powershell.exe"}
        if exe_name.lower() in ignore_list:
            return

        if exe_name == self._last_detected_exe:
            return

        self._last_detected_exe = exe_name

        # Search for a matching profile
        matched_profile: Optional[GameProfile] = None
        for profile in self.profiles.values():
            if profile.name == "Default":
                continue
            if profile.matches(exe_name, title):
                matched_profile = profile
                break

        target_name = matched_profile.name if matched_profile else "Default"
        if target_name != self.active_profile_name:
            logger.info(
                "Foreground window changed to '%s' ('%s'). Switching profile to '%s'.",
                exe_name, title, target_name
            )
            self.apply_profile(target_name)
