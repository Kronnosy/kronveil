"""
Transparent always-on-top chat overlay for Kronos Veil.
Implements Edit Mode (draggable/resizable with controls) and Locked Mode (minimal HUD with click-through),
message expiry/fading animations, capture test mode, and responsive layout.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from kronos_veil.chat.base import ChatMessage
from kronos_veil.chat.emotes import EmoteManager
from kronos_veil.chat.filters import ChatFilterEngine
from kronos_veil.config import AppSettings, ConfigManager
from kronos_veil.themes import THEME_PRESETS, get_theme
from kronos_veil.windows.capture_protection import (
    CaptureProtectionManager,
    CaptureProtectionStatus,
)
from kronos_veil.windows.window_styles import WindowStyleManager

logger = logging.getLogger(__name__)


class ChatMessageWidget(QFrame):
    """Visual widget representing a single livestream chat message row."""

    expired = Signal(QWidget)

    def __init__(
        self,
        msg: ChatMessage,
        settings: AppSettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.msg = msg
        self.settings = settings
        self.created_at = time.time()
        self._is_fading = False
        self._fade_anim: Optional[QPropertyAnimation] = None
        self._in_anim: Optional[QPropertyAnimation] = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        # Detect mention
        streamer = getattr(settings, "streamer_name", "").strip().lower()
        highlight_mentions = getattr(settings, "highlight_mentions", True)
        self.is_mentioned: bool = bool(
            streamer
            and highlight_mentions
            and (f"@{streamer}" in msg.message.lower() or streamer in msg.message.lower())
        )

        font_fam = getattr(settings, "font_family", "Segoe UI")
        theme = get_theme(getattr(settings, "theme_preset", "cyberpunk"))
        self._apply_frame_style(theme)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Optional Timestamp
        if settings.show_timestamps:
            self.time_label = QLabel(msg.timestamp, self)
            self.time_label.setStyleSheet(
                f"color: {theme.text_secondary}; font-size: {max(9, settings.font_size - 3)}pt; "
                f"font-family: '{font_fam}', sans-serif;"
            )
            self.time_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            layout.addWidget(self.time_label)

        # Optional Username & Badges
        if settings.show_usernames:
            emote_mgr = EmoteManager.get_instance()
            badges_html = emote_mgr.format_badges_html(msg.badges)

            platform_badge = ""
            plat = getattr(msg, "platform", "").lower()
            if plat and plat != "demo":
                if plat == "twitch":
                    platform_badge = '<span style="background-color: #9146FF; color: #ffffff; font-size: 7.5pt; font-weight: 800; padding: 1px 3px; border-radius: 2px; margin-right: 4px;">TW</span> '
                elif plat == "kick":
                    platform_badge = '<span style="background-color: #53FC18; color: #000000; font-size: 7.5pt; font-weight: 800; padding: 1px 3px; border-radius: 2px; margin-right: 4px;">KICK</span> '
                elif plat == "youtube":
                    platform_badge = '<span style="background-color: #FF0000; color: #ffffff; font-size: 7.5pt; font-weight: 800; padding: 1px 3px; border-radius: 2px; margin-right: 4px;">YT</span> '

            user_color = msg.color if msg.color else theme.accent_color
            self.user_label = QLabel(self)
            full_prefix = f"{platform_badge}{badges_html}"
            if full_prefix:
                self.user_label.setTextFormat(Qt.TextFormat.RichText)
                self.user_label.setText(
                    f'{full_prefix}<span style="color: {user_color}; font-weight: 700; '
                    f'font-size: {settings.font_size}pt; font-family: \'{font_fam}\', sans-serif;">{msg.username}:</span>'
                )
            else:
                self.user_label.setText(f"{msg.username}:")
                self.user_label.setStyleSheet(
                    f"color: {user_color}; font-weight: 700; font-size: {settings.font_size}pt; font-family: '{font_fam}', sans-serif;"
                )
            self.user_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            layout.addWidget(self.user_label)

        # Message Text with Emote Rendering
        self.text_label = QLabel(self)
        self.text_label.setWordWrap(True)
        text_color = theme.text_primary if not msg.is_system else "#ffcc00"
        self.text_label.setStyleSheet(
            f"color: {text_color}; font-size: {settings.font_size}pt; font-family: '{font_fam}', sans-serif;"
        )

        emotes_enabled = getattr(settings, "emotes_enabled", True)
        if emotes_enabled:
            self.text_label.setTextFormat(Qt.TextFormat.RichText)
            emote_size = int(settings.font_size * 1.6)
            formatted_html = EmoteManager.get_instance().format_message_html(
                msg.message, emotes_enabled=True, size_px=emote_size
            )
            self.text_label.setText(formatted_html)
        else:
            self.text_label.setText(msg.message)

        self.text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        if settings.text_shadow:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(3)
            shadow.setColor(QColor(0, 0, 0, 220))
            shadow.setOffset(1, 1)
            self.text_label.setGraphicsEffect(shadow)

        layout.addWidget(self.text_label)

        self.opacity_effect: Optional[QGraphicsOpacityEffect] = None
        self._trigger_entry_animation()

    def _apply_frame_style(self, theme) -> None:
        """Applies styles for Card, Bubble, or Clean display modes."""
        style = getattr(self.settings, "chat_style", "card")
        radius = getattr(self.settings, "card_radius", 6)

        if style == "card":
            border = f"1px solid {theme.mention_border}" if self.is_mentioned else f"1px solid {theme.card_border}"
            bg = "rgba(255, 0, 127, 0.22)" if self.is_mentioned else theme.card_background
            self.setStyleSheet(
                f"QFrame {{ background-color: {bg}; border: {border}; border-radius: {radius}px; "
                f"margin: 1px 0px; padding: 2px 6px; }}"
            )
        elif style == "bubble":
            bubble_rad = max(10, radius * 2)
            border = f"2px solid {theme.mention_border}" if self.is_mentioned else f"1px solid {theme.card_border}"
            bg = "rgba(255, 0, 127, 0.25)" if self.is_mentioned else theme.card_background
            self.setStyleSheet(
                f"QFrame {{ background-color: {bg}; border: {border}; border-radius: {bubble_rad}px; "
                f"margin: 2px 4px; padding: 4px 8px; }}"
            )
        else:  # "clean"
            if self.is_mentioned:
                self.setStyleSheet(
                    f"QFrame {{ background-color: rgba(255, 0, 127, 0.18); "
                    f"border-left: 3px solid {theme.mention_border}; border-radius: 2px; margin: 1px 0; padding: 2px 4px; }}"
                )
            else:
                self.setStyleSheet("QFrame { background: transparent; border: none; margin: 0; padding: 1px 2px; }")

    def _trigger_entry_animation(self) -> None:
        """Plays a subtle, lightweight fade-in entrance animation."""
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self._in_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self._in_anim.setDuration(160)
        self._in_anim.setStartValue(0.1)
        self._in_anim.setEndValue(1.0)
        self._in_anim.finished.connect(self._on_enter_finished)
        self._in_anim.start()

    def _on_enter_finished(self) -> None:
        # Detach top-level opacity effect after entrance so child drop shadows remain crisp
        if not self._is_fading:
            self.setGraphicsEffect(None)
            self.opacity_effect = None

    def start_fade_out(self, duration_sec: float) -> None:
        """Gradually fades out the message before removing it."""
        if self._is_fading:
            return
        self._is_fading = True
        if self.settings.text_shadow:
            self.text_label.setGraphicsEffect(None)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self._fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self._fade_anim.setDuration(int(duration_sec * 1000))
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(lambda: self.expired.emit(self))
        self._fade_anim.start()


class OverlayWindow(QWidget):
    """
    Main transparent always-on-top chat overlay window.
    Supports Edit Mode and Locked Mode with Win32 click-through and capture exclusion.
    """

    open_settings_requested = Signal()
    mode_changed = Signal(bool)  # True = locked, False = edit
    mention_detected = Signal(str, str)  # username, message
    settings_changed = Signal()

    def __init__(
        self,
        config_mgr: ConfigManager,
        capture_mgr: CaptureProtectionManager,
        style_mgr: WindowStyleManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_mgr = config_mgr
        self.settings = config_mgr.settings
        self.capture_mgr = capture_mgr
        self.style_mgr = style_mgr

        self._is_locked: bool = self.settings.locked
        self._is_click_through: bool = self.settings.click_through
        self._capture_test_mode: bool = False
        self._clutch_anim: Optional[QPropertyAnimation] = None
        self._is_clutch_dimmed: bool = False

        # Dragging and Resizing State for Edit Mode
        self._is_dragging: bool = False
        self._drag_position: QPoint = QPoint()
        self._is_resizing: bool = False
        self._resize_origin: QPoint = QPoint()
        self._resize_orig_geo: QRect = QRect()

        self._messages: List[ChatMessageWidget] = []
        self.filter_engine = ChatFilterEngine(
            getattr(self.settings, "filter_duplicate_window_sec", 3.0)
        )

        # Periodic check for expiring messages
        self._expiry_timer = QTimer(self)
        self._expiry_timer.setInterval(500)
        self._expiry_timer.timeout.connect(self._check_message_expirations)
        self._expiry_timer.start()

        self._init_ui()
        self._apply_window_flags()

    def _init_ui(self) -> None:
        """Builds the internal UI components for the overlay."""
        self.setObjectName("KronosVeilOverlay")
        self.setGeometry(
            self.settings.overlay_x,
            self.settings.overlay_y,
            self.settings.overlay_width,
            self.settings.overlay_height,
        )
        self.setMinimumSize(220, 150)

        # Root Layout
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # Container Frame
        self.container_frame = QFrame(self)
        self.container_frame.setObjectName("ContainerFrame")
        self.root_layout.addWidget(self.container_frame)

        self.container_layout = QVBoxLayout(self.container_frame)
        self.container_layout.setContentsMargins(6, 6, 6, 6)
        self.container_layout.setSpacing(4)

        # 1. Edit Mode Header Bar (Draggable strip & control buttons)
        self.header_bar = QWidget(self.container_frame)
        self.header_bar.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(4, 2, 4, 2)
        header_layout.setSpacing(6)

        self.title_label = QLabel("✦ KRONOS VEIL", self.header_bar)
        self.title_label.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 9.5pt;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        # Quick Theme Cycle Button
        self.theme_cycle_btn = QPushButton(self.header_bar)
        self.theme_cycle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_cycle_btn.setToolTip("Click to cycle theme preset (Cyberpunk, Stealth, Glass, Neon, Retro)")
        self.theme_cycle_btn.setStyleSheet(
            "QPushButton { background: #161f2e; color: #38bdf8; border: 1px solid #334155; "
            "border-radius: 3px; padding: 2px 7px; font-size: 8.5pt; font-weight: 600; } "
            "QPushButton:hover { background: #1e293b; border-color: #38bdf8; }"
        )
        self.theme_cycle_btn.clicked.connect(self._cycle_theme)
        header_layout.addWidget(self.theme_cycle_btn)

        # Quick Style Cycle Button
        self.style_cycle_btn = QPushButton(self.header_bar)
        self.style_cycle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.style_cycle_btn.setToolTip("Click to cycle message format (Card, Bubble, Clean)")
        self.style_cycle_btn.setStyleSheet(
            "QPushButton { background: #161f2e; color: #a5b4fc; border: 1px solid #334155; "
            "border-radius: 3px; padding: 2px 7px; font-size: 8.5pt; font-weight: 600; } "
            "QPushButton:hover { background: #1e293b; border-color: #a5b4fc; }"
        )
        self.style_cycle_btn.clicked.connect(self._cycle_style)
        header_layout.addWidget(self.style_cycle_btn)

        # Lock button
        self.lock_btn = QPushButton("🔒 Lock (Ctrl+Shift+F10)", self.header_bar)
        self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lock_btn.setToolTip("Lock overlay position and hide edit controls")
        self.lock_btn.setStyleSheet(
            "QPushButton { background: #1a2332; color: #38bdf8; border: 1px solid #0284c7; "
            "border-radius: 3px; padding: 2px 8px; font-size: 9pt; } "
            "QPushButton:hover { background: #0284c7; color: #ffffff; }"
        )
        self.lock_btn.clicked.connect(lambda: self.set_locked(True))
        header_layout.addWidget(self.lock_btn)

        # Settings button
        self.settings_btn = QPushButton("⚙", self.header_bar)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setToolTip("Open Kronos Veil Settings")
        self.settings_btn.setStyleSheet(
            "QPushButton { background: #1e293b; color: #cbd5e1; border: 1px solid #475569; "
            "border-radius: 3px; padding: 2px 6px; font-size: 9pt; } "
            "QPushButton:hover { background: #334155; color: #ffffff; }"
        )
        self.settings_btn.clicked.connect(self.open_settings_requested.emit)
        header_layout.addWidget(self.settings_btn)

        self.container_layout.addWidget(self.header_bar)

        # 2. Capture Test Banner (Hidden by default, shown during test mode)
        self.test_banner = QFrame(self.container_frame)
        self.test_banner.setObjectName("TestBanner")
        test_layout = QVBoxLayout(self.test_banner)
        test_layout.setContentsMargins(8, 6, 8, 6)
        test_layout.setSpacing(2)

        test_title = QLabel("🛡️ KRONOS VEIL — PRIVATE OVERLAY TEST", self.test_banner)
        test_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        test_title.setStyleSheet("color: #000000; font-weight: 900; font-size: 11pt; letter-spacing: 1px;")

        test_desc = QLabel(
            "LOOK AT YOUR OBS PREVIEW NOW:\n"
            "• If this box is INVISIBLE in OBS: Capture Protection is WORKING!\n"
            "• If this box is VISIBLE in OBS: Switch OBS to Game Capture or Window Capture.",
            self.test_banner,
        )
        test_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        test_desc.setStyleSheet("color: #111827; font-size: 8.5pt; font-weight: 600;")

        test_layout.addWidget(test_title)
        test_layout.addWidget(test_desc)
        self.test_banner.setStyleSheet(
            "QFrame#TestBanner { background-color: #ffd600; border: 2px solid #ffab00; border-radius: 4px; }"
        )
        self.test_banner.setVisible(False)
        self.container_layout.addWidget(self.test_banner)

        # 3. First-Launch Hint (Shown only when first_launch is True and in Edit Mode)
        self.hint_banner = QFrame(self.container_frame)
        hint_layout = QHBoxLayout(self.hint_banner)
        hint_layout.setContentsMargins(6, 4, 6, 4)
        hint_lbl = QLabel(
            "💡 Move/resize chat to your preferred location, then press Ctrl+Shift+F10 to lock it.",
            self.hint_banner,
        )
        hint_lbl.setStyleSheet("color: #94a3b8; font-size: 8.5pt; font-style: italic;")
        hint_layout.addWidget(hint_lbl)
        self.hint_banner.setStyleSheet(
            "background: rgba(15, 23, 42, 0.7); border: 1px dashed #334155; border-radius: 3px;"
        )
        self.hint_banner.setVisible(self.settings.first_launch and not self._is_locked)
        self.container_layout.addWidget(self.hint_banner)

        # 4. Message Scroll / Display Area
        self.scroll_area = QScrollArea(self.container_frame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.messages_container = QWidget()
        self.messages_container.setStyleSheet("background: transparent;")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(2, 2, 2, 2)
        self.messages_layout.setSpacing(self.settings.message_spacing)

        # Top spacer pushes messages to the bottom (messages enter bottom, scroll up)
        self.spacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.messages_layout.addItem(self.spacer)

        self.scroll_area.setWidget(self.messages_container)
        self.container_layout.addWidget(self.scroll_area, 1)

        # 5. Bottom Resize Handle (Visible in Edit Mode)
        self.resize_grip_bar = QWidget(self.container_frame)
        grip_layout = QHBoxLayout(self.resize_grip_bar)
        grip_layout.setContentsMargins(0, 0, 2, 0)
        grip_layout.addStretch()
        self.grip_label = QLabel("◢", self.resize_grip_bar)
        self.grip_label.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.grip_label.setStyleSheet("color: #00e5ff; font-size: 11pt;")
        grip_layout.addWidget(self.grip_label)
        self.container_layout.addWidget(self.resize_grip_bar)

        self._update_appearance()

    def _apply_window_flags(self) -> None:
        """Sets frameless, transparent, always-on-top, tool-window flags."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Apply native Win32 styles and capture protection once native HWND is active
        hwnd = int(self.winId())
        if hwnd:
            self.style_mgr.configure_overlay_styles(hwnd)
            if self.settings.capture_protection:
                status, msg = self.capture_mgr.set_protection(hwnd, enable=True)
                logger.info("Startup capture protection on HWND 0x%08X: %s (%s)", hwnd, status, msg)
            if self._is_click_through:
                self.style_mgr.set_click_through(hwnd, True)

    def _cycle_theme(self) -> None:
        presets = ["cyberpunk", "stealth", "glass", "neon", "retro"]
        curr = getattr(self.settings, "theme_preset", "cyberpunk")
        next_idx = (presets.index(curr) + 1) % len(presets) if curr in presets else 0
        self.settings.theme_preset = presets[next_idx]
        self.config_mgr.save()
        self.apply_settings_changes()
        self.settings_changed.emit()

    def _cycle_style(self) -> None:
        styles = ["card", "bubble", "clean"]
        curr = getattr(self.settings, "chat_style", "card")
        next_idx = (styles.index(curr) + 1) % len(styles) if curr in styles else 0
        self.settings.chat_style = styles[next_idx]
        self.config_mgr.save()
        self.apply_settings_changes()
        self.settings_changed.emit()

    def _update_appearance(self) -> None:
        """Refreshes stylesheets and borders based on current mode and opacity settings."""
        theme = get_theme(getattr(self.settings, "theme_preset", "cyberpunk"))
        bg_alpha = int(self.settings.background_opacity * 255)
        bg_color = theme.background_color.replace("{alpha}", str(bg_alpha))
        border_css = f"border: 1px solid {theme.border_color};" if not self._is_locked else "border: none;"

        self.container_frame.setStyleSheet(
            f"QFrame#ContainerFrame {{ "
            f"background-color: {bg_color}; "
            f"{border_css} "
            f"border-radius: 6px; "
            f"}}"
        )

        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(f"color: {theme.accent_color}; font-weight: bold; font-size: 9.5pt;")
        if hasattr(self, "theme_cycle_btn"):
            self.theme_cycle_btn.setText(f"🎨 {theme.display_name.split()[0]}")
        if hasattr(self, "style_cycle_btn"):
            self.style_cycle_btn.setText(f"🗂️ {self.settings.chat_style.title()}")
        if hasattr(self, "grip_label"):
            self.grip_label.setStyleSheet(f"color: {theme.accent_color}; font-size: 11pt;")

        self.header_bar.setVisible(not self._is_locked)
        self.resize_grip_bar.setVisible(not self._is_locked)
        self.hint_banner.setVisible(self.settings.first_launch and not self._is_locked)
        if not self._is_clutch_dimmed:
            self.setWindowOpacity(self.settings.overlay_opacity)

    def set_locked(self, locked: bool) -> None:
        """Switches between Edit Mode (interactive controls) and Locked Mode (minimal HUD)."""
        self._is_locked = locked
        self.settings.locked = locked
        if locked and self.settings.first_launch:
            self.settings.first_launch = False

        self._update_appearance()
        self.config_mgr.save()
        self.mode_changed.emit(locked)
        logger.info("Overlay mode changed: locked=%s", locked)

    def is_locked(self) -> bool:
        return self._is_locked

    def animate_clutch_opacity(self, target_opacity: float, duration_ms: int = 300) -> None:
        """
        Smoothly animates windowOpacity towards target_opacity.
        Used by Clutch Mode to dim the overlay during high-stakes gameplay and restore it.
        """
        clamped_target = max(0.0, min(float(target_opacity), 1.0))
        if self._clutch_anim:
            self._clutch_anim.stop()

        self._clutch_anim = QPropertyAnimation(self, b"windowOpacity")
        self._clutch_anim.setDuration(max(50, duration_ms))
        self._clutch_anim.setStartValue(self.windowOpacity())
        self._clutch_anim.setEndValue(clamped_target)
        self._clutch_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._clutch_anim.start()
        self._is_clutch_dimmed = (clamped_target < (self.settings.overlay_opacity * 0.5))
        logger.debug("Overlay animated opacity to %.2f over %d ms", clamped_target, duration_ms)

    def on_clutch_opacity_changed(self, target_opacity: float) -> None:
        """Slot for ClutchManager.opacity_target_changed signal."""
        self.animate_clutch_opacity(target_opacity, duration_ms=300)

    def set_click_through(self, enabled: bool) -> None:
        """Toggles Win32 click-through pass-through behavior."""
        self._is_click_through = enabled
        self.settings.click_through = enabled
        hwnd = int(self.winId())
        if hwnd:
            self.style_mgr.set_click_through(hwnd, enabled)
        self.config_mgr.save()
        logger.info("Overlay click-through updated: %s", enabled)

    def is_click_through(self) -> bool:
        return self._is_click_through

    def set_capture_test_mode(self, active: bool) -> None:
        """Displays or hides the prominent high-contrast OBS capture test banner."""
        self._capture_test_mode = active
        self.test_banner.setVisible(active)
        logger.info("Capture test mode: %s", active)

    def is_capture_test_mode(self) -> bool:
        return self._capture_test_mode

    def add_message(self, msg: ChatMessage) -> None:
        """Appends a new chat message to the overlay, maintaining limits."""
        if hasattr(self, "filter_engine") and self.filter_engine:
            if not self.filter_engine.should_display(
                msg,
                filter_bot_commands=getattr(self.settings, "filter_bot_commands", True),
                filter_duplicates=getattr(self.settings, "filter_duplicates", True),
            ):
                return

        widget = ChatMessageWidget(msg, self.settings, self.messages_container)
        widget.expired.connect(self._remove_message_widget)

        self.messages_layout.addWidget(widget)
        self._messages.append(widget)

        if getattr(widget, "is_mentioned", False):
            self.mention_detected.emit(msg.username, msg.message)

        # Enforce maximum messages limit
        while len(self._messages) > self.settings.max_messages:
            oldest = self._messages.pop(0)
            self._remove_message_widget(oldest)

        # Auto-scroll to bottom
        QTimer.singleShot(10, self._scroll_to_bottom)

    def clear_chat(self) -> None:
        """Removes all current chat messages from the view."""
        for w in list(self._messages):
            self._remove_message_widget(w)
        self._messages.clear()

    def _remove_message_widget(self, widget: QWidget) -> None:
        """Safely detaches and deletes a message widget."""
        if widget in self._messages:
            self._messages.remove(widget)
        self.messages_layout.removeWidget(widget)
        widget.deleteLater()

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _check_message_expirations(self) -> None:
        """Checks if any messages have exceeded the configured lifetime and initiates fading."""
        if self.settings.message_lifetime_sec <= 0:
            return  # Expiration disabled

        now = time.time()
        lifetime = self.settings.message_lifetime_sec
        fade_duration = self.settings.fade_duration_sec

        for widget in list(self._messages):
            if not widget._is_fading and (now - widget.created_at) >= lifetime:
                widget.start_fade_out(fade_duration)

    def apply_settings_changes(self) -> None:
        """Applies updated styling settings from ConfigManager."""
        self._update_appearance()
        self.messages_layout.setSpacing(self.settings.message_spacing)

        # Re-render messages with updated theme and styling
        current_msgs = [w.msg for w in self._messages]
        self.clear_chat()
        for m in current_msgs:
            w = ChatMessageWidget(m, self.settings, self.messages_container)
            w.expired.connect(self._remove_message_widget)
            self.messages_layout.addWidget(w)
            self._messages.append(w)

        # Refresh capture protection if changed
        hwnd = int(self.winId())
        if hwnd:
            self.capture_mgr.set_protection(hwnd, self.settings.capture_protection)
            self.style_mgr.set_click_through(hwnd, self.settings.click_through)

    # --- Mouse interaction for dragging and resizing in Edit Mode ---

    def mousePressEvent(self, event) -> None:
        if self._is_locked:
            event.ignore()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            # Check if clicking on bottom-right corner for resizing
            resize_rect = QRect(self.width() - 25, self.height() - 25, 25, 25)
            if resize_rect.contains(pos):
                self._is_resizing = True
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_orig_geo = self.geometry()
                event.accept()
                return

            # Otherwise drag window
            self._is_dragging = True
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._is_locked:
            event.ignore()
            return

        if self._is_resizing:
            delta = event.globalPosition().toPoint() - self._resize_origin
            new_w = max(self.minimumWidth(), self._resize_orig_geo.width() + delta.x())
            new_h = max(self.minimumHeight(), self._resize_orig_geo.height() + delta.y())
            self.resize(new_w, new_h)
            event.accept()
            return

        if self._is_dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_position
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._is_dragging or self._is_resizing:
            self._is_dragging = False
            self._is_resizing = False
            # Persist newly adjusted position/dimensions
            geo = self.geometry()
            self.settings.overlay_x = geo.x()
            self.settings.overlay_y = geo.y()
            self.settings.overlay_width = geo.width()
            self.settings.overlay_height = geo.height()
            self.config_mgr.save()
            event.accept()
