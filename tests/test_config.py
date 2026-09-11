"""Unit tests for Kronos Veil configuration and recovery."""

import json
from pathlib import Path
import pytest
from kronos_veil.config import AppSettings, ConfigManager


def test_default_settings():
    settings = AppSettings()
    assert settings.overlay_width == 380
    assert settings.overlay_height == 520
    assert settings.overlay_opacity == 0.95
    assert settings.locked is False
    assert settings.click_through is False
    assert settings.capture_protection is True
    assert settings.chat_provider == "demo"


def test_settings_validation_clamping():
    settings = AppSettings(
        overlay_width=10000,
        overlay_height=10,
        overlay_opacity=2.5,
        background_opacity=-0.5,
        font_size=50,
        max_messages=500,
        chat_provider="invalid_provider",
    )
    settings.validate()
    assert settings.overlay_width == 3804 or settings.overlay_width == 3840
    assert settings.overlay_height == 150
    assert settings.overlay_opacity == 1.0
    assert settings.background_opacity == 0.0
    assert settings.font_size == 36
    assert settings.max_messages == 200
    assert settings.chat_provider == "demo"


def test_corrupted_json_fallback(tmp_path: Path):
    corrupt_file = tmp_path / "settings.json"
    corrupt_file.write_text("{ this is corrupt json !!!", encoding="utf-8")

    mgr = ConfigManager(custom_path=corrupt_file)
    assert mgr.settings.overlay_width == 380
    assert mgr.settings.overlay_height == 520


def test_config_save_and_load(tmp_path: Path):
    config_file = tmp_path / "settings.json"
    mgr = ConfigManager(custom_path=config_file)
    mgr.settings.overlay_x = 120
    mgr.settings.overlay_y = 200
    mgr.settings.locked = True
    assert mgr.save() is True

    # Reload fresh
    mgr2 = ConfigManager(custom_path=config_file)
    assert mgr2.settings.overlay_x == 120
    assert mgr2.settings.overlay_y == 200
    assert mgr2.settings.locked is True


def test_multi_monitor_coordinate_sanitization(tmp_path: Path):
    config_file = tmp_path / "settings.json"
    mgr = ConfigManager(custom_path=config_file)
    # Put overlay completely off-screen at (-2000, -2000)
    mgr.settings.overlay_x = -2000
    mgr.settings.overlay_y = -2000

    # Connected monitor: Primary at (0, 0, 1920, 1080)
    screens = [(0, 0, 1920, 1080)]
    safe_x, safe_y = mgr.sanitize_coordinates(screens)

    assert safe_x == 60
    assert safe_y == 100
    assert mgr.settings.overlay_x == 60
    assert mgr.settings.overlay_y == 100


def test_new_feature_settings():
    settings = AppSettings(
        chat_provider="kick",
        kick_channel="xqc",
        emotes_enabled=True,
        obs_enabled=True,
        obs_port=4455,
        hud_enabled=True,
        hud_x=100,
        hud_y=50,
    )
    settings.validate()
    assert settings.chat_provider == "kick"
    assert settings.kick_channel == "xqc"
    assert settings.emotes_enabled is True
    assert settings.obs_enabled is True
    assert settings.obs_port == 4455
    assert settings.hud_enabled is True
    assert settings.hud_x == 100
    assert settings.hud_y == 50


def test_v13_gsi_hype_qa_settings():
    settings = AppSettings()
    # Test default values
    assert settings.gsi_enabled is False
    assert settings.gsi_port == 31337
    assert settings.clutch_mode_enabled is True
    assert settings.clutch_dim_opacity == 0.0
    assert settings.clutch_health_threshold == 25

    assert settings.hype_detector_enabled is True
    assert settings.hype_window_seconds == 15
    assert settings.hype_threshold_rate == 3.5
    assert settings.hype_auto_clip is False
    assert settings.hype_cooldown_seconds == 60

    assert settings.qa_deck_enabled is False
    assert settings.qa_max_items == 20
    assert settings.qa_auto_expire_seconds == 300


def test_v13_settings_validation_clamping():
    settings = AppSettings(
        gsi_port=80,  # below 1024
        clutch_dim_opacity=-0.5,  # below 0.0
        clutch_health_threshold=150,  # above 100
        hype_window_seconds=1,  # below 3
        hype_threshold_rate=0.1,  # below 0.5
        hype_cooldown_seconds=1000,  # above 600
        qa_max_items=500,  # above 100
        qa_auto_expire_seconds=10,  # below 30
    )
    settings.validate()
    assert settings.gsi_port == 1024
    assert settings.clutch_dim_opacity == 0.0
    assert settings.clutch_health_threshold == 100
    assert settings.hype_window_seconds == 3
    assert settings.hype_threshold_rate == 0.5
    assert settings.hype_cooldown_seconds == 600
    assert settings.qa_max_items == 100
    assert settings.qa_auto_expire_seconds == 30

    # Test upper bound clamps
    settings2 = AppSettings(
        gsi_port=99999,
        clutch_dim_opacity=2.5,
        clutch_health_threshold=0,
        hype_window_seconds=300,
        hype_threshold_rate=500.0,
        hype_cooldown_seconds=1,
        qa_max_items=2,
        qa_auto_expire_seconds=9999,
    )
    settings2.validate()
    assert settings2.gsi_port == 65535
    assert settings2.clutch_dim_opacity == 1.0
    assert settings2.clutch_health_threshold == 1
    assert settings2.hype_window_seconds == 120
    assert settings2.hype_threshold_rate == 100.0
    assert settings2.hype_cooldown_seconds == 5
    assert settings2.qa_max_items == 5
    assert settings2.qa_auto_expire_seconds == 3600

