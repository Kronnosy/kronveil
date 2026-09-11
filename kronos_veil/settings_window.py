"""
Settings and Control Window for Kronos Veil.
Provides a modern dark HUD interface to adjust visual properties, manage capture protection,
configure chat providers, and test OBS visibility.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from kronos_veil.autostart import is_autostart_enabled, is_autostart_supported, set_autostart
from kronos_veil.chat.base import ChatMessage
from kronos_veil.config import ConfigManager
from kronos_veil.gsi.installer import install_cfg, uninstall_cfg, verify_cfg_installed
from kronos_veil.overlay import ChatMessageWidget
from kronos_veil.profiles import GameProfile, ProfileManager, detect_foreground_window
from kronos_veil.themes import THEME_PRESETS, get_theme
from kronos_veil.web.companion import get_local_lan_ip
from kronos_veil.web.qr import generate_qr_svg
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
    padding: 6px 10px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-weight: 600;
    font-size: 8.5pt;
}

QTabBar::tab:selected {
    background-color: #0f141c;
    color: #00e5ff;
    border-top: 2px solid #00e5ff;
}

QTabBar::tab:hover:!selected {
    background-color: #273549;
    color: #cbd5e1;
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

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #161f2e;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 28px;
    color: #f8fafc;
    font-size: 9.5pt;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #00e5ff;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid #334155;
}

QComboBox QAbstractItemView {
    background-color: #0f172a;
    border: 1px solid #334155;
    selection-background-color: #0284c7;
    color: #f8fafc;
    padding: 4px;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    width: 8px;
    background: #0f141c;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 4px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #00e5ff;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
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
    obs_connect_requested = Signal()
    reset_hud_position_requested = Signal()
    hud_toggled = Signal(bool)
    hud_lock_toggled = Signal(bool)

    # Modular Widgets signals
    event_deck_toggled = Signal(bool)
    event_deck_lock_toggled = Signal(bool)
    reset_event_deck_position_requested = Signal()
    simulate_event_requested = Signal()

    # Profiles signals
    profile_applied = Signal(str)
    save_current_profile_requested = Signal(str)

    # Companion signals
    companion_restart_requested = Signal()

    # Game & AI Intelligence signals
    gsi_toggled = Signal(bool)
    clutch_mode_toggled = Signal(bool)
    simulate_clutch_requested = Signal()
    simulate_hype_requested = Signal()
    qa_deck_toggled = Signal(bool)
    qa_deck_lock_toggled = Signal(bool)
    reset_qa_deck_position_requested = Signal()
    clear_qa_deck_requested = Signal()

    def __init__(
        self,
        config_mgr: ConfigManager,
        capture_mgr: CaptureProtectionManager,
        profile_mgr: Optional[ProfileManager] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_mgr = config_mgr
        self.settings = config_mgr.settings
        self.capture_mgr = capture_mgr
        self.profile_mgr = profile_mgr

        self.setWindowTitle("Kronos Veil — Settings && Control Panel")
        self.resize(860, 720)
        self.setMinimumSize(800, 640)
        self.setStyleSheet(HUD_STYLESHEET)

        self._init_ui()

    @staticmethod
    def _wrap_in_scroll_area(widget: QWidget) -> QScrollArea:
        """Wraps a tab content widget in a frameless vertical scroll area to prevent clipping."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(widget)
        return scroll

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

        # Tabs (Concise labels with hover tooltips to fit perfectly on all screens without scroll arrows)
        self.tabs = QTabWidget(self)
        self.tabs.setUsesScrollButtons(False)
        self.tabs.setElideMode(Qt.TextElideMode.ElideNone)

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_privacy_tab()), "🛡️ Privacy")
        self.tabs.setTabToolTip(0, "Privacy & OBS Capture Protection")

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_mode_tab()), "🎮 Overlay")
        self.tabs.setTabToolTip(1, "Overlay Geometry & Interaction Modes")

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_visual_tab()), "🎨 Visuals")
        self.tabs.setTabToolTip(2, "Broadcast Themes, Typography & Styles")

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_chat_tab()), "💬 Chat")
        self.tabs.setTabToolTip(3, "Chat Providers, Multistream & Filters")

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_obs_hud_tab()), "📡 OBS/HUD")
        self.tabs.setTabToolTip(4, "OBS Studio WebSocket & Mini-HUD Telemetry")

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_widgets_tab()), "⚡ Events")
        self.tabs.setTabToolTip(5, "Stream Events Deck & Live Goal Bar")

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_intelligence_tab()), "🧠 AI & GSI")
        self.tabs.setTabToolTip(6, "CS2 Game State Integration, Clutch Silence, Hype Spike & Smart Q&A")

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_profiles_tab()), "🕹️ Profiles")
        self.tabs.setTabToolTip(7, "Per-Game Auto-Switching Profiles")

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_companion_tab()), "📱 Mobile")
        self.tabs.setTabToolTip(8, "Mobile LAN Web Companion & Touch Stream Deck")

        self.tabs.addTab(self._wrap_in_scroll_area(self._create_system_tab()), "⚙️ System")
        self.tabs.setTabToolTip(9, "System Settings & Multi-Monitor Recovery")

        main_layout.addWidget(self.tabs, 1)

        # Footer Buttons
        footer = QHBoxLayout()
        self.save_btn = QPushButton("Save && Close", self)
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
        main_vbox = QVBoxLayout(tab)
        main_vbox.setContentsMargins(10, 10, 10, 10)
        main_vbox.setSpacing(10)

        # 1. Quick Theme Presets Group
        theme_box = QGroupBox("🎨 1-Click Broadcast Theme Presets", tab)
        theme_row = QHBoxLayout(theme_box)
        theme_row.setSpacing(6)

        presets = [
            ("cyberpunk", "Cyberpunk Cyan", "#00e5ff", "#162338"),
            ("stealth", "Obsidian Stealth", "#cbd5e1", "#18181b"),
            ("glass", "Frosted Slate", "#38bdf8", "#1e293b"),
            ("neon", "Neon Sunset", "#ec4899", "#2e1065"),
            ("retro", "Retro Terminal", "#22c55e", "#052e16"),
        ]
        self.theme_buttons = {}
        for key, name, accent, bg in presets:
            btn = QPushButton(name, theme_box)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {bg}; color: {accent}; border: 1.5px solid {accent}; "
                f"border-radius: 4px; padding: 5px 8px; font-weight: 700; font-size: 8.5pt; }} "
                f"QPushButton:hover {{ background-color: {accent}; color: #000000; }}"
            )
            btn.clicked.connect(lambda _, k=key: self._apply_theme_preset(k))
            theme_row.addWidget(btn)
            self.theme_buttons[key] = btn

        main_vbox.addWidget(theme_box)

        # 2. Two-Column Split: Controls (Left) vs Live Preview Sandbox (Right)
        cols = QHBoxLayout()
        cols.setSpacing(10)

        # LEFT: Form Controls
        left_box = QGroupBox("Chat Appearance && Typography", tab)
        form = QFormLayout(left_box)

        # Chat Style
        self.style_combo = QComboBox(tab)
        self.style_combo.addItems([
            "Card (Rounded Boxes)",
            "Bubble Stream (Pills)",
            "Clean Minimalist (Borderless)",
        ])
        style_map = {"card": 0, "bubble": 1, "clean": 2}
        self.style_combo.setCurrentIndex(style_map.get(getattr(self.settings, "chat_style", "card"), 0))
        self.style_combo.currentIndexChanged.connect(self._on_style_changed)
        form.addRow("Chat Style:", self.style_combo)

        # Font Family
        self.font_combo = QComboBox(tab)
        self.font_combo.addItems(["Segoe UI", "Inter", "Roboto", "Consolas", "Arial", "Verdana"])
        curr_font = getattr(self.settings, "font_family", "Segoe UI")
        font_idx = self.font_combo.findText(curr_font)
        if font_idx >= 0:
            self.font_combo.setCurrentIndex(font_idx)
        self.font_combo.currentTextChanged.connect(self._on_font_changed)
        form.addRow("Font Family:", self.font_combo)

        # Streamer Username & Mentions
        self.streamer_name_edit = QLineEdit(tab)
        self.streamer_name_edit.setPlaceholderText("e.g. your_streamer_name")
        self.streamer_name_edit.setText(getattr(self.settings, "streamer_name", ""))
        self.streamer_name_edit.textChanged.connect(self._on_streamer_name_changed)
        form.addRow("Streamer Name:", self.streamer_name_edit)

        self.mentions_cb = QCheckBox("Highlight Mentions in Chat", tab)
        self.mentions_cb.setChecked(getattr(self.settings, "highlight_mentions", True))
        self.mentions_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "highlight_mentions", v),
                self.settings_changed.emit(),
                self._refresh_live_preview(),
            )
        )
        form.addRow(self.mentions_cb)

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
                self._refresh_live_preview(),
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
                self._refresh_live_preview(),
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
            lambda v: (
                setattr(self.settings, "font_size", v),
                self.settings_changed.emit(),
                self._refresh_live_preview(),
            )
        )
        form.addRow("Font Size (pt):", self.font_spin)

        # Message Spacing
        self.spacing_spin = QSpinBox(tab)
        self.spacing_spin.setRange(1, 20)
        self.spacing_spin.setValue(self.settings.message_spacing)
        self.spacing_spin.valueChanged.connect(
            lambda v: (
                setattr(self.settings, "message_spacing", v),
                self.settings_changed.emit(),
                self._refresh_live_preview(),
            )
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

        # Checkbox options
        self.timestamp_cb = QCheckBox("Show Timestamps", tab)
        self.timestamp_cb.setChecked(self.settings.show_timestamps)
        self.timestamp_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "show_timestamps", v),
                self.settings_changed.emit(),
                self._refresh_live_preview(),
            )
        )
        form.addRow(self.timestamp_cb)

        self.username_cb = QCheckBox("Show Usernames", tab)
        self.username_cb.setChecked(self.settings.show_usernames)
        self.username_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "show_usernames", v),
                self.settings_changed.emit(),
                self._refresh_live_preview(),
            )
        )
        form.addRow(self.username_cb)

        self.shadow_cb = QCheckBox("Render Text Shadow", tab)
        self.shadow_cb.setChecked(self.settings.text_shadow)
        self.shadow_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "text_shadow", v),
                self.settings_changed.emit(),
                self._refresh_live_preview(),
            )
        )
        form.addRow(self.shadow_cb)

        self.emotes_cb = QCheckBox("Enable Twitch && 7TV Emotes", tab)
        self.emotes_cb.setChecked(getattr(self.settings, "emotes_enabled", True))
        self.emotes_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "emotes_enabled", v),
                self.settings_changed.emit(),
                self._refresh_live_preview(),
            )
        )
        form.addRow(self.emotes_cb)

        cols.addWidget(left_box, 1)

        # RIGHT: Live Preview Sandbox
        right_box = QGroupBox("👁️ Live In-Game Overlay Preview", tab)
        preview_vbox = QVBoxLayout(right_box)
        preview_vbox.setContentsMargins(10, 10, 10, 10)
        preview_vbox.setSpacing(6)

        # Simulated Game Canvas
        self.game_sim_frame = QFrame(right_box)
        self.game_sim_frame.setStyleSheet(
            "QFrame { background-color: #070a10; border: 1px solid #1e293b; border-radius: 6px; }"
        )
        game_sim_layout = QVBoxLayout(self.game_sim_frame)
        game_sim_layout.setContentsMargins(8, 8, 8, 8)

        # Mini Overlay Container
        self.preview_box = QFrame(self.game_sim_frame)
        self.preview_layout = QVBoxLayout(self.preview_box)
        self.preview_layout.setContentsMargins(6, 6, 6, 6)
        self.preview_layout.setSpacing(self.settings.message_spacing)

        game_sim_layout.addWidget(self.preview_box)
        preview_vbox.addWidget(self.game_sim_frame, 1)

        preview_hint = QLabel("Changes update in real-time. Matches in-game render.", right_box)
        preview_hint.setStyleSheet("color: #64748b; font-size: 8pt; font-style: italic;")
        preview_vbox.addWidget(preview_hint)

        cols.addWidget(right_box, 1)
        main_vbox.addLayout(cols)

        # Populate initial preview
        self._refresh_live_preview()

        return tab

    def _create_chat_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        box = QGroupBox("Active Chat Stream", tab)
        form = QFormLayout(box)
        form.setContentsMargins(12, 14, 12, 12)
        form.setVerticalSpacing(10)

        self.provider_combo = QComboBox(tab)
        self.provider_combo.setMinimumHeight(30)
        self.provider_combo.addItems([
            "Local Demo Simulation",
            "Twitch Live Chat",
            "YouTube Live Chat",
            "Kick Live Chat",
        ])
        current_map = {"demo": 0, "twitch": 1, "youtube": 2, "kick": 3}
        self.provider_combo.setCurrentIndex(current_map.get(self.settings.chat_provider, 0))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_selection_changed)
        form.addRow("Provider:", self.provider_combo)

        # Twitch Channel
        self.twitch_channel_edit = QLineEdit(tab)
        self.twitch_channel_edit.setMinimumHeight(30)
        self.twitch_channel_edit.setPlaceholderText("e.g. shroud or yourchannel")
        self.twitch_channel_edit.setText(self.settings.twitch_channel)
        self.twitch_channel_edit.textChanged.connect(
            lambda t: setattr(self.settings, "twitch_channel", t.strip())
        )
        form.addRow("Twitch Channel:", self.twitch_channel_edit)

        # Kick Channel
        self.kick_channel_edit = QLineEdit(tab)
        self.kick_channel_edit.setMinimumHeight(30)
        self.kick_channel_edit.setPlaceholderText("e.g. xqc or channel slug/ID")
        self.kick_channel_edit.setText(getattr(self.settings, "kick_channel", ""))
        self.kick_channel_edit.textChanged.connect(
            lambda t: setattr(self.settings, "kick_channel", t.strip())
        )
        form.addRow("Kick Channel:", self.kick_channel_edit)

        # YouTube Video ID
        self.yt_id_edit = QLineEdit(tab)
        self.yt_id_edit.setMinimumHeight(30)
        self.yt_id_edit.setPlaceholderText("e.g. jfKfPfyJRdk (Live Stream Video ID)")
        self.yt_id_edit.setText(self.settings.youtube_video_id)
        self.yt_id_edit.textChanged.connect(
            lambda t: setattr(self.settings, "youtube_video_id", t.strip())
        )
        form.addRow("YouTube Video ID:", self.yt_id_edit)

        layout.addWidget(box)

        # Multistream Unified Aggregator
        multi_box = QGroupBox("Multistream Unified Aggregator (Twitch + Kick + YouTube)", tab)
        multi_layout = QVBoxLayout(multi_box)

        self.multi_enable_cb = QCheckBox("Enable Multistream Aggregator (Merge feeds into unified chat)", tab)
        self.multi_enable_cb.setChecked(getattr(self.settings, "multistream_enabled", False))
        self.multi_enable_cb.toggled.connect(
            lambda v: (setattr(self.settings, "multistream_enabled", v), self.settings_changed.emit())
        )
        multi_layout.addWidget(self.multi_enable_cb)

        plats_row = QHBoxLayout()
        self.multi_tw_cb = QCheckBox("Twitch", tab)
        self.multi_tw_cb.setChecked(getattr(self.settings, "multistream_twitch", True))
        self.multi_tw_cb.toggled.connect(
            lambda v: (setattr(self.settings, "multistream_twitch", v), self.settings_changed.emit())
        )
        plats_row.addWidget(self.multi_tw_cb)

        self.multi_kick_cb = QCheckBox("Kick", tab)
        self.multi_kick_cb.setChecked(getattr(self.settings, "multistream_kick", False))
        self.multi_kick_cb.toggled.connect(
            lambda v: (setattr(self.settings, "multistream_kick", v), self.settings_changed.emit())
        )
        plats_row.addWidget(self.multi_kick_cb)

        self.multi_yt_cb = QCheckBox("YouTube", tab)
        self.multi_yt_cb.setChecked(getattr(self.settings, "multistream_youtube", False))
        self.multi_yt_cb.toggled.connect(
            lambda v: (setattr(self.settings, "multistream_youtube", v), self.settings_changed.emit())
        )
        plats_row.addWidget(self.multi_yt_cb)
        multi_layout.addLayout(plats_row)
        layout.addWidget(multi_box)

        # Smart Chat Filters
        filter_box = QGroupBox("Smart Chat Filters && Spam Protection", tab)
        filter_layout = QVBoxLayout(filter_box)

        self.filter_bot_cb = QCheckBox("Filter Bot Commands (!commands, /commands, .commands)", tab)
        self.filter_bot_cb.setChecked(getattr(self.settings, "filter_bot_commands", True))
        self.filter_bot_cb.toggled.connect(
            lambda v: (setattr(self.settings, "filter_bot_commands", v), self.settings_changed.emit())
        )
        filter_layout.addWidget(self.filter_bot_cb)

        dup_row = QHBoxLayout()
        self.filter_dup_cb = QCheckBox("Suppress Rapid Duplicate Spam", tab)
        self.filter_dup_cb.setChecked(getattr(self.settings, "filter_duplicates", True))
        self.filter_dup_cb.toggled.connect(
            lambda v: (setattr(self.settings, "filter_duplicates", v), self.settings_changed.emit())
        )
        dup_row.addWidget(self.filter_dup_cb)

        dup_row.addWidget(QLabel("Window (sec):", tab))
        self.filter_dup_spin = QDoubleSpinBox(tab)
        self.filter_dup_spin.setRange(0.5, 30.0)
        self.filter_dup_spin.setSingleStep(0.5)
        self.filter_dup_spin.setMinimumHeight(28)
        self.filter_dup_spin.setValue(getattr(self.settings, "filter_duplicate_window_sec", 3.0))
        self.filter_dup_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "filter_duplicate_window_sec", float(v)), self.settings_changed.emit())
        )
        dup_row.addWidget(self.filter_dup_spin)
        filter_layout.addLayout(dup_row)
        layout.addWidget(filter_box)

        # Hybrid Auth (Optional)
        auth_box = QGroupBox("Optional Credentials && Hybrid Auth", tab)
        auth_form = QFormLayout(auth_box)
        auth_form.setContentsMargins(12, 14, 12, 12)
        auth_form.setVerticalSpacing(10)

        self.twitch_token_edit = QLineEdit(tab)
        self.twitch_token_edit.setMinimumHeight(30)
        self.twitch_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.twitch_token_edit.setPlaceholderText("Optional oauth:xxxx token (leave empty for zero-setup read-only)")
        self.twitch_token_edit.setText(getattr(self.settings, "twitch_oauth_token", ""))
        self.twitch_token_edit.textChanged.connect(
            lambda t: setattr(self.settings, "twitch_oauth_token", t.strip())
        )
        auth_form.addRow("Twitch OAuth Token:", self.twitch_token_edit)
        layout.addWidget(auth_box)

        # Chat actions
        action_box = QGroupBox("Testing && Actions", tab)
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
            "<b>Multistream:</b> Connects to selected platforms in parallel and tags each message with a platform badge.<br>"
            "<b>Zero-Setup:</b> Anonymous SSL IRC and WebSockets are used by default without developer tokens.",
            tab,
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        layout.addWidget(help_text)

        layout.addStretch()
        return tab

    def _create_obs_hud_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # OBS WebSocket Box
        obs_box = QGroupBox("OBS Studio WebSocket v5 Integration", tab)
        obs_form = QFormLayout(obs_box)

        self.obs_enable_cb = QCheckBox("Enable OBS WebSocket Connection", tab)
        self.obs_enable_cb.setChecked(getattr(self.settings, "obs_enabled", False))
        self.obs_enable_cb.toggled.connect(
            lambda v: (setattr(self.settings, "obs_enabled", v), self.settings_changed.emit())
        )
        obs_form.addRow(self.obs_enable_cb)

        self.obs_host_edit = QLineEdit(tab)
        self.obs_host_edit.setText(getattr(self.settings, "obs_host", "localhost"))
        self.obs_host_edit.setPlaceholderText("localhost")
        self.obs_host_edit.textChanged.connect(
            lambda t: setattr(self.settings, "obs_host", t.strip())
        )
        obs_form.addRow("OBS Host:", self.obs_host_edit)

        self.obs_port_spin = QSpinBox(tab)
        self.obs_port_spin.setRange(1, 65535)
        self.obs_port_spin.setValue(getattr(self.settings, "obs_port", 4455))
        self.obs_port_spin.valueChanged.connect(
            lambda v: setattr(self.settings, "obs_port", v)
        )
        obs_form.addRow("OBS Port:", self.obs_port_spin)

        self.obs_password_edit = QLineEdit(tab)
        self.obs_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.obs_password_edit.setText(getattr(self.settings, "obs_password", ""))
        self.obs_password_edit.setPlaceholderText("Leave blank if no server password configured")
        self.obs_password_edit.textChanged.connect(
            lambda t: setattr(self.settings, "obs_password", t)
        )
        obs_form.addRow("Server Password:", self.obs_password_edit)

        obs_btn_row = QHBoxLayout()
        self.obs_connect_btn = QPushButton("Connect / Test OBS", tab)
        self.obs_connect_btn.clicked.connect(self.obs_connect_requested.emit)
        obs_btn_row.addWidget(self.obs_connect_btn)

        self.obs_status_lbl = QLabel("Status: Disconnected", tab)
        self.obs_status_lbl.setStyleSheet("color: #94a3b8; font-weight: 600;")
        obs_btn_row.addWidget(self.obs_status_lbl)
        obs_btn_row.addStretch()
        obs_form.addRow(obs_btn_row)

        layout.addWidget(obs_box)

        # Standalone Mini-HUD Window Box
        hud_box = QGroupBox("Floating Mini-HUD Window && Notifications", tab)
        hud_form = QFormLayout(hud_box)

        self.hud_enable_cb = QCheckBox("Show Standalone Mini-HUD (Bitrate, Frames, Uptime)", tab)
        self.hud_enable_cb.setChecked(getattr(self.settings, "hud_enabled", True))
        self.hud_enable_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "hud_enabled", v),
                self.hud_toggled.emit(v),
                self.settings_changed.emit(),
            )
        )
        hud_form.addRow(self.hud_enable_cb)

        self.hud_lock_cb = QCheckBox("Lock Mini-HUD (Click-Through Mode)", tab)
        self.hud_lock_cb.setChecked(getattr(self.settings, "hud_locked", False))
        self.hud_lock_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "hud_locked", v),
                self.hud_lock_toggled.emit(v),
                self.settings_changed.emit(),
            )
        )
        hud_form.addRow(self.hud_lock_cb)

        # HUD Layout Mode
        self.hud_layout_combo = QComboBox(tab)
        self.hud_layout_combo.addItems([
            "Horizontal Bar (Standard)",
            "Compact Dock (Minimal)",
        ])
        hud_map = {"horizontal": 0, "compact": 1}
        self.hud_layout_combo.setCurrentIndex(hud_map.get(getattr(self.settings, "hud_layout", "horizontal"), 0))
        self.hud_layout_combo.currentIndexChanged.connect(self._on_hud_layout_changed)
        hud_form.addRow("HUD Layout Mode:", self.hud_layout_combo)

        # In-Game Toast Notifications
        self.toast_enable_cb = QCheckBox("Show In-Game Notification Toasts (Stream Health && Mentions)", tab)
        self.toast_enable_cb.setChecked(getattr(self.settings, "toast_enabled", True))
        self.toast_enable_cb.toggled.connect(
            lambda v: (setattr(self.settings, "toast_enabled", v), self.settings_changed.emit())
        )
        hud_form.addRow(self.toast_enable_cb)

        self.toast_duration_spin = QSpinBox(tab)
        self.toast_duration_spin.setRange(1, 15)
        self.toast_duration_spin.setValue(int(getattr(self.settings, "toast_duration_sec", 4.0)))
        self.toast_duration_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "toast_duration_sec", float(v)), self.settings_changed.emit())
        )
        hud_form.addRow("Toast Duration (sec):", self.toast_duration_spin)

        self.reset_hud_btn = QPushButton("Reset Mini-HUD Position", tab)
        self.reset_hud_btn.clicked.connect(self.reset_hud_position_requested.emit)
        hud_form.addRow(self.reset_hud_btn)

        layout.addWidget(hud_box)

        notice_lbl = QLabel(
            "<b>Note:</b> Like the chat overlay, the Mini-HUD uses Windows Display Affinity "
            "<code>WDA_EXCLUDEFROMCAPTURE</code> and will remain invisible in OBS stream output.",
            tab,
        )
        notice_lbl.setWordWrap(True)
        notice_lbl.setStyleSheet("color: #38bdf8; font-size: 8.5pt;")
        layout.addWidget(notice_lbl)

        layout.addStretch()
        return tab

    def _create_widgets_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # 1. Stream Events Deck Box
        ed_box = QGroupBox("Stream Events Deck (Followers, Subs, Bits, Tips, Goals)", tab)
        ed_form = QFormLayout(ed_box)

        self.ed_enable_cb = QCheckBox("Show Stream Events Deck Bar", tab)
        self.ed_enable_cb.setChecked(getattr(self.settings, "event_deck_enabled", True))
        self.ed_enable_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "event_deck_enabled", v),
                self.event_deck_toggled.emit(v),
                self.settings_changed.emit(),
            )
        )
        ed_form.addRow(self.ed_enable_cb)

        self.ed_lock_cb = QCheckBox("Lock Event Deck (Click-Through Mode)", tab)
        self.ed_lock_cb.setChecked(getattr(self.settings, "event_deck_locked", False))
        self.ed_lock_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "event_deck_locked", v),
                self.event_deck_lock_toggled.emit(v),
                self.settings_changed.emit(),
            )
        )
        ed_form.addRow(self.ed_lock_cb)

        ed_btn_row = QHBoxLayout()
        self.reset_ed_btn = QPushButton("Reset Position", tab)
        self.reset_ed_btn.clicked.connect(self.reset_event_deck_position_requested.emit)
        ed_btn_row.addWidget(self.reset_ed_btn)

        self.sim_event_btn = QPushButton("⚡ Simulate Test Event", tab)
        self.sim_event_btn.clicked.connect(self.simulate_event_requested.emit)
        ed_btn_row.addWidget(self.sim_event_btn)
        ed_btn_row.addStretch()
        ed_form.addRow(ed_btn_row)

        self.se_jwt_edit = QLineEdit(tab)
        self.se_jwt_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.se_jwt_edit.setPlaceholderText("Optional: StreamElements JWT token for real-time live tips")
        self.se_jwt_edit.setText(getattr(self.settings, "streamelements_jwt", ""))
        self.se_jwt_edit.textChanged.connect(
            lambda t: setattr(self.settings, "streamelements_jwt", t.strip())
        )
        ed_form.addRow("StreamElements JWT:", self.se_jwt_edit)

        layout.addWidget(ed_box)
        layout.addStretch()
        return tab

    def _create_intelligence_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # 1. CS2 Game State Integration & Clutch Silence
        gsi_box = QGroupBox("CS2 Game State Integration (GSI) && Clutch Silence Mode", tab)
        gsi_layout = QVBoxLayout(gsi_box)
        gsi_layout.setSpacing(8)

        self.gsi_enable_cb = QCheckBox("Enable Valve CS2 Game State Integration (Zero-Injection Local HTTP)", tab)
        self.gsi_enable_cb.setChecked(getattr(self.settings, "gsi_enabled", False))
        self.gsi_enable_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "gsi_enabled", v),
                self.gsi_toggled.emit(v),
                self.settings_changed.emit(),
            )
        )
        gsi_layout.addWidget(self.gsi_enable_cb)

        gsi_port_row = QHBoxLayout()
        gsi_port_row.addWidget(QLabel("GSI Port:", tab))
        self.gsi_port_spin = QSpinBox(tab)
        self.gsi_port_spin.setRange(1024, 65535)
        self.gsi_port_spin.setValue(getattr(self.settings, "gsi_port", 31337))
        self.gsi_port_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "gsi_port", int(v)), self.settings_changed.emit())
        )
        gsi_port_row.addWidget(self.gsi_port_spin)

        gsi_port_row.addWidget(QLabel("Auth Token:", tab))
        self.gsi_token_edit = QLineEdit(tab)
        self.gsi_token_edit.setPlaceholderText("Optional token (default empty)")
        self.gsi_token_edit.setText(getattr(self.settings, "gsi_auth_token", ""))
        self.gsi_token_edit.textChanged.connect(
            lambda t: (setattr(self.settings, "gsi_auth_token", t.strip()), self.settings_changed.emit())
        )
        gsi_port_row.addWidget(self.gsi_token_edit)
        gsi_layout.addLayout(gsi_port_row)

        # CS2 CFG Installer Controls
        cfg_row = QHBoxLayout()
        self.install_cfg_btn = QPushButton("📁 1-Click Install CS2 CFG", tab)
        self.install_cfg_btn.clicked.connect(self._on_install_cfg_clicked)
        cfg_row.addWidget(self.install_cfg_btn)

        self.uninstall_cfg_btn = QPushButton("Remove CFG", tab)
        self.uninstall_cfg_btn.clicked.connect(self._on_uninstall_cfg_clicked)
        cfg_row.addWidget(self.uninstall_cfg_btn)

        self.cfg_status_lbl = QLabel(tab)
        self.cfg_status_lbl.setStyleSheet("font-size: 8.5pt; font-weight: 600;")
        self._update_cfg_status()
        cfg_row.addWidget(self.cfg_status_lbl)
        cfg_row.addStretch()
        gsi_layout.addLayout(cfg_row)

        # Clutch Silence Sub-section
        clutch_line = QFrame(tab)
        clutch_line.setFrameShape(QFrame.Shape.HLine)
        clutch_line.setStyleSheet("color: #1e293b;")
        gsi_layout.addWidget(clutch_line)

        self.clutch_enable_cb = QCheckBox("Enable Clutch Silence Mode (Dims overlay during high-stakes combat)", tab)
        self.clutch_enable_cb.setChecked(getattr(self.settings, "clutch_mode_enabled", True))
        self.clutch_enable_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "clutch_mode_enabled", v),
                self.clutch_mode_toggled.emit(v),
                self.settings_changed.emit(),
            )
        )
        gsi_layout.addWidget(self.clutch_enable_cb)

        dim_row = QHBoxLayout()
        dim_row.addWidget(QLabel("Clutch Dim Opacity:", tab))
        self.clutch_dim_slider = QSlider(Qt.Orientation.Horizontal, tab)
        self.clutch_dim_slider.setRange(0, 100)
        self.clutch_dim_slider.setValue(int(getattr(self.settings, "clutch_dim_opacity", 0.0) * 100))
        dim_row.addWidget(self.clutch_dim_slider)

        self.clutch_dim_lbl = QLabel(f"{int(getattr(self.settings, 'clutch_dim_opacity', 0.0) * 100)}%", tab)
        self.clutch_dim_lbl.setFixedWidth(40)
        self.clutch_dim_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dim_row.addWidget(self.clutch_dim_lbl)

        self.clutch_dim_slider.valueChanged.connect(self._on_clutch_dim_changed)
        gsi_layout.addLayout(dim_row)

        hp_row = QHBoxLayout()
        hp_row.addWidget(QLabel("Clutch Health Threshold (HP):", tab))
        self.clutch_health_spin = QSpinBox(tab)
        self.clutch_health_spin.setRange(1, 100)
        self.clutch_health_spin.setValue(getattr(self.settings, "clutch_health_threshold", 25))
        self.clutch_health_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "clutch_health_threshold", int(v)), self.settings_changed.emit())
        )
        hp_row.addWidget(self.clutch_health_spin)

        self.sim_clutch_btn = QPushButton("🎮 Simulate Clutch Mode", tab)
        self.sim_clutch_btn.clicked.connect(self.simulate_clutch_requested.emit)
        hp_row.addWidget(self.sim_clutch_btn)
        hp_row.addStretch()
        gsi_layout.addLayout(hp_row)

        layout.addWidget(gsi_box)

        # 2. Hype Spike Analyzer & OBS Auto-Clip Engine
        hype_box = QGroupBox("Hype Spike Analyzer && OBS Auto-Clip Engine", tab)
        hype_layout = QVBoxLayout(hype_box)
        hype_layout.setSpacing(8)

        self.hype_enable_cb = QCheckBox("Enable Hype Spike Analyzer (Real-time chat velocity && reaction emotes)", tab)
        self.hype_enable_cb.setChecked(getattr(self.settings, "hype_detector_enabled", True))
        self.hype_enable_cb.toggled.connect(
            lambda v: (setattr(self.settings, "hype_detector_enabled", v), self.settings_changed.emit())
        )
        hype_layout.addWidget(self.hype_enable_cb)

        hype_params_row = QHBoxLayout()
        hype_params_row.addWidget(QLabel("Sliding Window (sec):", tab))
        self.hype_window_spin = QSpinBox(tab)
        self.hype_window_spin.setRange(3, 120)
        self.hype_window_spin.setValue(getattr(self.settings, "hype_window_seconds", 15))
        self.hype_window_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "hype_window_seconds", int(v)), self.settings_changed.emit())
        )
        hype_params_row.addWidget(self.hype_window_spin)

        hype_params_row.addWidget(QLabel("Trigger Threshold (msgs/sec):", tab))
        self.hype_threshold_spin = QDoubleSpinBox(tab)
        self.hype_threshold_spin.setRange(0.5, 100.0)
        self.hype_threshold_spin.setSingleStep(0.5)
        self.hype_threshold_spin.setValue(getattr(self.settings, "hype_threshold_rate", 3.5))
        self.hype_threshold_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "hype_threshold_rate", float(v)), self.settings_changed.emit())
        )
        hype_params_row.addWidget(self.hype_threshold_spin)
        hype_layout.addLayout(hype_params_row)

        clip_row = QHBoxLayout()
        self.hype_autoclip_cb = QCheckBox("Auto-Save OBS Replay Buffer && Stream Marker on Hype Spike", tab)
        self.hype_autoclip_cb.setChecked(getattr(self.settings, "hype_auto_clip", False))
        self.hype_autoclip_cb.toggled.connect(
            lambda v: (setattr(self.settings, "hype_auto_clip", v), self.settings_changed.emit())
        )
        clip_row.addWidget(self.hype_autoclip_cb)

        clip_row.addWidget(QLabel("Cooldown (sec):", tab))
        self.hype_cooldown_spin = QSpinBox(tab)
        self.hype_cooldown_spin.setRange(5, 600)
        self.hype_cooldown_spin.setValue(getattr(self.settings, "hype_cooldown_seconds", 60))
        self.hype_cooldown_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "hype_cooldown_seconds", int(v)), self.settings_changed.emit())
        )
        clip_row.addWidget(self.hype_cooldown_spin)
        hype_layout.addLayout(clip_row)

        sim_hype_row = QHBoxLayout()
        self.sim_hype_btn = QPushButton("🔥 Simulate Hype Spike Alert", tab)
        self.sim_hype_btn.clicked.connect(self.simulate_hype_requested.emit)
        sim_hype_row.addWidget(self.sim_hype_btn)
        sim_hype_row.addStretch()
        hype_layout.addLayout(sim_hype_row)

        layout.addWidget(hype_box)

        # 3. Smart Q&A Question Deck
        qa_box = QGroupBox("Smart Q&&A Question Deck Window", tab)
        qa_layout = QVBoxLayout(qa_box)
        qa_layout.setSpacing(8)

        self.qa_deck_enable_cb = QCheckBox("Show Smart Q&&A Question Deck Window", tab)
        self.qa_deck_enable_cb.setChecked(getattr(self.settings, "qa_deck_enabled", False))
        self.qa_deck_enable_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "qa_deck_enabled", v),
                self.qa_deck_toggled.emit(v),
                self.settings_changed.emit(),
            )
        )
        qa_layout.addWidget(self.qa_deck_enable_cb)

        self.qa_deck_lock_cb = QCheckBox("Lock Q&&A Deck (Click-Through / Passthrough Mode)", tab)
        self.qa_deck_lock_cb.setChecked(getattr(self.settings, "qa_deck_locked", False))
        self.qa_deck_lock_cb.toggled.connect(
            lambda v: (
                setattr(self.settings, "qa_deck_locked", v),
                self.qa_deck_lock_toggled.emit(v),
                self.settings_changed.emit(),
            )
        )
        qa_layout.addWidget(self.qa_deck_lock_cb)

        qa_params_row = QHBoxLayout()
        qa_params_row.addWidget(QLabel("Max Questions Queued:", tab))
        self.qa_max_items_spin = QSpinBox(tab)
        self.qa_max_items_spin.setRange(5, 100)
        self.qa_max_items_spin.setValue(getattr(self.settings, "qa_max_items", 20))
        self.qa_max_items_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "qa_max_items", int(v)), self.settings_changed.emit())
        )
        qa_params_row.addWidget(self.qa_max_items_spin)

        qa_params_row.addWidget(QLabel("Auto-Expire Unanswered (sec):", tab))
        self.qa_auto_expire_spin = QSpinBox(tab)
        self.qa_auto_expire_spin.setRange(30, 3600)
        self.qa_auto_expire_spin.setValue(getattr(self.settings, "qa_auto_expire_seconds", 300))
        self.qa_auto_expire_spin.valueChanged.connect(
            lambda v: (setattr(self.settings, "qa_auto_expire_seconds", int(v)), self.settings_changed.emit())
        )
        qa_params_row.addWidget(self.qa_auto_expire_spin)
        qa_layout.addLayout(qa_params_row)

        qa_btn_row = QHBoxLayout()
        self.reset_qa_deck_btn = QPushButton("Reset Deck Position", tab)
        self.reset_qa_deck_btn.clicked.connect(self.reset_qa_deck_position_requested.emit)
        qa_btn_row.addWidget(self.reset_qa_deck_btn)

        self.clear_qa_deck_btn = QPushButton("Clear All Questions", tab)
        self.clear_qa_deck_btn.clicked.connect(self.clear_qa_deck_requested.emit)
        qa_btn_row.addWidget(self.clear_qa_deck_btn)
        qa_btn_row.addStretch()
        qa_layout.addLayout(qa_btn_row)

        layout.addWidget(qa_box)

        layout.addStretch()
        return tab

    def _on_clutch_dim_changed(self, value: int) -> None:
        opacity = value / 100.0
        self.settings.clutch_dim_opacity = opacity
        if hasattr(self, "clutch_dim_lbl"):
            self.clutch_dim_lbl.setText(f"{value}%")
        self.config_mgr.save()
        self.settings_changed.emit()

    def _update_cfg_status(self, custom_msg: Optional[str] = None, success: Optional[bool] = None) -> None:
        if not hasattr(self, "cfg_status_lbl"):
            return
        if custom_msg is not None:
            color = "#4ade80" if success else "#ef4444"
            self.cfg_status_lbl.setText(f'<span style="color:{color};">{custom_msg}</span>')
            return

        installed = verify_cfg_installed()
        if installed:
            self.cfg_status_lbl.setText('<span style="color:#4ade80;">● Config Installed</span>')
        else:
            self.cfg_status_lbl.setText('<span style="color:#94a3b8;">○ Not Installed</span>')

    def _on_install_cfg_clicked(self) -> None:
        ok, msg = install_cfg(
            port=getattr(self.settings, "gsi_port", 31337),
            auth_token=getattr(self.settings, "gsi_auth_token", ""),
        )
        self._update_cfg_status(custom_msg=msg, success=ok)

    def _on_uninstall_cfg_clicked(self) -> None:
        ok, msg = uninstall_cfg()
        self._update_cfg_status(custom_msg=msg, success=ok)

    def _create_profiles_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        prof_box = QGroupBox("Per-Game Auto-Switching Profiles", tab)
        prof_form = QFormLayout(prof_box)

        self.auto_profile_cb = QCheckBox("Enable Automatic Profile Switching (Detects Active Game)", tab)
        self.auto_profile_cb.setChecked(getattr(self.settings, "auto_profile_enabled", True))
        self.auto_profile_cb.toggled.connect(self._on_auto_profile_toggled)
        prof_form.addRow(self.auto_profile_cb)

        self.profile_combo = QComboBox(tab)
        if self.profile_mgr:
            for p in self.profile_mgr.get_all_profiles():
                self.profile_combo.addItem(p.name)
            idx = self.profile_combo.findText(self.profile_mgr.active_profile_name)
            if idx >= 0:
                self.profile_combo.setCurrentIndex(idx)
        else:
            self.profile_combo.addItems(["Default", "Valorant", "League of Legends", "Counter-Strike 2"])
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        prof_form.addRow("Current Profile:", self.profile_combo)

        self.profile_process_edit = QLineEdit(tab)
        self.profile_process_edit.setPlaceholderText("Executable names separated by commas (e.g. cs2.exe, valorant.exe)")
        if self.profile_mgr:
            curr_prof = self.profile_mgr.get_profile(self.profile_combo.currentText())
            if curr_prof:
                self.profile_process_edit.setText(", ".join(curr_prof.process_names))
        self.profile_process_edit.textChanged.connect(self._on_profile_processes_changed)
        prof_form.addRow("Associated Game Executables:", self.profile_process_edit)

        btn_row = QHBoxLayout()
        self.detect_game_btn = QPushButton("🎯 Detect Foreground Window", tab)
        self.detect_game_btn.clicked.connect(self._on_detect_game_clicked)
        btn_row.addWidget(self.detect_game_btn)

        self.save_profile_btn = QPushButton("💾 Save Current Windows to Profile", tab)
        self.save_profile_btn.setObjectName("PrimaryBtn")
        self.save_profile_btn.clicked.connect(self._on_save_profile_clicked)
        btn_row.addWidget(self.save_profile_btn)
        btn_row.addStretch()
        prof_form.addRow(btn_row)

        self.detected_info_lbl = QLabel("Focus your game and click 'Detect Foreground Window'", tab)
        self.detected_info_lbl.setStyleSheet("color: #38bdf8; font-size: 8.5pt;")
        prof_form.addRow(self.detected_info_lbl)

        layout.addWidget(prof_box)

        guide_lbl = QLabel(
            "<b>How Profiles Work:</b> Each profile remembers individual overlay, HUD, and widget positions "
            "so you never have to re-arrange your screen between different games (e.g. avoiding Valorant radar vs LoL minimap).",
            tab,
        )
        guide_lbl.setWordWrap(True)
        guide_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        layout.addWidget(guide_lbl)

        layout.addStretch()
        return tab

    def _on_auto_profile_toggled(self, checked: bool) -> None:
        self.settings.auto_profile_enabled = checked
        if self.profile_mgr:
            self.profile_mgr.auto_switch_enabled = checked
        self.config_mgr.save()
        self.settings_changed.emit()

    def _on_profile_selected(self, index: int) -> None:
        name = self.profile_combo.currentText()
        if not name:
            return
        self.settings.active_profile = name
        if self.profile_mgr:
            self.profile_mgr.apply_profile(name)
            curr = self.profile_mgr.get_profile(name)
            if curr and hasattr(self, "profile_process_edit"):
                self.profile_process_edit.setText(", ".join(curr.process_names))
        self.profile_applied.emit(name)
        self.config_mgr.save()

    def _on_profile_processes_changed(self, text: str) -> None:
        name = self.profile_combo.currentText()
        if not name or not self.profile_mgr:
            return
        curr = self.profile_mgr.get_profile(name)
        if curr:
            curr.process_names = [p.strip() for p in text.split(",") if p.strip()]
            self.settings.profiles = self.profile_mgr.export_data()
            self.config_mgr.save()

    def _on_detect_game_clicked(self) -> None:
        exe, title = detect_foreground_window()
        if exe:
            self.detected_info_lbl.setText(f"Detected: {exe} ({title})")
            if hasattr(self, "profile_process_edit"):
                curr_text = self.profile_process_edit.text()
                if exe.lower() not in curr_text.lower():
                    new_text = f"{curr_text}, {exe}" if curr_text else exe
                    self.profile_process_edit.setText(new_text)
        else:
            self.detected_info_lbl.setText("No game window detected. Make sure to click outside first.")

    def _on_save_profile_clicked(self) -> None:
        name = self.profile_combo.currentText()
        if name:
            self.save_current_profile_requested.emit(name)
            self.detected_info_lbl.setText(f"Saved current window positions to '{name}' profile!")

    def _create_companion_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Overview & Control Box
        box = QGroupBox("Mobile LAN Web Companion && Touch Stream Deck", tab)
        form = QFormLayout(box)

        desc_lbl = QLabel(
            "Turn any smartphone, tablet, or secondary PC on your local Wi-Fi into an interactive touch Stream Deck, "
            "live chat monitor, and telemetry dashboard without installing any app!",
            tab,
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #e2e8f0; font-size: 9pt;")
        form.addRow(desc_lbl)

        self.companion_enable_cb = QCheckBox("Enable Mobile Web Companion Server", tab)
        self.companion_enable_cb.setChecked(getattr(self.settings, "web_companion_enabled", True))
        self.companion_enable_cb.toggled.connect(self._on_companion_enabled_toggled)
        form.addRow(self.companion_enable_cb)

        self.companion_port_spin = QSpinBox(tab)
        self.companion_port_spin.setRange(1024, 65535)
        self.companion_port_spin.setValue(getattr(self.settings, "web_companion_port", 8989))
        self.companion_port_spin.valueChanged.connect(self._on_companion_port_changed)
        form.addRow("Server Port:", self.companion_port_spin)

        pin_row = QHBoxLayout()
        self.companion_pin_edit = QLineEdit(tab)
        self.companion_pin_edit.setMaxLength(6)
        self.companion_pin_edit.setText(getattr(self.settings, "web_companion_pin", "7749"))
        self.companion_pin_edit.textChanged.connect(self._on_companion_pin_changed)
        pin_row.addWidget(self.companion_pin_edit)

        self.regen_pin_btn = QPushButton("🎲 Generate PIN", tab)
        self.regen_pin_btn.clicked.connect(self._on_regenerate_pin)
        pin_row.addWidget(self.regen_pin_btn)
        form.addRow("Pairing PIN:", pin_row)

        lan_ip = get_local_lan_ip()
        self.companion_url = f"http://{lan_ip}:{self.settings.web_companion_port}"

        self.url_lbl = QLabel(f'<a href="{self.companion_url}" style="color: #00e5ff; font-weight: 700; font-size: 10.5pt;">{self.companion_url}</a>', tab)
        self.url_lbl.setOpenExternalLinks(True)
        form.addRow("Mobile Browser URL:", self.url_lbl)

        url_btns = QHBoxLayout()
        self.copy_url_btn = QPushButton("📋 Copy URL", tab)
        self.copy_url_btn.clicked.connect(self._on_copy_companion_url)
        url_btns.addWidget(self.copy_url_btn)

        self.open_browser_btn = QPushButton("🌐 Open in Browser", tab)
        self.open_browser_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.companion_url)))
        url_btns.addWidget(self.open_browser_btn)
        form.addRow(url_btns)

        layout.addWidget(box)

        # Visual QR Code Display
        qr_box = QGroupBox("Instant Phone Camera Pairing (Point Camera to Connect)", tab)
        qr_layout = QVBoxLayout(qr_box)

        qr_center = QHBoxLayout()
        qr_center.addStretch()
        self.qr_widget = QSvgWidget(qr_box)
        self.qr_widget.setFixedSize(190, 190)
        self._refresh_qr_code()
        qr_center.addWidget(self.qr_widget)
        qr_center.addStretch()
        qr_layout.addLayout(qr_center)

        scan_hint = QLabel("Scan with your phone camera while connected to the same Wi-Fi.", qr_box)
        scan_hint.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        scan_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_layout.addWidget(scan_hint)

        layout.addWidget(qr_box)
        layout.addStretch()
        return tab

    def _refresh_qr_code(self) -> None:
        if hasattr(self, "qr_widget"):
            lan_ip = get_local_lan_ip()
            port = getattr(self.settings, "web_companion_port", 8989)
            url = f"http://{lan_ip}:{port}"
            svg = generate_qr_svg(url)
            self.qr_widget.load(QByteArray(svg.encode("utf-8")))

    def _on_companion_enabled_toggled(self, checked: bool) -> None:
        self.settings.web_companion_enabled = checked
        self.config_mgr.save()
        self.companion_restart_requested.emit()

    def _on_companion_port_changed(self, port: int) -> None:
        self.settings.web_companion_port = port
        lan_ip = get_local_lan_ip()
        self.companion_url = f"http://{lan_ip}:{port}"
        if hasattr(self, "url_lbl"):
            self.url_lbl.setText(f'<a href="{self.companion_url}" style="color: #00e5ff; font-weight: 700; font-size: 10.5pt;">{self.companion_url}</a>')
        self._refresh_qr_code()
        self.config_mgr.save()
        self.companion_restart_requested.emit()

    def _on_companion_pin_changed(self, pin: str) -> None:
        self.settings.web_companion_pin = pin.strip()
        self.config_mgr.save()

    def _on_regenerate_pin(self) -> None:
        import random
        new_pin = f"{random.randint(1000, 9999)}"
        self.settings.web_companion_pin = new_pin
        if hasattr(self, "companion_pin_edit"):
            self.companion_pin_edit.setText(new_pin)
        self.config_mgr.save()

    def _on_copy_companion_url(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(self.companion_url)
            if hasattr(self, "copy_url_btn"):
                self.copy_url_btn.setText("✓ Copied!")
                QTimer.singleShot(2000, lambda: self.copy_url_btn.setText("📋 Copy URL"))

    def _create_system_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Windows Startup Box
        startup_box = QGroupBox("Windows Startup && Automation", tab)
        startup_layout = QVBoxLayout(startup_box)

        self.startup_cb = QCheckBox("Start Kronos Veil Automatically on Windows Boot", tab)
        self.startup_cb.setEnabled(is_autostart_supported())
        self.startup_cb.setChecked(is_autostart_enabled())
        self.startup_cb.toggled.connect(self._on_autostart_toggled)
        startup_layout.addWidget(self.startup_cb)

        startup_hint = QLabel("Registers in HKCU Run registry key. Runs silently in tray on user login.", tab)
        startup_hint.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        startup_layout.addWidget(startup_hint)
        layout.addWidget(startup_box)

        recovery_box = QGroupBox("Multi-Monitor && Window Recovery", tab)
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

    def _on_autostart_toggled(self, checked: bool) -> None:
        set_autostart(checked)
        self.settings.launch_on_startup = checked
        self.config_mgr.save()

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

        if hasattr(self, "overlay_opacity_slider"):
            self.overlay_opacity_slider.setValue(int(self.settings.overlay_opacity * 100))
        if hasattr(self, "bg_opacity_slider"):
            self.bg_opacity_slider.setValue(int(self.settings.background_opacity * 100))
        if hasattr(self, "font_spin"):
            self.font_spin.setValue(self.settings.font_size)
        if hasattr(self, "spacing_spin"):
            self.spacing_spin.setValue(self.settings.message_spacing)
        if hasattr(self, "max_msg_spin"):
            self.max_msg_spin.setValue(self.settings.max_messages)
        if hasattr(self, "lifetime_spin"):
            self.lifetime_spin.setValue(self.settings.message_lifetime_sec)
        if hasattr(self, "timestamp_cb"):
            self.timestamp_cb.setChecked(self.settings.show_timestamps)
        if hasattr(self, "username_cb"):
            self.username_cb.setChecked(self.settings.show_usernames)
        if hasattr(self, "shadow_cb"):
            self.shadow_cb.setChecked(self.settings.text_shadow)
        if hasattr(self, "emotes_cb"):
            self.emotes_cb.setChecked(getattr(self.settings, "emotes_enabled", True))

        if hasattr(self, "style_combo"):
            style_map = {"card": 0, "bubble": 1, "clean": 2}
            self.style_combo.setCurrentIndex(style_map.get(getattr(self.settings, "chat_style", "card"), 0))
        if hasattr(self, "font_combo"):
            f_idx = self.font_combo.findText(getattr(self.settings, "font_family", "Segoe UI"))
            if f_idx >= 0:
                self.font_combo.setCurrentIndex(f_idx)
        if hasattr(self, "streamer_name_edit"):
            self.streamer_name_edit.setText(getattr(self.settings, "streamer_name", ""))
        if hasattr(self, "mentions_cb"):
            self.mentions_cb.setChecked(getattr(self.settings, "highlight_mentions", True))

        if hasattr(self, "hud_layout_combo"):
            h_map = {"horizontal": 0, "compact": 1}
            self.hud_layout_combo.setCurrentIndex(h_map.get(getattr(self.settings, "hud_layout", "horizontal"), 0))
        if hasattr(self, "toast_enable_cb"):
            self.toast_enable_cb.setChecked(getattr(self.settings, "toast_enabled", True))
        if hasattr(self, "toast_duration_spin"):
            self.toast_duration_spin.setValue(int(getattr(self.settings, "toast_duration_sec", 4.0)))

        if hasattr(self, "obs_enable_cb"):
            self.obs_enable_cb.setChecked(getattr(self.settings, "obs_enabled", False))
        if hasattr(self, "hud_enable_cb"):
            self.hud_enable_cb.setChecked(getattr(self.settings, "hud_enabled", True))
        if hasattr(self, "hud_lock_cb"):
            self.hud_lock_cb.setChecked(getattr(self.settings, "hud_locked", False))

        if hasattr(self, "ed_enable_cb"):
            self.ed_enable_cb.setChecked(getattr(self.settings, "event_deck_enabled", True))
        if hasattr(self, "ed_lock_cb"):
            self.ed_lock_cb.setChecked(getattr(self.settings, "event_deck_locked", False))
        if hasattr(self, "auto_profile_cb"):
            self.auto_profile_cb.setChecked(getattr(self.settings, "auto_profile_enabled", True))

        if hasattr(self, "multi_enable_cb"):
            self.multi_enable_cb.setChecked(getattr(self.settings, "multistream_enabled", False))
        if hasattr(self, "multi_tw_cb"):
            self.multi_tw_cb.setChecked(getattr(self.settings, "multistream_twitch", True))
        if hasattr(self, "multi_kick_cb"):
            self.multi_kick_cb.setChecked(getattr(self.settings, "multistream_kick", False))
        if hasattr(self, "multi_yt_cb"):
            self.multi_yt_cb.setChecked(getattr(self.settings, "multistream_youtube", False))
        if hasattr(self, "filter_bot_cb"):
            self.filter_bot_cb.setChecked(getattr(self.settings, "filter_bot_commands", True))
        if hasattr(self, "filter_dup_cb"):
            self.filter_dup_cb.setChecked(getattr(self.settings, "filter_duplicates", True))
        if hasattr(self, "filter_dup_spin"):
            self.filter_dup_spin.setValue(getattr(self.settings, "filter_duplicate_window_sec", 3.0))
        if hasattr(self, "twitch_token_edit"):
            self.twitch_token_edit.setText(getattr(self.settings, "twitch_oauth_token", ""))
        if hasattr(self, "companion_enable_cb"):
            self.companion_enable_cb.setChecked(getattr(self.settings, "web_companion_enabled", True))
        if hasattr(self, "companion_port_spin"):
            self.companion_port_spin.setValue(getattr(self.settings, "web_companion_port", 8989))
        if hasattr(self, "companion_pin_edit"):
            self.companion_pin_edit.setText(getattr(self.settings, "web_companion_pin", "7749"))
        if hasattr(self, "startup_cb"):
            self.startup_cb.setChecked(is_autostart_enabled())

        # Game & AI Intelligence controls
        if hasattr(self, "gsi_enable_cb"):
            self.gsi_enable_cb.setChecked(getattr(self.settings, "gsi_enabled", False))
        if hasattr(self, "gsi_port_spin"):
            self.gsi_port_spin.setValue(getattr(self.settings, "gsi_port", 31337))
        if hasattr(self, "gsi_token_edit"):
            self.gsi_token_edit.setText(getattr(self.settings, "gsi_auth_token", ""))
        if hasattr(self, "clutch_enable_cb"):
            self.clutch_enable_cb.setChecked(getattr(self.settings, "clutch_mode_enabled", True))
        if hasattr(self, "clutch_dim_slider"):
            dim_val = int(getattr(self.settings, "clutch_dim_opacity", 0.0) * 100)
            self.clutch_dim_slider.setValue(dim_val)
            if hasattr(self, "clutch_dim_lbl"):
                self.clutch_dim_lbl.setText(f"{dim_val}%")
        if hasattr(self, "clutch_health_spin"):
            self.clutch_health_spin.setValue(getattr(self.settings, "clutch_health_threshold", 25))
        if hasattr(self, "hype_enable_cb"):
            self.hype_enable_cb.setChecked(getattr(self.settings, "hype_detector_enabled", True))
        if hasattr(self, "hype_window_spin"):
            self.hype_window_spin.setValue(getattr(self.settings, "hype_window_seconds", 15))
        if hasattr(self, "hype_threshold_spin"):
            self.hype_threshold_spin.setValue(getattr(self.settings, "hype_threshold_rate", 3.5))
        if hasattr(self, "hype_autoclip_cb"):
            self.hype_autoclip_cb.setChecked(getattr(self.settings, "hype_auto_clip", False))
        if hasattr(self, "hype_cooldown_spin"):
            self.hype_cooldown_spin.setValue(getattr(self.settings, "hype_cooldown_seconds", 60))
        if hasattr(self, "qa_deck_enable_cb"):
            self.qa_deck_enable_cb.setChecked(getattr(self.settings, "qa_deck_enabled", False))
        if hasattr(self, "qa_deck_lock_cb"):
            self.qa_deck_lock_cb.setChecked(getattr(self.settings, "qa_deck_locked", False))
        if hasattr(self, "qa_max_items_spin"):
            self.qa_max_items_spin.setValue(getattr(self.settings, "qa_max_items", 20))
        if hasattr(self, "qa_auto_expire_spin"):
            self.qa_auto_expire_spin.setValue(getattr(self.settings, "qa_auto_expire_seconds", 300))
        if hasattr(self, "cfg_status_lbl"):
            self._update_cfg_status()

        self._update_status_badge()
        self.status_detail_lbl.setText(self.capture_mgr.last_error_message)
        self._refresh_live_preview()

    def _apply_theme_preset(self, preset_key: str) -> None:
        """Applies a curated theme preset and updates active UI elements."""
        self.settings.theme_preset = preset_key
        theme = get_theme(preset_key)
        self.settings.accent_color = theme.accent_color
        if preset_key == "retro":
            self.settings.font_family = "Consolas"
        else:
            self.settings.font_family = "Segoe UI"

        if hasattr(self, "font_combo"):
            idx = self.font_combo.findText(self.settings.font_family)
            if idx >= 0:
                self.font_combo.setCurrentIndex(idx)

        self.config_mgr.save()
        self.settings_changed.emit()
        self._refresh_live_preview()

    def _on_style_changed(self, index: int) -> None:
        keys = ["card", "bubble", "clean"]
        if 0 <= index < len(keys):
            self.settings.chat_style = keys[index]
            self.config_mgr.save()
            self.settings_changed.emit()
            self._refresh_live_preview()

    def _on_font_changed(self, font_name: str) -> None:
        if font_name:
            self.settings.font_family = font_name
            self.config_mgr.save()
            self.settings_changed.emit()
            self._refresh_live_preview()

    def _on_streamer_name_changed(self, text: str) -> None:
        self.settings.streamer_name = text.strip()
        self.config_mgr.save()
        self.settings_changed.emit()
        self._refresh_live_preview()

    def _on_hud_layout_changed(self, index: int) -> None:
        keys = ["horizontal", "compact"]
        if 0 <= index < len(keys):
            self.settings.hud_layout = keys[index]
            self.config_mgr.save()
            self.settings_changed.emit()

    def _refresh_live_preview(self) -> None:
        """Dynamically re-renders the mini overlay sandbox with sample messages."""
        if not hasattr(self, "preview_layout"):
            return

        # Clear existing preview items
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        theme = get_theme(getattr(self.settings, "theme_preset", "cyberpunk"))
        bg_alpha = int(self.settings.background_opacity * 255)
        bg_color = theme.background_color.replace("{alpha}", str(bg_alpha))
        border_css = f"border: 1px solid {theme.border_color};"

        self.preview_box.setStyleSheet(
            f"QFrame {{ "
            f"background-color: {bg_color}; "
            f"{border_css} "
            f"border-radius: 6px; "
            f"}}"
        )
        self.preview_layout.setSpacing(self.settings.message_spacing)

        # 3 realistic sample messages for the live preview
        streamer_mention = f"@{self.settings.streamer_name}" if self.settings.streamer_name else "@Streamer"
        sample_msgs = [
            ChatMessage(
                username="KronosVeil",
                message="Stream session started! Welcome everyone Pog",
                color=theme.accent_color,
                badges=["broadcaster"],
                is_system=True,
            ),
            ChatMessage(
                username="ShadowNinja",
                message=f"{streamer_mention} clutch 1v4 round! monkaS",
                color="#f43f5e",
                badges=["vip"],
            ),
            ChatMessage(
                username="PixelKnight",
                message="chat overlay is looking clean and private KEKW",
                color="#38bdf8",
                badges=["subscriber"],
            ),
        ]

        for m in sample_msgs:
            widget = ChatMessageWidget(m, self.settings, self.preview_box)
            self.preview_layout.addWidget(widget)

    def update_obs_status(self, connected: bool, message: str) -> None:
        """Displays connection status in the OBS settings tab."""
        if hasattr(self, "obs_status_lbl"):
            color = "#4ade80" if connected else "#ef4444"
            self.obs_status_lbl.setText(f"Status: {message}")
            self.obs_status_lbl.setStyleSheet(f"color: {color}; font-weight: 600;")

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
        keys = ["demo", "twitch", "youtube", "kick"]
        if 0 <= index < len(keys):
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
