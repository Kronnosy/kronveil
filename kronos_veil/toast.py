"""
In-game capture-protected toast notification manager for Kronos Veil.
Renders ephemeral, non-intrusive stream telemetry and chat alert pills on top of games.
Fully excluded from OBS and screen capture via WDA_EXCLUDEFROMCAPTURE.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QPoint, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from kronos_veil.config import AppSettings, ConfigManager
from kronos_veil.themes import get_theme
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager

logger = logging.getLogger(__name__)


class ToastWindow(QWidget):
    """
    Floating, capture-protected toast card.
    Displays stream state changes, dropped frame warnings, and chat mentions.
    """

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

        self._fade_anim: Optional[QPropertyAnimation] = None
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._fade_out)

        self._init_ui()
        self._apply_window_flags()

    def _init_ui(self) -> None:
        self.setObjectName("KronosVeilToast")
        self.resize(360, 52)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame(self)
        self.card.setObjectName("ToastCard")
        root_layout.addWidget(self.card)

        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(10)

        self.icon_label = QLabel("🔔", self.card)
        self.icon_label.setStyleSheet("font-size: 14pt;")
        card_layout.addWidget(self.icon_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.title_label = QLabel("Notification", self.card)
        self.title_label.setStyleSheet("font-weight: 700; font-size: 9.5pt; color: #f8fafc;")
        text_layout.addWidget(self.title_label)

        self.message_label = QLabel("", self.card)
        self.message_label.setStyleSheet("font-size: 8.5pt; color: #94a3b8;")
        self.message_label.setWordWrap(True)
        text_layout.addWidget(self.message_label)

        card_layout.addLayout(text_layout, 1)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        self.reposition()

    def _apply_window_flags(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        hwnd = int(self.winId())
        if hwnd:
            self.style_mgr.configure_overlay_styles(hwnd)
            self.style_mgr.set_click_through(hwnd, True)
            if getattr(self.settings, "capture_protection", True):
                self.capture_mgr.set_protection(hwnd, True)

    def reposition(self) -> None:
        """Positions toast horizontally centered at the top of the primary screen."""
        hud_x = getattr(self.settings, "hud_x", 60)
        hud_y = getattr(self.settings, "hud_y", 30)
        # Position slightly offset below or adjacent to HUD
        self.move(max(20, hud_x), max(10, hud_y + 48))

    def show_toast(
        self,
        title: str,
        message: str,
        icon: str = "🔔",
        level: str = "info",
        duration_sec: Optional[float] = None,
    ) -> None:
        """Presents an in-game toast with smooth fade-in and auto-dismiss."""
        if not getattr(self.settings, "toast_enabled", True):
            return

        theme = get_theme(getattr(self.settings, "theme_preset", "cyberpunk"))
        self.reposition()

        # Color schemes by level
        level_colors = {
            "info": (theme.accent_color, "rgba(15, 23, 42, 0.92)", theme.border_color),
            "success": ("#22c55e", "rgba(5, 46, 22, 0.92)", "#16a34a"),
            "warning": ("#f59e0b", "rgba(69, 26, 3, 0.92)", "#d97706"),
            "danger": ("#ef4444", "rgba(69, 10, 10, 0.92)", "#dc2626"),
            "mention": ("#ff007f", "rgba(42, 12, 34, 0.92)", "#ff007f"),
            "hype": ("#fdba74", "rgba(124, 45, 18, 0.95)", "#ea580c"),
        }
        title_color, bg_color, border_color = level_colors.get(level, level_colors["info"])

        self.card.setStyleSheet(
            f"QFrame#ToastCard {{ "
            f"background-color: {bg_color}; "
            f"border: 1.5px solid {border_color}; "
            f"border-radius: 8px; "
            f"}}"
        )
        self.icon_label.setText(icon)
        self.title_label.setText(title)
        self.title_label.setStyleSheet(
            f"font-weight: 700; font-size: 9.5pt; color: {title_color}; font-family: '{theme.font_family}';"
        )
        self.message_label.setText(message)
        self.message_label.setStyleSheet(
            f"font-size: 8.5pt; color: #f1f5f9; font-family: '{theme.font_family}';"
        )

        self.show()
        self.raise_()

        # Fade in
        if self._fade_anim:
            self._fade_anim.stop()

        self._fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self._fade_anim.setDuration(220)
        self._fade_anim.setStartValue(self.opacity_effect.opacity())
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        timeout = duration_sec or getattr(self.settings, "toast_duration_sec", 4.0)
        self._dismiss_timer.start(int(timeout * 1000))

    def _fade_out(self) -> None:
        if self._fade_anim:
            self._fade_anim.stop()
        self._fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self._fade_anim.setDuration(350)
        self._fade_anim.setStartValue(self.opacity_effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()


# Backward and semantic compatibility alias
ToastNotification = ToastWindow
