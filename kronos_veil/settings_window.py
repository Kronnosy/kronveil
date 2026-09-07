"""
Settings and Control Window for Kronos Veil.
Provides a modern dark HUD interface to adjust visual properties, manage capture protection,
configure chat providers, and test OBS visibility.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from kronos_veil.config import ConfigManager
from kronos_veil.windows.capture_protection import (
    CaptureProtectionManager,
    CaptureProtectionStatus,
)

logger = logging.getLogger(__name__)

HUD_STYLESHEET = """
QWidget {
    background-color: #0f141c;
    color: #e2e8f0;
    font-family: 'Segoe UI', sans-serif;
    font-size: 9.5pt;
}

QTabWidget::pane {
    border: 1px solid #1e293b;
    background-color: #0f141c;
    border-radius: 4px;
}

QTabBar::tab {
    background-color: #1e293b;
    color: #94a3b8;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #0f141c;
    color: #00e5ff;
    border-top: 2px solid #00e5ff;
}

QGroupBox {
    border: 1px solid #1e293b;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 14px;
    font-weight: 600;
    color: #38bdf8;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    color: #00e5ff;
}

QPushButton {
    background-color: #1e293b;
    border: 1px solid #334155;
    color: #f1f5f9;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #334155;
    border-color: #00e5ff;
}

QPushButton:pressed {
    background-color: #0284c7;
    color: #ffffff;
}

QPushButton#PrimaryBtn {
    background-color: #0284c7;
    border-color: #38bdf8;
    color: #ffffff;
}

QPushButton#PrimaryBtn:hover {
    background-color: #0369a1;
}

QLineEdit, QSpinBox, QComboBox {
    background-color: #161f2e;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 5px 8px;
    color: #f8fafc;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #00e5ff;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #1e293b;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background: #00e5ff;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #f8fafc;
    border: 1px solid #00e5ff;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #475569;
    background-color: #161f2e;
}

