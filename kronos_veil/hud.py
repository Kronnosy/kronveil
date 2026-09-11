"""
Standalone Modular Mini-HUD Window for Kronos Veil.
Renders real-time stream status, OBS connection health, bitrate, dropped frames,
and viewer count in an always-on-top, click-through, capture-protected HUD bar.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from kronos_veil.config import AppSettings, ConfigManager
from kronos_veil.obs.client import OBSStreamStats
from kronos_veil.themes import get_theme
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager

logger = logging.getLogger(__name__)


class MiniHudWindow(QWidget):
    """
    Independent floating status HUD.
    Displays live metrics from OBS Studio and streaming platform.
    Can be dragged in Edit Mode and locked with full click-through transparency.
    """

    mode_changed = Signal(bool)  # True = locked, False = edit
    open_settings_requested = Signal()

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

        self._is_locked: bool = getattr(self.settings, "hud_locked", False)
        self._is_dragging: bool = False
        self._drag_position: QPoint = QPoint()

        self._current_stats = OBSStreamStats()
        self._viewer_count: int = 0

        self._bomb_timer = QTimer(self)
        self._bomb_timer.setInterval(100)
        self._bomb_timer.timeout.connect(self._on_bomb_tick)
        self._bomb_remaining: float = 0.0
        self._bomb_end_time: float = 0.0

        self._init_ui()
        self._apply_window_flags()

    def _init_ui(self) -> None:
        self.setObjectName("KronosVeilMiniHud")
        hud_x = getattr(self.settings, "hud_x", 60)
        hud_y = getattr(self.settings, "hud_y", 30)
        self.setGeometry(hud_x, hud_y, 480, 44)
        self.setMinimumSize(320, 38)

        # Root layout
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Container Frame
        self.frame = QFrame(self)
        self.frame.setObjectName("HudFrame")
        root_layout.addWidget(self.frame)

        self.layout = QHBoxLayout(self.frame)
        self.layout.setContentsMargins(10, 4, 10, 4)
        self.layout.setSpacing(10)

        # 1. Drag / Edit Mode Label (visible only in Edit Mode)
        self.edit_grip_label = QLabel("✦ HUD", self.frame)
        self.edit_grip_label.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 8.5pt;")
        self.layout.addWidget(self.edit_grip_label)

        # 2. Live Status Badge (🔴 LIVE / ⚪ OFFLINE)
        self.live_badge = QLabel("⚪ OFFLINE", self.frame)
        self.live_badge.setStyleSheet(
            "background-color: #2d3748; color: #a0aec0; font-weight: bold; "
            "font-size: 8.5pt; border-radius: 4px; padding: 2px 6px;"
        )
        self.layout.addWidget(self.live_badge)

        # 2b. OBS Recording Badge (⏺️ REC)
        self.rec_badge = QLabel("⏺️ REC", self.frame)
        self.rec_badge.setStyleSheet(
            "background-color: #dc2626; color: #ffffff; font-weight: bold; "
            "font-size: 8pt; border-radius: 3px; padding: 2px 5px;"
        )
        self.rec_badge.hide()
        self.layout.addWidget(self.rec_badge)

        # 3. Uptime
        self.uptime_label = QLabel("⏱️ 00:00:00", self.frame)
        self.uptime_label.setStyleSheet("color: #e2e8f0; font-size: 9pt; font-family: 'Segoe UI';")
        self.layout.addWidget(self.uptime_label)

        # 4. Bitrate
        self.bitrate_label = QLabel("⚡ 0 kbps", self.frame)
        self.bitrate_label.setStyleSheet("color: #38bdf8; font-size: 9pt; font-family: 'Segoe UI';")
        self.layout.addWidget(self.bitrate_label)

        # 5. Dropped Frames Warning
        self.frames_label = QLabel("📉 0.0%", self.frame)
        self.frames_label.setStyleSheet("color: #4ade80; font-size: 9pt; font-family: 'Segoe UI';")
        self.layout.addWidget(self.frames_label)

        # 6. Viewers
        self.viewers_label = QLabel("👥 0", self.frame)
        self.viewers_label.setStyleSheet("color: #c084fc; font-size: 9pt; font-family: 'Segoe UI';")
        self.layout.addWidget(self.viewers_label)

        # 6b. CS2 / GSI Live Indicators
        self.cs2_badge = QLabel("🎮 CS2", self.frame)
        self.cs2_badge.setStyleSheet(
            "background-color: #ea580c; color: #ffffff; font-weight: bold; "
            "font-size: 8pt; border-radius: 3px; padding: 2px 5px;"
        )
        self.cs2_badge.hide()
        self.layout.addWidget(self.cs2_badge)

        self.round_badge = QLabel("R: --", self.frame)
        self.round_badge.setStyleSheet("color: #fed7aa; font-size: 8.5pt; font-weight: 600; font-family: 'Segoe UI';")
        self.round_badge.hide()
        self.layout.addWidget(self.round_badge)

        self.bomb_badge = QLabel("💣 40s", self.frame)
        self.bomb_badge.setStyleSheet(
            "background-color: #dc2626; color: #ffffff; font-weight: bold; "
            "font-size: 8pt; border-radius: 3px; padding: 2px 6px;"
        )
        self.bomb_badge.hide()
        self.layout.addWidget(self.bomb_badge)

        # 6c. Hype Spike Meter Badge
        self.hype_badge = QLabel("🔥 0.0/s", self.frame)
        self.hype_badge.setStyleSheet(
            "background-color: rgba(249, 115, 22, 0.25); color: #fdba74; "
            "font-weight: bold; font-size: 8pt; border-radius: 3px; padding: 2px 5px;"
        )
        self.hype_badge.hide()
        self.layout.addWidget(self.hype_badge)

        self.layout.addStretch()

        # 7. Lock Button (Edit Mode only)
        self.lock_btn = QPushButton("🔒 Lock", self.frame)
        self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lock_btn.setStyleSheet(
            "background: rgba(0, 229, 255, 0.15); border: 1px solid #00e5ff; "
            "color: #00e5ff; border-radius: 3px; font-size: 8pt; padding: 2px 8px;"
        )
        self.lock_btn.clicked.connect(lambda: self.set_locked(True))
        self.layout.addWidget(self.lock_btn)

        self.apply_layout_mode()
        self._update_style()

    def _apply_window_flags(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_platform_win32_attributes()

    def _apply_platform_win32_attributes(self) -> None:
        hwnd = int(self.winId())
        if not hwnd:
            return

        # Exclude HUD window from OBS / screen capture
        if getattr(self.settings, "capture_protection", True):
            self.capture_mgr.set_protection(hwnd, True)

        self.style_mgr.ensure_topmost(hwnd)

        # Apply click-through when locked
        if self._is_locked:
            self.style_mgr.set_click_through(hwnd, True)
        else:
            self.style_mgr.set_click_through(hwnd, False)

    def set_locked(self, locked: bool) -> None:
        """Toggles between draggable Edit Mode and click-through Locked Mode."""
        self._is_locked = locked
        setattr(self.settings, "hud_locked", locked)
        self.config_mgr.save()

        hwnd = int(self.winId())
        if hwnd:
            self.style_mgr.set_click_through(hwnd, locked)

        self._update_style()
        self.mode_changed.emit(locked)

    def apply_layout_mode(self) -> None:
        """Adapts HUD dimensions and visible widgets according to hud_layout setting."""
        mode = getattr(self.settings, "hud_layout", "horizontal")
        if mode == "compact":
            self.uptime_label.hide()
            self.viewers_label.hide()
            self.setMinimumSize(220, 36)
            self.resize(300, 38)
        else:
            self.uptime_label.show()
            self.viewers_label.show()
            self.setMinimumSize(320, 38)
            self.resize(480, 44)
        self._update_style()

    def is_locked(self) -> bool:
        return self._is_locked

    def update_stats(self, stats: OBSStreamStats) -> None:
        """Updates UI elements with fresh telemetry from OBS WebSocket."""
        self._current_stats = stats

        # Update recording badge
        if getattr(stats, "is_recording", False):
            self.rec_badge.show()
        else:
            self.rec_badge.hide()

        if stats.is_live:
            self.live_badge.setText("🔴 LIVE")
            self.live_badge.setStyleSheet(
                "background-color: #dc2626; color: #ffffff; font-weight: bold; "
                "font-size: 8.5pt; border-radius: 4px; padding: 2px 6px;"
            )
            self.uptime_label.setText(f"⏱️ {stats.uptime}")
            self.bitrate_label.setText(f"⚡ {stats.bitrate_kbps:,} kbps")

            # Dynamic bitrate health color coding
            if stats.bitrate_kbps >= 5500:
                bitrate_col = "#22c55e"
            elif stats.bitrate_kbps >= 3500:
                bitrate_col = "#f59e0b"
            else:
                bitrate_col = "#ef4444"
            self.bitrate_label.setStyleSheet(f"color: {bitrate_col}; font-weight: 600; font-size: 9pt;")

            if stats.has_warning:
                self.frames_label.setText(f"⚠️ {stats.dropped_frames} ({stats.dropped_percent}%)")
                self.frames_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 9pt;")
            else:
                self.frames_label.setText(f"📉 {stats.dropped_percent}%")
                self.frames_label.setStyleSheet("color: #4ade80; font-size: 9pt;")
        elif stats.is_connected:
            self.live_badge.setText("READY")
            self.live_badge.setStyleSheet(
                "background-color: #15803d; color: #ffffff; font-weight: bold; "
                "font-size: 8.5pt; border-radius: 4px; padding: 2px 6px;"
            )
            self.uptime_label.setText("⏱️ 00:00:00")
            self.bitrate_label.setText("⚡ 0 kbps")
            self.bitrate_label.setStyleSheet("color: #38bdf8; font-size: 9pt;")
            self.frames_label.setText("📉 0.0%")
            self.frames_label.setStyleSheet("color: #4ade80; font-size: 9pt;")
        else:
            self.live_badge.setText("⚪ OFFLINE")
            self.live_badge.setStyleSheet(
                "background-color: #2d3748; color: #a0aec0; font-weight: bold; "
                "font-size: 8.5pt; border-radius: 4px; padding: 2px 6px;"
            )
            self.uptime_label.setText("⏱️ --:--:--")
            self.bitrate_label.setText("⚡ --")
            self.bitrate_label.setStyleSheet("color: #718096; font-size: 9pt;")
            self.frames_label.setText("📉 --")
            self.frames_label.setStyleSheet("color: #718096; font-size: 9pt;")

    def update_viewers(self, viewers: int) -> None:
        """Updates viewer count display."""
        self._viewer_count = viewers
        self.viewers_label.setText(f"👥 {viewers:,}")

    def _on_bomb_tick(self) -> None:
        rem = max(0.0, self._bomb_end_time - time.time())
        self._bomb_remaining = rem
        if rem <= 0.0:
            self._bomb_timer.stop()
            self.bomb_badge.setText("💥 0.0s")
            self.bomb_badge.setStyleSheet(
                "background-color: #7f1d1d; color: #fca5a5; font-weight: bold; font-size: 8pt; border-radius: 3px; padding: 2px 6px;"
            )
        else:
            self.bomb_badge.setText(f"💣 {rem:.1f}s")
            if rem <= 10.0 and int(rem * 5) % 2 == 0:
                self.bomb_badge.setStyleSheet(
                    "background-color: #ffffff; color: #dc2626; font-weight: 900; font-size: 8pt; border-radius: 3px; padding: 2px 6px;"
                )
            else:
                self.bomb_badge.setStyleSheet(
                    "background-color: #dc2626; color: #ffffff; font-weight: bold; font-size: 8pt; border-radius: 3px; padding: 2px 6px;"
                )

    def update_bomb_state(self, bomb_state: str, duration_sec: float = 40.0) -> None:
        """Updates or triggers the live bomb countdown timer on the HUD."""
        state_str = (bomb_state or "").lower()
        if state_str == "planted":
            self.bomb_badge.show()
            self._bomb_remaining = duration_sec
            self._bomb_end_time = time.time() + duration_sec
            self.bomb_badge.setText(f"💣 {duration_sec:.1f}s")
            self.bomb_badge.setStyleSheet(
                "background-color: #dc2626; color: #ffffff; font-weight: bold; font-size: 8pt; border-radius: 3px; padding: 2px 6px;"
            )
            if not self._bomb_timer.isActive():
                self._bomb_timer.start()
        elif state_str == "defused":
            self._bomb_timer.stop()
            self.bomb_badge.show()
            self.bomb_badge.setText("✅ DEFUSED")
            self.bomb_badge.setStyleSheet(
                "background-color: #15803d; color: #ffffff; font-weight: bold; font-size: 8pt; border-radius: 3px; padding: 2px 6px;"
            )
            QTimer.singleShot(4000, lambda: self.bomb_badge.hide() if not self._bomb_timer.isActive() else None)
        elif state_str == "exploded":
            self._bomb_timer.stop()
            self.bomb_badge.show()
            self.bomb_badge.setText("💥 EXPLODED")
            self.bomb_badge.setStyleSheet(
                "background-color: #7f1d1d; color: #fca5a5; font-weight: bold; font-size: 8pt; border-radius: 3px; padding: 2px 6px;"
            )
            QTimer.singleShot(4000, lambda: self.bomb_badge.hide() if not self._bomb_timer.isActive() else None)
        else:
            self._bomb_timer.stop()
            self.bomb_badge.hide()

    def update_gsi_state(self, state: Any) -> None:
        """Updates CS2 game telemetry: round badge, live score, and bomb status."""
        if not getattr(state, "is_in_game", False):
            self.cs2_badge.hide()
            self.round_badge.hide()
            self.bomb_badge.hide()
            self._bomb_timer.stop()
            return

        self.cs2_badge.show()
        self.round_badge.show()

        t_score = getattr(getattr(state, "map", None), "team_t_score", 0)
        ct_score = getattr(getattr(state, "map", None), "team_ct_score", 0)
        phase = getattr(getattr(state, "round", None), "phase", "") or ""

        if (t_score > 0 or ct_score > 0):
            self.round_badge.setText(f"T {t_score} - {ct_score} CT")
        elif phase:
            self.round_badge.setText(f"R: {phase.upper()}")
        else:
            self.round_badge.setText("CS2 MATCH")

        bomb = getattr(getattr(state, "round", None), "bomb", None) or ""
        if bomb:
            self.update_bomb_state(bomb)
        elif not self._bomb_timer.isActive():
            self.bomb_badge.hide()

    def update_hype(self, velocity: float, is_spike: bool = False) -> None:
        """Updates real-time hype velocity badge on HUD."""
        if velocity >= 0.8 or is_spike:
            self.hype_badge.show()
            self.hype_badge.setText(f"🔥 {velocity:.1f}/s")
            if is_spike:
                self.hype_badge.setStyleSheet(
                    "background-color: #dc2626; color: #ffffff; font-weight: bold; font-size: 8pt; border-radius: 3px; padding: 2px 5px;"
                )
            else:
                self.hype_badge.setStyleSheet(
                    "background-color: rgba(249, 115, 22, 0.25); color: #fdba74; font-weight: bold; font-size: 8pt; border-radius: 3px; padding: 2px 5px;"
                )
        else:
            self.hype_badge.hide()

    def _update_style(self) -> None:
        theme = get_theme(getattr(self.settings, "theme_preset", "cyberpunk"))
        if self._is_locked:
            self.edit_grip_label.hide()
            self.lock_btn.hide()
            self.frame.setStyleSheet(
                f"QFrame#HudFrame {{ "
                f"background-color: rgba(12, 16, 23, 0.88); "
                f"border: 1px solid {theme.border_color}; "
                f"border-radius: 8px; "
                f"}}"
            )
        else:
            self.edit_grip_label.show()
            self.lock_btn.show()
            self.edit_grip_label.setStyleSheet(f"color: {theme.accent_color}; font-weight: bold; font-size: 8.5pt;")
            self.lock_btn.setStyleSheet(
                f"background: rgba(0, 229, 255, 0.15); border: 1px solid {theme.accent_color}; "
                f"color: {theme.accent_color}; border-radius: 3px; font-size: 8pt; padding: 2px 8px;"
            )
            self.frame.setStyleSheet(
                f"QFrame#HudFrame {{ "
                f"background-color: rgba(18, 24, 38, 0.95); "
                f"border: 1.5px dashed {theme.accent_color}; "
                f"border-radius: 8px; "
                f"}}"
            )

    # Mouse Event handling for dragging in Edit Mode
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._is_locked and event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_dragging and event.buttons() & Qt.MouseButton.LeftButton:
            new_top_left = event.globalPosition().toPoint() - self._drag_position
            self.move(new_top_left)
            setattr(self.settings, "hud_x", self.x())
            setattr(self.settings, "hud_y", self.y())
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_dragging:
            self._is_dragging = False
            setattr(self.settings, "hud_x", self.x())
            setattr(self.settings, "hud_y", self.y())
            self.config_mgr.save()
            event.accept()
