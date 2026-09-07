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
