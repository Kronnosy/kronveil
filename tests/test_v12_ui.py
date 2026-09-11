"""Tests for Kronos Veil v1.2 UI components, platform badges, and settings."""

from PySide6.QtWidgets import QApplication

from kronos_veil.chat.base import ChatMessage
from kronos_veil.config import AppSettings, ConfigManager
from kronos_veil.overlay import ChatMessageWidget, OverlayWindow
from kronos_veil.settings_window import SettingsWindow
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager


def test_chat_message_widget_platform_badges(qapp):
    settings = AppSettings()
    settings.show_usernames = True

    # Twitch platform badge
    msg_tw = ChatMessage(username="Shroud", message="Nice shot!", platform="twitch")
    widget_tw = ChatMessageWidget(msg_tw, settings)
    assert hasattr(widget_tw, "user_label")
    assert "TW" in widget_tw.user_label.text()

    # Kick platform badge
    msg_kick = ChatMessage(username="xQc", message="JUICE", platform="kick")
    widget_kick = ChatMessageWidget(msg_kick, settings)
    assert "KICK" in widget_kick.user_label.text()

    # YouTube platform badge
    msg_yt = ChatMessage(username="Valkyrae", message="Let's go!", platform="youtube")
    widget_yt = ChatMessageWidget(msg_yt, settings)
    assert "YT" in widget_yt.user_label.text()


def test_overlay_chat_filtering(qapp, tmp_path):
    config_file = tmp_path / "test_filter_config.json"
    cfg = ConfigManager(custom_path=config_file)
    cfg.settings.filter_bot_commands = True
    cfg.settings.filter_duplicates = True
    cfg.settings.filter_duplicate_window_sec = 5.0

    cap = CaptureProtectionManager()
    style = WindowStyleManager()
    overlay = OverlayWindow(cfg, cap, style)

    # 1. Normal message should be added
    msg1 = ChatMessage(username="viewer", message="Hello world!")
    overlay.add_message(msg1)
    assert len(overlay._messages) == 1

    # 2. Bot command message should be filtered out
    msg_bot = ChatMessage(username="viewer", message="!sens")
    overlay.add_message(msg_bot)
    assert len(overlay._messages) == 1  # Unchanged!

    # 3. Duplicate message should be filtered out
    msg_dup = ChatMessage(username="viewer", message="Hello world!")
    overlay.add_message(msg_dup)
    assert len(overlay._messages) == 1  # Unchanged!

    # 4. Different text passes
    msg2 = ChatMessage(username="viewer", message="Different text")
    overlay.add_message(msg2)
    assert len(overlay._messages) == 2


def test_settings_window_v12_tabs_and_controls(qapp, tmp_path):
    config_file = tmp_path / "test_settings_v12.json"
    cfg = ConfigManager(custom_path=config_file)
    cap = CaptureProtectionManager()

    settings_win = SettingsWindow(cfg, cap)

    # Verify Companion tab controls
    assert hasattr(settings_win, "companion_enable_cb")
    assert hasattr(settings_win, "companion_port_spin")
    assert hasattr(settings_win, "companion_pin_edit")
    assert hasattr(settings_win, "qr_widget")

    # Verify Multistream controls
    assert hasattr(settings_win, "multi_enable_cb")
    assert hasattr(settings_win, "multi_tw_cb")
    assert hasattr(settings_win, "multi_kick_cb")
    assert hasattr(settings_win, "multi_yt_cb")

    # Verify Smart Filter controls
    assert hasattr(settings_win, "filter_bot_cb")
    assert hasattr(settings_win, "filter_dup_cb")
    assert hasattr(settings_win, "filter_dup_spin")

    # Verify Windows startup control
    assert hasattr(settings_win, "startup_cb")

    # Verify scroll areas and tab ergonomics
    from PySide6.QtWidgets import QGroupBox, QScrollArea

    assert settings_win.tabs.count() >= 9
    assert settings_win.tabs.usesScrollButtons() is False
    for i in range(settings_win.tabs.count()):
        assert isinstance(settings_win.tabs.widget(i), QScrollArea)

    # Verify no QGroupBox has an unescaped single ampersand (which causes unwanted accelerator underlines)
    for gb in settings_win.findChildren(QGroupBox):
        title = gb.title()
        if "&" in title:
            assert "&&" in title, f"QGroupBox title '{title}' contains single '&' mnemonic!"

    # Verify input fields have sufficient minimum height to prevent clipping
    assert settings_win.provider_combo.minimumHeight() >= 28
    assert settings_win.twitch_channel_edit.minimumHeight() >= 28
    assert settings_win.kick_channel_edit.minimumHeight() >= 28
    assert settings_win.yt_id_edit.minimumHeight() >= 28


def test_app_obs_companion_integration(qapp, tmp_path, monkeypatch):
    from kronos_veil.app import KronosVeilApp
    from kronos_veil.hotkeys import HotkeyManager
    from kronos_veil.obs.client import OBSStreamStats

    cfg_file = tmp_path / "test_app_config.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cfg.settings.companion_enabled = False

    monkeypatch.setattr(HotkeyManager, "register_hotkey", lambda *args, **kwargs: True)

    app_instance = KronosVeilApp(cfg)

    # 1. Test stats update when OBS stats arrive (must not raise AttributeError)
    stats = OBSStreamStats(is_connected=False, is_live=False, bitrate_kbps=0)
    app_instance._on_obs_stats_updated(stats)

    # 2. Test companion actions without OBS connected (must not raise AttributeError)
    app_instance._on_companion_action("obs_toggle_stream", {})
    app_instance._on_companion_action("obs_toggle_record", {})
    app_instance._on_companion_action("obs_set_scene", {"scene_name": "Game"})
    app_instance._on_companion_action("toggle_clickthrough", {})
    app_instance._on_companion_action("test_alert", {})
    app_instance._on_companion_action("clear_chat", {})
