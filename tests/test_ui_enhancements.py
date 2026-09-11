"""
Unit tests for the new UI enhancements:
- Theme presets and palettes (cyberpunk, stealth, glass, neon, retro)
- ChatMessageWidget styling (card, bubble, clean) and mention detection
- Overlay quick theme/style cycling and mention signals
- SettingsWindow live preview canvas and 1-click theme presets
- MiniHud dynamic bitrate health coloring, recording badge, and compact mode
- ToastWindow in-game capture-protected notifications
"""

import pytest
from PySide6.QtWidgets import QApplication

from kronos_veil.chat.base import ChatMessage
from kronos_veil.config import ConfigManager
from kronos_veil.hud import MiniHudWindow
from kronos_veil.obs.client import OBSStreamStats
from kronos_veil.overlay import ChatMessageWidget, OverlayWindow
from kronos_veil.settings_window import SettingsWindow
from kronos_veil.themes import THEME_PRESETS, get_theme
from kronos_veil.toast import ToastWindow
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager


def test_theme_presets():
    assert "cyberpunk" in THEME_PRESETS
    assert "stealth" in THEME_PRESETS
    assert "glass" in THEME_PRESETS
    assert "neon" in THEME_PRESETS
    assert "retro" in THEME_PRESETS

    theme = get_theme("neon")
    assert theme.name == "neon"
    assert theme.accent_color == "#ec4899"

    # Fallback to cyberpunk
    unknown = get_theme("unknown_theme_xyz")
    assert unknown.name == "cyberpunk"


def test_chat_message_styles_and_mentions(qapp, tmp_path):
    cfg_file = tmp_path / "cfg.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cfg.settings.streamer_name = "SuperGamer"
    cfg.settings.highlight_mentions = True

    # 1. Normal message in Card style
    cfg.settings.chat_style = "card"
    msg1 = ChatMessage(username="Alice", message="Hello world!")
    w1 = ChatMessageWidget(msg1, cfg.settings)
    assert w1.is_mentioned is False
    assert "background-color" in w1.styleSheet()

    # 2. Mentioned message in Bubble style
    cfg.settings.chat_style = "bubble"
    msg2 = ChatMessage(username="Bob", message="Hey @supergamer great shot!")
    w2 = ChatMessageWidget(msg2, cfg.settings)
    assert w2.is_mentioned is True

    # 3. Clean style
    cfg.settings.chat_style = "clean"
    msg3 = ChatMessage(username="Charlie", message="GG WP!")
    w3 = ChatMessageWidget(msg3, cfg.settings)
    assert w3.is_mentioned is False
    assert "background: transparent" in w3.styleSheet()

    w1.deleteLater()
    w2.deleteLater()
    w3.deleteLater()


def test_overlay_quick_cycles_and_mention_signal(qapp, tmp_path):
    cfg_file = tmp_path / "cfg_overlay.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cfg.settings.streamer_name = "ProPlayer"
    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    overlay = OverlayWindow(cfg, cap, style)
    overlay.show()

    # Verify quick toolbar buttons exist
    assert hasattr(overlay, "theme_cycle_btn")
    assert hasattr(overlay, "style_cycle_btn")

    # Test cycling theme
    initial_theme = overlay.settings.theme_preset
    overlay._cycle_theme()
    assert overlay.settings.theme_preset != initial_theme

    # Test cycling style
    initial_style = overlay.settings.chat_style
    overlay._cycle_style()
    assert overlay.settings.chat_style != initial_style

    # Test mention detection signal emission
    mentions = []
    overlay.mention_detected.connect(lambda u, m: mentions.append((u, m)))

    msg = ChatMessage(username="Fan1", message="Hey @ProPlayer you're the best!")
    overlay.add_message(msg)
    assert len(mentions) == 1
    assert mentions[0][0] == "Fan1"

    overlay.close()


def test_settings_window_live_preview_and_presets(qapp, tmp_path):
    cfg_file = tmp_path / "cfg_settings.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()

    settings_win = SettingsWindow(cfg, cap)
    settings_win.show()

    # Check live preview container exists and has widgets
    assert hasattr(settings_win, "preview_box")
    assert hasattr(settings_win, "preview_layout")
    assert settings_win.preview_layout.count() >= 3

    # Test 1-click theme presets button
    settings_win._apply_theme_preset("retro")
    assert cfg.settings.theme_preset == "retro"
    assert cfg.settings.font_family == "Consolas"

    # Test changing chat style
    settings_win.style_combo.setCurrentIndex(1)  # bubble
    assert cfg.settings.chat_style == "bubble"

    # Test changing HUD layout
    settings_win.hud_layout_combo.setCurrentIndex(1)  # compact
    assert cfg.settings.hud_layout == "compact"

    settings_win.close()


def test_hud_recording_and_health_colors(qapp, tmp_path):
    cfg_file = tmp_path / "cfg_hud.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    hud = MiniHudWindow(cfg, cap, style)
    hud.show()

    # Test healthy bitrate (>5500 kbps)
    stats_good = OBSStreamStats(
        is_live=True,
        is_recording=True,
        bitrate_kbps=6200,
        dropped_frames=0,
        dropped_percent=0.0,
    )
    hud.update_stats(stats_good)
    assert hud.rec_badge.isVisible() is True
    assert "#22c55e" in hud.bitrate_label.styleSheet()

    # Test low bitrate warning (<3500 kbps)
    stats_bad = OBSStreamStats(
        is_live=True,
        is_recording=False,
        bitrate_kbps=2800,
        dropped_frames=120,
        dropped_percent=4.2,
    )
    hud.update_stats(stats_bad)
    assert hud.rec_badge.isHidden() is True
    assert "#ef4444" in hud.bitrate_label.styleSheet()

    # Test compact layout mode
    cfg.settings.hud_layout = "compact"
    hud.apply_layout_mode()
    assert hud.uptime_label.isHidden() is True
    assert hud.viewers_label.isHidden() is True

    # Test standard horizontal layout mode
    cfg.settings.hud_layout = "horizontal"
    hud.apply_layout_mode()
    assert hud.uptime_label.isHidden() is False
    assert hud.viewers_label.isHidden() is False

    hud.close()


def test_toast_notification_window(qapp, tmp_path):
    cfg_file = tmp_path / "cfg_toast.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()
    style = WindowStyleManager()

    toast = ToastWindow(cfg, cap, style)
    toast.show_toast(
        title="Test Alert",
        message="Broadcast is live!",
        icon="🔴",
        level="danger",
        duration_sec=1.0,
    )
    assert toast.title_label.text() == "Test Alert"
    assert toast.message_label.text() == "Broadcast is live!"
    assert toast.icon_label.text() == "🔴"

    toast.close()