QCheckBox::indicator:checked {
    background-color: #00e5ff;
    border-color: #00e5ff;
}
"""


class SettingsWindow(QWidget):
    """Configuration dialog for Kronos Veil."""

    settings_changed = Signal()
    demo_message_requested = Signal()
    clear_chat_requested = Signal()
    capture_test_toggled = Signal(bool)
    reset_position_requested = Signal()
    provider_reconnect_requested = Signal()

    def __init__(
        self,
        config_mgr: ConfigManager,
        capture_mgr: CaptureProtectionManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_mgr = config_mgr
        self.settings = config_mgr.settings
        self.capture_mgr = capture_mgr

        self.setWindowTitle("Kronos Veil — Settings & Control Panel")
        self.resize(520, 560)
        self.setStyleSheet(HUD_STYLESHEET)

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # Header Title Banner
        header = QHBoxLayout()
        title_lbl = QLabel("KRONOS VEIL", self)
        title_lbl.setStyleSheet("font-size: 14pt; font-weight: 800; color: #00e5ff; letter-spacing: 1.5px;")
        tagline_lbl = QLabel("Private Streamer Chat Overlay", self)
        tagline_lbl.setStyleSheet("font-size: 9pt; color: #94a3b8;")

        header.addWidget(title_lbl)
        header.addWidget(tagline_lbl)
        header.addStretch()
        main_layout.addLayout(header)

        # Tabs
        tabs = QTabWidget(self)
        tabs.addTab(self._create_privacy_tab(), "🛡️ Privacy & OBS")
        tabs.addTab(self._create_mode_tab(), "🎮 Overlay & Modes")
        tabs.addTab(self._create_visual_tab(), "🎨 Visuals & Style")
        tabs.addTab(self._create_chat_tab(), "💬 Chat Provider")
        tabs.addTab(self._create_system_tab(), "⚙️ System")

        main_layout.addWidget(tabs, 1)

        # Footer Buttons
        footer = QHBoxLayout()
        self.save_btn = QPushButton("Save & Close", self)
        self.save_btn.setObjectName("PrimaryBtn")
        self.save_btn.clicked.connect(self._on_save_clicked)

        footer.addStretch()
        footer.addWidget(self.save_btn)
        main_layout.addLayout(footer)

    def _create_privacy_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Status Box
        status_box = QGroupBox("Capture Protection Status", tab)
        status_layout = QVBoxLayout(status_box)

        badge_row = QHBoxLayout()
        self.status_badge = QLabel(self)
        self.status_badge.setStyleSheet("padding: 4px 12px; border-radius: 4px; font-weight: 700; font-size: 10pt;")
        self._update_status_badge()
        badge_row.addWidget(QLabel("Current Status: "))
        badge_row.addWidget(self.status_badge)
        badge_row.addStretch()
        status_layout.addLayout(badge_row)

        self.status_detail_lbl = QLabel(self.capture_mgr.last_error_message, self)
        self.status_detail_lbl.setWordWrap(True)
        self.status_detail_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        status_layout.addWidget(self.status_detail_lbl)

        self.cap_protect_cb = QCheckBox("Enable Windows Capture Exclusion (WDA_EXCLUDEFROMCAPTURE)", self)
        self.cap_protect_cb.setChecked(self.settings.capture_protection)
        self.cap_protect_cb.toggled.connect(self._on_capture_protect_toggled)
        status_layout.addWidget(self.cap_protect_cb)

        layout.addWidget(status_box)

        # OBS Verification / Test Mode
        test_box = QGroupBox("OBS Capture Test Mode", tab)
        test_layout = QVBoxLayout(test_box)

        test_info = QLabel(
            "Activate Test Mode to display a high-contrast diagnostic pattern on the overlay. "
            "Open your OBS Studio preview to confirm whether the overlay is hidden.",
            tab,
        )
        test_info.setWordWrap(True)
        test_info.setStyleSheet("color: #cbd5e1; font-size: 8.5pt;")
        test_layout.addWidget(test_info)

        self.test_mode_btn = QPushButton("Toggle Capture Test Mode Banner", tab)
        self.test_mode_btn.setCheckable(True)
        self.test_mode_btn.toggled.connect(self.capture_test_toggled.emit)
        test_layout.addWidget(self.test_mode_btn)

        layout.addWidget(test_box)

        # OBS Guidelines
        info_box = QGroupBox("OBS Capture Guidance", tab)
        info_layout = QVBoxLayout(info_box)
        guidance_text = (
            "<b>Recommended OBS Sources:</b><br>"
            "• <b>Game Capture:</b> 100% Recommended. Captures the game process directly via DirectX/Vulkan; overlays are never captured.<br>"
            "• <b>Window Capture:</b> Compatible when using 'Windows Graphics Capture' method.<br>"
            "• <b>Display Capture:</b> May capture desktop overlays depending on Windows build and GPU configuration.<br><br>"
            "<i>Note: Always verify your stream preview in OBS before going live.</i>"
        )
        info_lbl = QLabel(guidance_text, tab)
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt; line-height: 1.4;")
        info_layout.addWidget(info_lbl)
        layout.addWidget(info_box)

        layout.addStretch()
        return tab

    def _create_mode_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        mode_box = QGroupBox("Overlay Operational Mode", tab)
        mode_layout = QVBoxLayout(mode_box)

        self.lock_cb = QCheckBox("Lock Overlay (Hide borders and edit controls)", tab)
        self.lock_cb.setChecked(self.settings.locked)
        self.lock_cb.toggled.connect(self._on_lock_toggled)
        mode_layout.addWidget(self.lock_cb)

        self.click_through_cb = QCheckBox("Click-Through Mode (Pass all mouse clicks to game)", tab)
        self.click_through_cb.setChecked(self.settings.click_through)
        self.click_through_cb.toggled.connect(self._on_click_through_toggled)
        mode_layout.addWidget(self.click_through_cb)

        layout.addWidget(mode_box)

        hotkey_box = QGroupBox("Configured Global Hotkeys", tab)
        hotkey_layout = QFormLayout(hotkey_box)

        self.hotkey_lock_lbl = QLabel(self.settings.hotkey_toggle_lock, tab)
        self.hotkey_lock_lbl.setStyleSheet("color: #00e5ff; font-weight: bold;")
        hotkey_layout.addRow("Toggle Edit / Lock:", self.hotkey_lock_lbl)

        self.hotkey_ct_lbl = QLabel(self.settings.hotkey_toggle_clickthrough, tab)
        self.hotkey_ct_lbl.setStyleSheet("color: #00e5ff; font-weight: bold;")
        hotkey_layout.addRow("Toggle Click-Through:", self.hotkey_ct_lbl)

        self.hotkey_peek_lbl = QLabel(self.settings.hotkey_peek, tab)
        self.hotkey_peek_lbl.setStyleSheet("color: #00e5ff; font-weight: bold;")
        hotkey_layout.addRow("Peek Chat:", self.hotkey_peek_lbl)

        layout.addWidget(hotkey_box)

        help_lbl = QLabel(
            "Hotkeys function system-wide even when full-screen games have focus. "
            "Use them anytime to recover control from click-through mode.",
            tab,
        )
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt; font-style: italic;")
        layout.addWidget(help_lbl)

        layout.addStretch()
        return tab

    def _create_visual_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        form_box = QGroupBox("Chat Appearance & Styling", tab)
        form = QFormLayout(form_box)

        # Overlay Opacity
        self.overlay_opacity_slider = QSlider(Qt.Orientation.Horizontal, tab)
        self.overlay_opacity_slider.setRange(10, 100)
        self.overlay_opacity_slider.setValue(int(self.settings.overlay_opacity * 100))
        self.overlay_opacity_val = QLabel(f"{self.overlay_opacity_slider.value()}%", tab)
        self.overlay_opacity_slider.valueChanged.connect(
            lambda v: (
                self.overlay_opacity_val.setText(f"{v}%"),
                setattr(self.settings, "overlay_opacity", v / 100.0),
                self.settings_changed.emit(),
            )
        )
        row1 = QHBoxLayout()
        row1.addWidget(self.overlay_opacity_slider)
        row1.addWidget(self.overlay_opacity_val)
        form.addRow("Overlay Opacity:", row1)

        # Background Opacity
        self.bg_opacity_slider = QSlider(Qt.Orientation.Horizontal, tab)
        self.bg_opacity_slider.setRange(0, 100)
        self.bg_opacity_slider.setValue(int(self.settings.background_opacity * 100))
        self.bg_opacity_val = QLabel(f"{self.bg_opacity_slider.value()}%", tab)
        self.bg_opacity_slider.valueChanged.connect(
            lambda v: (
                self.bg_opacity_val.setText(f"{v}%"),
                setattr(self.settings, "background_opacity", v / 100.0),
                self.settings_changed.emit(),
            )
        )
        row2 = QHBoxLayout()
        row2.addWidget(self.bg_opacity_slider)
        row2.addWidget(self.bg_opacity_val)
        form.addRow("Background Opacity:", row2)

        # Font Size
        self.font_spin = QSpinBox(tab)
        self.font_spin.setRange(9, 28)
        self.font_spin.setValue(self.settings.font_size)
        self.font_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "font_size", v), self.settings_changed.emit())
        )
        form.addRow("Font Size (pt):", self.font_spin)

        # Message Spacing
        self.spacing_spin = QSpinBox(tab)
        self.spacing_spin.setRange(1, 20)
        self.spacing_spin.setValue(self.settings.message_spacing)
        self.spacing_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "message_spacing", v), self.settings_changed.emit())
        )
        form.addRow("Row Spacing (px):", self.spacing_spin)

        # Max Messages
        self.max_msg_spin = QSpinBox(tab)
        self.max_msg_spin.setRange(5, 100)
        self.max_msg_spin.setValue(self.settings.max_messages)
        self.max_msg_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "max_messages", v), self.settings_changed.emit())
        )
        form.addRow("Max Messages:", self.max_msg_spin)

        # Message Lifetime
        self.lifetime_spin = QSpinBox(tab)
        self.lifetime_spin.setRange(0, 300)
        self.lifetime_spin.setSpecialValueText("Never Expire")
        self.lifetime_spin.setValue(self.settings.message_lifetime_sec)
        self.lifetime_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "message_lifetime_sec", v), self.settings_changed.emit())
        )
        form.addRow("Message Expiry (sec):", self.lifetime_spin)

        # Toggles
        self.timestamp_cb = QCheckBox("Show Timestamps", tab)
        self.timestamp_cb.setChecked(self.settings.show_timestamps)
        self.timestamp_cb.toggled.connect(
            lambda v: (setattr(self.settings, "show_timestamps", v), self.settings_changed.emit())
        )
        form.addRow(self.timestamp_cb)

        self.username_cb = QCheckBox("Show Usernames", tab)
        self.username_cb.setChecked(self.settings.show_usernames)
        self.username_cb.toggled.connect(
            lambda v: (setattr(self.settings, "show_usernames", v), self.settings_changed.emit())
        )
        form.addRow(self.username_cb)

        self.shadow_cb = QCheckBox("Render Text Shadow (Increases In-Game Legibility)", tab)
        self.shadow_cb.setChecked(self.settings.text_shadow)
        self.shadow_cb.toggled.connect(
            lambda v: (setattr(self.settings, "text_shadow", v), self.settings_changed.emit())
        )
        form.addRow(self.shadow_cb)

        layout.addWidget(form_box)
        layout.addStretch()
        return tab

    def _create_chat_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        box = QGroupBox("Active Chat Stream", tab)
        form = QFormLayout(box)

        self.provider_combo = QComboBox(tab)
        self.provider_combo.addItems(["Local Demo Simulation", "Twitch Live Chat", "YouTube Live Chat"])
        current_map = {"demo": 0, "twitch": 1, "youtube": 2}
        self.provider_combo.setCurrentIndex(current_map.get(self.settings.chat_provider, 0))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_selection_changed)
        form.addRow("Provider:", self.provider_combo)

        # Twitch Channel
        self.twitch_channel_edit = QLineEdit(tab)
        self.twitch_channel_edit.setPlaceholderText("e.g. shroud or yourchannel")
        self.twitch_channel_edit.setText(self.settings.twitch_channel)
        self.twitch_channel_edit.textChanged.connect(
            lambda t: setattr(self.settings, "twitch_channel", t.strip())
        )
        form.addRow("Twitch Channel:", self.twitch_channel_edit)

        # YouTube Video ID
        self.yt_id_edit = QLineEdit(tab)
        self.yt_id_edit.setPlaceholderText("e.g. jfKfPfyJRdk (Live Stream Video ID)")
        self.yt_id_edit.setText(self.settings.youtube_video_id)
        self.yt_id_edit.textChanged.connect(
            lambda t: setattr(self.settings, "youtube_video_id", t.strip())
        )
        form.addRow("YouTube Video ID:", self.yt_id_edit)

        layout.addWidget(box)

        # Chat actions
        action_box = QGroupBox("Testing & Actions", tab)
        action_layout = QHBoxLayout(action_box)

        self.demo_msg_btn = QPushButton("Send Demo Message", tab)
        self.demo_msg_btn.clicked.connect(self.demo_message_requested.emit)
        action_layout.addWidget(self.demo_msg_btn)

        self.clear_chat_btn = QPushButton("Clear Chat", tab)
        self.clear_chat_btn.clicked.connect(self.clear_chat_requested.emit)
        action_layout.addWidget(self.clear_chat_btn)

        self.reconnect_btn = QPushButton("Reconnect Stream", tab)
        self.reconnect_btn.clicked.connect(self.provider_reconnect_requested.emit)
        action_layout.addWidget(self.reconnect_btn)

        layout.addWidget(action_box)

        help_text = QLabel(
            "<b>Twitch:</b> Connects anonymously to public chat via SSL IRC — zero tokens or developer apps required.<br>"
            "<b>Demo:</b> Generates realistic messages periodically without network requirements.",
            tab,
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        layout.addWidget(help_text)

        layout.addStretch()
        return tab

    def _create_system_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        recovery_box = QGroupBox("Multi-Monitor & Window Recovery", tab)
        recovery_layout = QVBoxLayout(recovery_box)

        rec_lbl = QLabel(
            "If the overlay window was moved off-screen, or monitor arrangement changed, "
            "reset coordinates to place it visibly on your primary display.",
            tab,
        )
        rec_lbl.setWordWrap(True)
        rec_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        recovery_layout.addWidget(rec_lbl)

        self.reset_pos_btn = QPushButton("Reset Overlay Position to Primary Screen", tab)
        self.reset_pos_btn.clicked.connect(self.reset_position_requested.emit)
        recovery_layout.addWidget(self.reset_pos_btn)

        layout.addWidget(recovery_box)

        defaults_box = QGroupBox("Restore Defaults", tab)
        defaults_layout = QVBoxLayout(defaults_box)

        self.reset_all_btn = QPushButton("Reset All Settings to Factory Defaults", tab)
        self.reset_all_btn.setStyleSheet("color: #ef4444; border-color: #7f1d1d;")
        self.reset_all_btn.clicked.connect(self._on_reset_all_clicked)
        defaults_layout.addWidget(self.reset_all_btn)

        layout.addWidget(defaults_box)
        layout.addStretch()
        return tab

    def _update_status_badge(self) -> None:
        status = self.capture_mgr.status
        colors = {
            CaptureProtectionStatus.ACTIVE: ("#052e16", "#22c55e", "ACTIVE (Protected from OBS)"),
            CaptureProtectionStatus.UNSUPPORTED: ("#451a03", "#f59e0b", "UNSUPPORTED (OS/DWM limitation)"),
            CaptureProtectionStatus.FAILED: ("#450a0a", "#ef4444", "FAILED (API error)"),
            CaptureProtectionStatus.DISABLED: ("#1e293b", "#94a3b8", "DISABLED"),
        }
        bg, fg, text = colors.get(status, ("#1e293b", "#94a3b8", str(status)))
        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border: 1px solid {fg}; "
            f"padding: 4px 10px; border-radius: 4px; font-weight: bold;"
        )

    def refresh_from_settings(self) -> None:
        """Syncs GUI controls with current AppSettings state."""
        self.lock_cb.setChecked(self.settings.locked)
        self.click_through_cb.setChecked(self.settings.click_through)
        self.cap_protect_cb.setChecked(self.settings.capture_protection)
        self._update_status_badge()
        self.status_detail_lbl.setText(self.capture_mgr.last_error_message)

    def _on_capture_protect_toggled(self, checked: bool) -> None:
        self.settings.capture_protection = checked
        self.config_mgr.save()
        self.settings_changed.emit()
        self._update_status_badge()
        self.status_detail_lbl.setText(self.capture_mgr.last_error_message)

    def _on_lock_toggled(self, checked: bool) -> None:
        self.settings.locked = checked
        self.config_mgr.save()
        self.settings_changed.emit()

    def _on_click_through_toggled(self, checked: bool) -> None:
        self.settings.click_through = checked
        self.config_mgr.save()
        self.settings_changed.emit()

    def _on_provider_selection_changed(self, index: int) -> None:
        keys = ["demo", "twitch", "youtube"]
        self.settings.chat_provider = keys[index]
        self.config_mgr.save()
        self.provider_reconnect_requested.emit()

    def _on_reset_all_clicked(self) -> None:
        from kronos_veil.config import AppSettings
        self.config_mgr.settings = AppSettings()
        self.settings = self.config_mgr.settings
        self.config_mgr.save()
        self.refresh_from_settings()
        self.settings_changed.emit()

    def _on_save_clicked(self) -> None:
        self.config_mgr.save()
        self.settings_changed.emit()
        self.hide()
