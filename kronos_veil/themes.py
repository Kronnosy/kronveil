"""
Theme presets and palette engine for Kronos Veil.
Provides curated broadcast-ready color schemes and visual configurations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ThemePalette:
    name: str
    display_name: str
    background_color: str  # Hex or rgba
    border_color: str
    accent_color: str
    text_primary: str
    text_secondary: str
    card_background: str
    card_border: str
    mention_border: str
    font_family: str


THEME_PRESETS: Dict[str, ThemePalette] = {
    "cyberpunk": ThemePalette(
        name="cyberpunk",
        display_name="Cyberpunk Cyan",
        background_color="rgba(13, 17, 23, {alpha})",
        border_color="#00e5ff",
        accent_color="#00e5ff",
        text_primary="#ffffff",
        text_secondary="#94a3b8",
        card_background="rgba(22, 31, 46, 0.75)",
        card_border="rgba(0, 229, 255, 0.35)",
        mention_border="#ff007f",
        font_family="Segoe UI",
    ),
    "stealth": ThemePalette(
        name="stealth",
        display_name="Obsidian Stealth",
        background_color="rgba(10, 10, 12, {alpha})",
        border_color="#334155",
        accent_color="#f8fafc",
        text_primary="#f1f5f9",
        text_secondary="#64748b",
        card_background="rgba(18, 18, 22, 0.85)",
        card_border="rgba(71, 85, 105, 0.4)",
        mention_border="#fbbf24",
        font_family="Segoe UI",
    ),
    "glass": ThemePalette(
        name="glass",
        display_name="Frosted Slate",
        background_color="rgba(15, 23, 42, {alpha})",
        border_color="#38bdf8",
        accent_color="#38bdf8",
        text_primary="#f8fafc",
        text_secondary="#94a3b8",
        card_background="rgba(30, 41, 59, 0.65)",
        card_border="rgba(56, 189, 248, 0.25)",
        mention_border="#f43f5e",
        font_family="Segoe UI",
    ),
    "neon": ThemePalette(
        name="neon",
        display_name="Neon Sunset",
        background_color="rgba(18, 10, 26, {alpha})",
        border_color="#ec4899",
        accent_color="#ec4899",
        text_primary="#ffffff",
        text_secondary="#c084fc",
        card_background="rgba(42, 16, 56, 0.75)",
        card_border="rgba(236, 72, 153, 0.4)",
        mention_border="#eab308",
        font_family="Segoe UI",
    ),
    "retro": ThemePalette(
        name="retro",
        display_name="Retro Terminal",
        background_color="rgba(5, 15, 10, {alpha})",
        border_color="#22c55e",
        accent_color="#22c55e",
        text_primary="#4ade80",
        text_secondary="#166534",
        card_background="rgba(10, 26, 16, 0.85)",
        card_border="rgba(34, 197, 94, 0.35)",
        mention_border="#86efac",
        font_family="Consolas",
    ),
}


def get_theme(theme_name: str) -> ThemePalette:
    """Safely retrieves a theme palette, falling back to 'cyberpunk'."""
    return THEME_PRESETS.get(theme_name.lower(), THEME_PRESETS["cyberpunk"])
