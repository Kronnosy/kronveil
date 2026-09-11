"""Unit tests for SettingsWindow 'Game & AI Intelligence' Tab and UI bindings."""

from pathlib import Path
import pytest
from PySide6.QtCore import Qt

from kronos_veil.config import ConfigManager
from kronos_veil.settings_window import SettingsWindow
from kronos_veil.windows.capture_protection import CaptureProtectionManager


def test_intelligence_tab_controls_and_bindings(qapp, tmp_path):
    cfg_file = tmp_path / "test_settings_intel.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()

    win = SettingsWindow(cfg, cap)
    win.show()

    # 1. Verify GSI & Clutch Mode controls exist
    assert hasattr(win, "gsi_enable_cb")
    assert hasattr(win, "gsi_port_spin")
    assert hasattr(win, "gsi_token_edit")
    assert hasattr(win, "install_cfg_btn")
    assert hasattr(win, "uninstall_cfg_btn")
    assert hasattr(win, "cfg_status_lbl")
    assert hasattr(win, "clutch_enable_cb")
    assert hasattr(win, "clutch_dim_slider")
    assert hasattr(win, "clutch_dim_lbl")
    assert hasattr(win, "clutch_health_spin")
    assert hasattr(win, "sim_clutch_btn")

    # 2. Verify Hype Spike Engine controls exist
    assert hasattr(win, "hype_enable_cb")
    assert hasattr(win, "hype_window_spin")
    assert hasattr(win, "hype_threshold_spin")
    assert hasattr(win, "hype_autoclip_cb")
    assert hasattr(win, "hype_cooldown_spin")
    assert hasattr(win, "sim_hype_btn")

    # 3. Verify Smart Q&A Deck controls exist
    assert hasattr(win, "qa_deck_enable_cb")
    assert hasattr(win, "qa_deck_lock_cb")
    assert hasattr(win, "qa_max_items_spin")
    assert hasattr(win, "qa_auto_expire_spin")
    assert hasattr(win, "reset_qa_deck_btn")
    assert hasattr(win, "clear_qa_deck_btn")

    # 4. Test UI -> Config value bindings
    # GSI
    assert win.gsi_enable_cb.isChecked() is False
    win.gsi_enable_cb.setChecked(True)
    assert cfg.settings.gsi_enabled is True

    win.gsi_port_spin.setValue(31338)
    assert cfg.settings.gsi_port == 31338

    win.gsi_token_edit.setText("my_secret_token")
    assert cfg.settings.gsi_auth_token == "my_secret_token"

    # Clutch
    assert win.clutch_enable_cb.isChecked() is True
    win.clutch_enable_cb.setChecked(False)
    assert cfg.settings.clutch_mode_enabled is False

    win.clutch_dim_slider.setValue(25)
    assert abs(cfg.settings.clutch_dim_opacity - 0.25) < 0.01
    assert win.clutch_dim_lbl.text() == "25%"

    win.clutch_health_spin.setValue(30)
    assert cfg.settings.clutch_health_threshold == 30

    # Hype
    assert win.hype_enable_cb.isChecked() is True
    win.hype_enable_cb.setChecked(False)
    assert cfg.settings.hype_detector_enabled is False

    win.hype_window_spin.setValue(20)
    assert cfg.settings.hype_window_seconds == 20

    win.hype_threshold_spin.setValue(5.5)
    assert abs(cfg.settings.hype_threshold_rate - 5.5) < 0.01

    win.hype_autoclip_cb.setChecked(True)
    assert cfg.settings.hype_auto_clip is True

    win.hype_cooldown_spin.setValue(45)
    assert cfg.settings.hype_cooldown_seconds == 45

    # Q&A Deck
    assert win.qa_deck_enable_cb.isChecked() is False
    win.qa_deck_enable_cb.setChecked(True)
    assert cfg.settings.qa_deck_enabled is True

    assert win.qa_deck_lock_cb.isChecked() is False
    win.qa_deck_lock_cb.setChecked(True)
    assert cfg.settings.qa_deck_locked is True

    win.qa_max_items_spin.setValue(35)
    assert cfg.settings.qa_max_items == 35

    win.qa_auto_expire_spin.setValue(450)
    assert cfg.settings.qa_auto_expire_seconds == 450

    # 5. Test Signal Emissions
    clutch_sim_emitted = []
    hype_sim_emitted = []
    reset_qa_emitted = []
    clear_qa_emitted = []
    qa_toggle_emitted = []
    qa_lock_emitted = []

    win.simulate_clutch_requested.connect(lambda: clutch_sim_emitted.append(True))
    win.simulate_hype_requested.connect(lambda: hype_sim_emitted.append(True))
    win.reset_qa_deck_position_requested.connect(lambda: reset_qa_emitted.append(True))
    win.clear_qa_deck_requested.connect(lambda: clear_qa_emitted.append(True))
    win.qa_deck_toggled.connect(lambda v: qa_toggle_emitted.append(v))
    win.qa_deck_lock_toggled.connect(lambda v: qa_lock_emitted.append(v))

    win.sim_clutch_btn.click()
    assert len(clutch_sim_emitted) == 1

    win.sim_hype_btn.click()
    assert len(hype_sim_emitted) == 1

    win.reset_qa_deck_btn.click()
    assert len(reset_qa_emitted) == 1

    win.clear_qa_deck_btn.click()
    assert len(clear_qa_emitted) == 1

    win.qa_deck_enable_cb.setChecked(False)
    assert qa_toggle_emitted == [False]

    win.qa_deck_lock_cb.setChecked(False)
    assert qa_lock_emitted == [False]

    # 6. Test refresh_from_settings
    cfg.settings.gsi_enabled = False
    cfg.settings.clutch_dim_opacity = 0.50
    cfg.settings.qa_max_items = 50
    win.refresh_from_settings()

    assert win.gsi_enable_cb.isChecked() is False
    assert win.clutch_dim_slider.value() == 50
    assert win.clutch_dim_lbl.text() == "50%"
    assert win.qa_max_items_spin.value() == 50

    win.close()


def test_cfg_install_buttons(qapp, tmp_path, monkeypatch):
    import kronos_veil.settings_window as sw

    cfg_file = tmp_path / "test_settings_cfg.json"
    cfg = ConfigManager(custom_path=cfg_file)
    cap = CaptureProtectionManager()

    win = SettingsWindow(cfg, cap)

    # Mock install_cfg and uninstall_cfg in settings_window
    monkeypatch.setattr(
        sw,
        "install_cfg",
        lambda port, auth_token: (True, "Installed successfully"),
    )
    monkeypatch.setattr(
        sw,
        "uninstall_cfg",
        lambda: (True, "Removed successfully"),
    )

    win.install_cfg_btn.click()
    assert "Installed successfully" in win.cfg_status_lbl.text()

    win.uninstall_cfg_btn.click()
    assert "Removed successfully" in win.cfg_status_lbl.text()

    win.close()
