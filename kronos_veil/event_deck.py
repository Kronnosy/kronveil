"""
Stream Events Deck Window for Kronos Veil.
Renders recent stream events (Followers, Subs, Bits, Tips) and a dynamic
live Goal Progress Bar in an always-on-top, click-through, capture-protected floating bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import random
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from kronos_veil.config import ConfigManager
from kronos_veil.themes import get_theme
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    event_type: str  # "follower", "sub", "bits", "tip"
    username: str
    amount: str = ""
    message: str = ""
    timestamp: str = ""

    def display_text(self) -> str:
        if self.event_type == "follower":
            return f"🌟 Follow: {self.username}"
        elif self.event_type == "sub":
            return f"👑 Sub: {self.username}"
        elif self.event_type == "bits":
            return f"💎 Bits: {self.username} ({self.amount})"
        elif self.event_type == "tip":
            return f"💸 Tip: {self.username} (${self.amount})"
        return f"⚡ {self.username}: {self.message}"


@dataclass
class GoalProgress:
    title: str = "Sub Goal"
    current: int = 18
    target: int = 25

    @property
    def percentage(self) -> int:
        if self.target <= 0:
            return 100
        return min(100, int((self.current / self.target) * 100))


class EventService(QWidget):
    """
    Service managing stream events and goals.
    Provides automatic tokenless demo event simulation and optional webhook/API ingestion.
    """

    event_received = Signal(StreamEvent)
    goal_updated = Signal(GoalProgress)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_goal = GoalProgress(title="Sub Goal", current=18, target=25)
        self._demo_timer = QTimer(self)
        self._demo_timer.timeout.connect(self._generate_random_event)
        self._sim_users = [
            "NeoGamer", "CyberValkyrie", "PhantomBlade", "AuraStream",
            "ByteMaster", "VoxelQueen", "ShadowRunner", "RetroRider"
        ]

    def start_demo_cycle(self, interval_ms: int = 22000) -> None:
        """Starts generating simulated events periodically for tokenless testing."""
        if not self._demo_timer.isActive():
            self._demo_timer.start(interval_ms)

    def stop_demo_cycle(self) -> None:
        if self._demo_timer.isActive():
            self._demo_timer.stop()

    def simulate_event(self, event_type: str, username: str, amount: str = "", message: str = "") -> None:
        now_str = datetime.now().strftime("%H:%M")
        ev = StreamEvent(
            event_type=event_type,
            username=username,
            amount=amount,
            message=message,
            timestamp=now_str,
        )
        if event_type == "sub":
            self.current_goal.current += 1
            self.goal_updated.emit(self.current_goal)
        self.event_received.emit(ev)

    def _generate_random_event(self) -> None:
        types = ["follower", "sub", "bits", "tip"]
        ev_type = random.choice(types)
        user = random.choice(self._sim_users)
        amount = ""
        if ev_type == "bits":
            amount = str(random.choice([50, 100, 250, 500]))
        elif ev_type == "tip":
            amount = f"{random.choice([3.0, 5.0, 10.0, 20.0]):.2f}"
        self.simulate_event(ev_type, user, amount)


class EventDeckWindow(QWidget):
    """
    Modular floating Stream Events & Goal Ticker HUD.
    Draggable in Edit Mode and click-through/capture-protected when locked.
    """

    mode_changed = Signal(bool)
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

        self._is_locked: bool = getattr(self.settings, "event_deck_locked", False)
        self._is_dragging: bool = False
        self._drag_position: QPoint = QPoint()

        self.event_service = EventService(self)

        self._init_ui()
        self._apply_window_flags()

        # Connect event service signals
        self.event_service.event_received.connect(self._on_event_received)
        self.event_service.goal_updated.connect(self._on_goal_updated)

        # Start simulated demo events if in demo provider
        if getattr(self.settings, "chat_provider", "demo") == "demo":
            self.event_service.start_demo_cycle(20000)

    def _init_ui(self) -> None:
        self.setObjectName("KronosVeilEventDeck")
        deck_x = getattr(self.settings, "event_deck_x", 60)
        deck_y = getattr(self.settings, "event_deck_y", 80)
        deck_w = getattr(self.settings, "event_deck_width", 500)
        deck_h = getattr(self.settings, "event_deck_height", 42)
        self.setGeometry(deck_x, deck_y, deck_w, deck_h)
        self.setMinimumSize(360, 38)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.frame = QFrame(self)
        self.frame.setObjectName("EventDeckFrame")
        root_layout.addWidget(self.frame)

        self.layout = QHBoxLayout(self.frame)
        self.layout.setContentsMargins(10, 4, 10, 4)
        self.layout.setSpacing(10)

        # 1. Edit Grip label
        self.edit_grip_label = QLabel("✦ EVENTS", self.frame)
        self.edit_grip_label.setStyleSheet("color: #a855f7; font-weight: bold; font-size: 8.5pt;")
        self.layout.addWidget(self.edit_grip_label)

        # 2. Latest Event Chip
        self.event_chip = QLabel("🌟 Welcome to Stream!", self.frame)
        self.event_chip.setStyleSheet(
            "background-color: rgba(168, 85, 247, 0.2); color: #f3e8ff; "
            "font-weight: 600; font-size: 8.5pt; border-radius: 4px; padding: 2px 8px;"
        )
        self.layout.addWidget(self.event_chip)

        # 3. Dynamic Goal Progress
        self.goal_label = QLabel("🎯 Goal: 18/25", self.frame)
        self.goal_label.setStyleSheet("color: #38bdf8; font-size: 8.5pt; font-weight: bold;")
        self.layout.addWidget(self.goal_label)

        self.progress_bar = QProgressBar(self.frame)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(72)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setFixedWidth(90)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: rgba(255, 255, 255, 0.15); border-radius: 4px; } "
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a855f7, stop:1 #00e5ff); border-radius: 4px; }"
        )
        self.layout.addWidget(self.progress_bar)

        self.layout.addStretch()

        # 4. Lock Button (Edit mode only)
        self.lock_btn = QPushButton("🔒 Lock", self.frame)
        self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lock_btn.setStyleSheet(
            "background: rgba(168, 85, 247, 0.2); border: 1px solid #a855f7; "
            "color: #a855f7; border-radius: 3px; font-size: 8pt; padding: 2px 8px;"
        )
        self.lock_btn.clicked.connect(lambda: self.set_locked(True))
        self.layout.addWidget(self.lock_btn)

        self._apply_theme_styling()

    def _apply_window_flags(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def _apply_theme_styling(self) -> None:
        preset_name = getattr(self.settings, "theme_preset", "cyberpunk")
        palette = get_theme(preset_name)

        if not self._is_locked:
            # Edit Mode
            self.frame.setStyleSheet(
                f"#EventDeckFrame {{ background-color: rgba(18, 18, 26, 0.92); "
                f"border: 1px dashed {palette.accent_color}; border-radius: 6px; }}"
            )
            self.edit_grip_label.show()
            self.lock_btn.show()
        else:
            # Locked Mode
            self.frame.setStyleSheet(
                "#EventDeckFrame { background-color: rgba(12, 14, 20, 0.70); "
                "border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; }"
            )
            self.edit_grip_label.hide()
            self.lock_btn.hide()

    def set_locked(self, locked: bool) -> None:
        self._is_locked = locked
        self.settings.event_deck_locked = locked
        self.config_mgr.save()
        self._apply_theme_styling()

        hwnd = int(self.winId())
        if hwnd:
            if locked and getattr(self.settings, "click_through", False):
                self.style_mgr.set_click_through(hwnd, True)
            else:
                self.style_mgr.set_click_through(hwnd, False)

            if getattr(self.settings, "capture_protection", True):
                self.capture_mgr.set_protection(hwnd, True)

        self.mode_changed.emit(locked)

    def is_locked(self) -> bool:
        return self._is_locked

    def _on_event_received(self, event: StreamEvent) -> None:
        text = event.display_text()
        self.event_chip.setText(text)

        # Color-code chip based on event type
        if event.event_type == "follower":
            self.event_chip.setStyleSheet(
                "background-color: rgba(56, 189, 248, 0.25); color: #bae6fd; "
                "font-weight: 600; font-size: 8.5pt; border-radius: 4px; padding: 2px 8px;"
            )
        elif event.event_type == "sub":
            self.event_chip.setStyleSheet(
                "background-color: rgba(168, 85, 247, 0.35); color: #f3e8ff; "
                "font-weight: bold; font-size: 8.5pt; border-radius: 4px; padding: 2px 8px;"
            )
        elif event.event_type == "bits":
            self.event_chip.setStyleSheet(
                "background-color: rgba(234, 179, 8, 0.25); color: #fef08a; "
                "font-weight: bold; font-size: 8.5pt; border-radius: 4px; padding: 2px 8px;"
            )
        elif event.event_type == "tip":
            self.event_chip.setStyleSheet(
                "background-color: rgba(34, 197, 94, 0.25); color: #bbf7d0; "
                "font-weight: bold; font-size: 8.5pt; border-radius: 4px; padding: 2px 8px;"
            )

    def _on_goal_updated(self, goal: GoalProgress) -> None:
        self.goal_label.setText(f"🎯 {goal.title}: {goal.current}/{goal.target}")
        self.progress_bar.setValue(goal.percentage)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._is_locked and event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._is_locked and self._is_dragging and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_position
            self.move(new_pos)
            self.settings.event_deck_x = new_pos.x()
            self.settings.event_deck_y = new_pos.y()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_dragging:
            self._is_dragging = False
            self.config_mgr.save()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        hwnd = int(self.winId())
        if hwnd:
            if getattr(self.settings, "capture_protection", True):
                self.capture_mgr.set_protection(hwnd, True)
            if self._is_locked and getattr(self.settings, "click_through", False):
                self.style_mgr.set_click_through(hwnd, True)
