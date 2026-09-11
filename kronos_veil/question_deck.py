"""
Capture-Protected Smart Q&A Deck Window for Kronos Veil.
Renders queued viewer questions with one-click 'Mark Answered' and 'Dismiss' actions,
transparent background, theme-based styling, click-through pass-through, and WDA_EXCLUDEFROMCAPTURE protection.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from kronos_veil.chat.questions import QuestionDeckManager, QuestionItem
from kronos_veil.config import ConfigManager
from kronos_veil.themes import get_theme
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager

logger = logging.getLogger(__name__)


class QuestionCardWidget(QFrame):
    """
    Card widget representing a single viewer question.
    Provides 1-click 'Mark Answered' and 'Dismiss' buttons.
    """

    answered_clicked = Signal(str)  # question_id
    dismiss_clicked = Signal(str)   # question_id

    def __init__(self, item: QuestionItem, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.item = item
        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("QuestionCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 8, 10, 8)
        root_layout.setSpacing(6)

        # 1. Header row: Platform badge + Username + Timestamp + Action Buttons
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        # Platform badge
        platform_colors = {
            "twitch": ("#9146ff", "#ffffff"),
            "kick": ("#53fc18", "#000000"),
            "youtube": ("#ff0000", "#ffffff"),
            "demo": ("#00e5ff", "#000000"),
        }
        bg_col, txt_col = platform_colors.get(self.item.platform.lower(), ("#38bdf8", "#000000"))

        self.platform_badge = QLabel(self.item.platform.upper()[:3], self)
        self.platform_badge.setStyleSheet(
            f"background-color: {bg_col}; color: {txt_col}; font-weight: 800; "
            f"font-size: 7.5pt; border-radius: 3px; padding: 1px 4px;"
        )
        header_layout.addWidget(self.platform_badge)

        # Username
        self.author_label = QLabel(self.item.author or "Anonymous", self)
        self.author_label.setStyleSheet("color: #f1f5f9; font-weight: bold; font-size: 8.5pt;")
        header_layout.addWidget(self.author_label)

        # Timestamp
        self.time_label = QLabel(self.item.timestamp, self)
        self.time_label.setStyleSheet("color: #64748b; font-size: 8pt;")
        header_layout.addWidget(self.time_label)

        header_layout.addStretch()

        # Action: Mark Answered
        self.answer_btn = QPushButton("✓ Answered", self)
        self.answer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.answer_btn.setStyleSheet(
            "QPushButton { background: rgba(34, 197, 94, 0.2); border: 1px solid #22c55e; "
            "color: #4ade80; border-radius: 3px; font-size: 8pt; font-weight: 600; padding: 2px 7px; } "
            "QPushButton:hover { background: #22c55e; color: #ffffff; }"
        )
        self.answer_btn.clicked.connect(lambda: self.answered_clicked.emit(self.item.id))
        header_layout.addWidget(self.answer_btn)

        # Action: Dismiss
        self.dismiss_btn = QPushButton("✕", self)
        self.dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dismiss_btn.setToolTip("Dismiss Question")
        self.dismiss_btn.setStyleSheet(
            "QPushButton { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); "
            "color: #f87171; border-radius: 3px; font-size: 8pt; font-weight: bold; padding: 2px 6px; } "
            "QPushButton:hover { background: #ef4444; color: #ffffff; }"
        )
        self.dismiss_btn.clicked.connect(lambda: self.dismiss_clicked.emit(self.item.id))
        header_layout.addWidget(self.dismiss_btn)

        root_layout.addLayout(header_layout)

        # 2. Question Text
        self.text_label = QLabel(self.item.text, self)
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("color: #e2e8f0; font-size: 9pt; line-height: 1.3;")
        root_layout.addWidget(self.text_label)

        self._apply_state_style()

    def update_item(self, item: QuestionItem) -> None:
        self.item = item
        self.text_label.setText(item.text)
        self._apply_state_style()

    def _apply_state_style(self) -> None:
        if self.item.is_answered:
            self.setStyleSheet(
                "QFrame#QuestionCard { background-color: rgba(20, 35, 25, 0.75); "
                "border: 1px solid rgba(34, 197, 94, 0.4); border-radius: 6px; }"
            )
            self.answer_btn.setText("✓ Done")
            self.answer_btn.setEnabled(False)
            self.answer_btn.setStyleSheet(
                "background: rgba(34, 197, 94, 0.3); border: none; color: #86efac; "
                "border-radius: 3px; font-size: 8pt; padding: 2px 6px;"
            )
            self.text_label.setStyleSheet("color: #94a3b8; font-size: 9pt; text-decoration: line-through;")
        elif self.item.is_dismissed:
            self.setStyleSheet(
                "QFrame#QuestionCard { background-color: rgba(35, 20, 20, 0.6); "
                "border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; }"
            )
            self.text_label.setStyleSheet("color: #64748b; font-size: 9pt;")
        else:
            self.setStyleSheet(
                "QFrame#QuestionCard { background-color: rgba(18, 24, 38, 0.85); "
                "border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; }"
            )
            self.text_label.setStyleSheet("color: #f1f5f9; font-size: 9pt;")


class QuestionDeckWindow(QWidget):
    """
    Floating, independent, capture-protected Smart Q&A Deck Window.
    Allows streamers to view, answer, and dismiss audience questions in real time.
    """

    mode_changed = Signal(bool)
    open_settings_requested = Signal()

    def __init__(
        self,
        config_mgr: ConfigManager,
        capture_mgr: CaptureProtectionManager,
        style_mgr: WindowStyleManager,
        deck_mgr: Optional[QuestionDeckManager] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_mgr = config_mgr
        self.settings = config_mgr.settings
        self.capture_mgr = capture_mgr
        self.style_mgr = style_mgr
        self.deck_mgr = deck_mgr or QuestionDeckManager(
            qa_max_items=getattr(self.settings, "qa_max_items", 20),
            qa_auto_expire_seconds=getattr(self.settings, "qa_auto_expire_seconds", 300),
        )

        self._is_locked: bool = getattr(self.settings, "qa_deck_locked", False)
        self._is_dragging: bool = False
        self._drag_position: QPoint = QPoint()
        self._is_resizing: bool = False
        self._resize_origin: QPoint = QPoint()
        self._resize_orig_geo: QRect = QRect()

        self._cards: Dict[str, QuestionCardWidget] = {}

        self._init_ui()
        self._apply_window_flags()
        self._connect_deck_signals()

    def _init_ui(self) -> None:
        self.setObjectName("KronosVeilQuestionDeck")
        deck_x = getattr(self.settings, "qa_deck_x", 60)
        deck_y = getattr(self.settings, "qa_deck_y", 140)
        deck_w = getattr(self.settings, "qa_deck_width", 440)
        deck_h = getattr(self.settings, "qa_deck_height", 300)
        self.setGeometry(deck_x, deck_y, deck_w, deck_h)
        self.setMinimumSize(280, 160)

        # Root layout
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Frame container
        self.frame = QFrame(self)
        self.frame.setObjectName("QuestionDeckFrame")
        root_layout.addWidget(self.frame)

        self.container_layout = QVBoxLayout(self.frame)
        self.container_layout.setContentsMargins(10, 8, 10, 8)
        self.container_layout.setSpacing(8)

        # 1. Header Bar
        self.header_bar = QWidget(self.frame)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.edit_grip_label = QLabel("✦ Q&A DECK", self.header_bar)
        self.edit_grip_label.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 9pt;")
        header_layout.addWidget(self.edit_grip_label)

        self.count_badge = QLabel("0", self.header_bar)
        self.count_badge.setStyleSheet(
            "background-color: rgba(0, 229, 255, 0.2); color: #00e5ff; "
            "font-weight: bold; font-size: 8pt; border-radius: 8px; padding: 2px 7px;"
        )
        header_layout.addWidget(self.count_badge)

        header_layout.addStretch()

        # Clear All Button
        self.clear_btn = QPushButton("🗑️ Clear", self.header_bar)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip("Clear all questions from deck")
        self.clear_btn.setStyleSheet(
            "QPushButton { background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.15); "
            "color: #cbd5e1; border-radius: 3px; font-size: 8pt; padding: 2px 8px; } "
            "QPushButton:hover { background: rgba(239, 68, 68, 0.25); color: #f87171; }"
        )
        self.clear_btn.clicked.connect(self.deck_mgr.clear)
        header_layout.addWidget(self.clear_btn)

        # Lock Button (Edit Mode only)
        self.lock_btn = QPushButton("🔒 Lock", self.header_bar)
        self.lock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lock_btn.setStyleSheet(
            "QPushButton { background: rgba(0, 229, 255, 0.15); border: 1px solid #00e5ff; "
            "color: #00e5ff; border-radius: 3px; font-size: 8pt; padding: 2px 8px; } "
            "QPushButton:hover { background: #00e5ff; color: #000000; }"
        )
        self.lock_btn.clicked.connect(lambda: self.set_locked(True))
        header_layout.addWidget(self.lock_btn)

        self.container_layout.addWidget(self.header_bar)

        # 2. Scroll Area containing questions
        self.scroll_area = QScrollArea(self.frame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; } "
            "QScrollBar:vertical { background: rgba(0, 0, 0, 0.2); width: 6px; border-radius: 3px; } "
            "QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.25); border-radius: 3px; } "
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(6)

        # Empty State Indicator
        self.empty_label = QLabel("No questions queued.\nQuestions from chat will appear here.", self.scroll_content)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #64748b; font-size: 9pt; font-style: italic; padding: 20px;")
        self.cards_layout.addWidget(self.empty_label)

        self.cards_spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.cards_layout.addItem(self.cards_spacer)

        self.scroll_area.setWidget(self.scroll_content)
        self.container_layout.addWidget(self.scroll_area, 1)

        # 3. Bottom Resize Grip Bar (visible only in Edit Mode)
        self.resize_grip_bar = QWidget(self.frame)
        grip_layout = QHBoxLayout(self.resize_grip_bar)
        grip_layout.setContentsMargins(0, 0, 2, 0)
        grip_layout.addStretch()
        self.grip_label = QLabel("◢", self.resize_grip_bar)
        self.grip_label.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.grip_label.setStyleSheet("color: #00e5ff; font-size: 10pt;")
        grip_layout.addWidget(self.grip_label)
        self.container_layout.addWidget(self.resize_grip_bar)

        self._apply_theme_styling()
        self._refresh_all_cards()

    def _apply_window_flags(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def _connect_deck_signals(self) -> None:
        self.deck_mgr.question_added.connect(self._on_question_added)
        self.deck_mgr.question_updated.connect(self._on_question_updated)
        self.deck_mgr.question_removed.connect(self._on_question_removed)
        self.deck_mgr.deck_cleared.connect(self._on_deck_cleared)

    def _apply_theme_styling(self) -> None:
        preset_name = getattr(self.settings, "theme_preset", "cyberpunk")
        palette = get_theme(preset_name)

        if not self._is_locked:
            # Edit Mode
            self.frame.setStyleSheet(
                f"#QuestionDeckFrame {{ background-color: rgba(14, 18, 28, 0.92); "
                f"border: 1.5px dashed {palette.accent_color}; border-radius: 8px; }}"
            )
            self.edit_grip_label.show()
            self.lock_btn.show()
            self.clear_btn.show()
            self.resize_grip_bar.show()
        else:
            # Locked Mode
            self.frame.setStyleSheet(
                "#QuestionDeckFrame { background-color: rgba(10, 14, 22, 0.75); "
                "border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px; }"
            )
            self.edit_grip_label.hide()
            self.lock_btn.hide()
            self.clear_btn.hide()
            self.resize_grip_bar.hide()

        self.edit_grip_label.setStyleSheet(f"color: {palette.accent_color}; font-weight: bold; font-size: 9pt;")
        self.grip_label.setStyleSheet(f"color: {palette.accent_color}; font-size: 10pt;")

    def set_locked(self, locked: bool) -> None:
        self._is_locked = locked
        setattr(self.settings, "qa_deck_locked", locked)
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        hwnd = int(self.winId())
        if hwnd:
            if getattr(self.settings, "capture_protection", True):
                self.capture_mgr.set_protection(hwnd, True)
            if self._is_locked and getattr(self.settings, "click_through", False):
                self.style_mgr.set_click_through(hwnd, True)

    def _on_question_added(self, item: QuestionItem) -> None:
        if item.id in self._cards:
            self._cards[item.id].update_item(item)
            return

        card = QuestionCardWidget(item, self.scroll_content)
        card.answered_clicked.connect(self.deck_mgr.mark_answered)
        card.dismiss_clicked.connect(self.deck_mgr.dismiss_question)

        self._cards[item.id] = card
        # Insert before spacer
        insert_idx = max(0, self.cards_layout.count() - 1)
        self.cards_layout.insertWidget(insert_idx, card)
        self._update_visibility()

    def _on_question_updated(self, item: QuestionItem) -> None:
        if item.id in self._cards:
            self._cards[item.id].update_item(item)
        self._update_visibility()

    def _on_question_removed(self, q_id: str) -> None:
        card = self._cards.pop(q_id, None)
        if card:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._update_visibility()

    def _on_deck_cleared(self) -> None:
        for card in self._cards.values():
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._update_visibility()

    def _refresh_all_cards(self) -> None:
        self._on_deck_cleared()
        for q in self.deck_mgr.get_active_questions(include_answered=True, include_dismissed=False):
            self._on_question_added(q)

    def _update_visibility(self) -> None:
        active_count = self.deck_mgr.active_count()
        self.count_badge.setText(str(active_count))
        self.empty_label.setVisible(len(self._cards) == 0)

    # Dragging & Resizing handling in Edit Mode
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._is_locked and event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            # Bottom-right corner check for resizing (within 24px)
            if pos.x() >= self.width() - 24 and pos.y() >= self.height() - 24:
                self._is_resizing = True
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_orig_geo = self.geometry()
            else:
                self._is_dragging = True
                self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._is_locked and event.buttons() & Qt.MouseButton.LeftButton:
            if self._is_resizing:
                delta = event.globalPosition().toPoint() - self._resize_origin
                new_w = max(self.minimumWidth(), self._resize_orig_geo.width() + delta.x())
                new_h = max(self.minimumHeight(), self._resize_orig_geo.height() + delta.y())
                self.resize(new_w, new_h)
                setattr(self.settings, "qa_deck_width", new_w)
                setattr(self.settings, "qa_deck_height", new_h)
            elif self._is_dragging:
                new_pos = event.globalPosition().toPoint() - self._drag_position
                self.move(new_pos)
                setattr(self.settings, "qa_deck_x", new_pos.x())
                setattr(self.settings, "qa_deck_y", new_pos.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_dragging or self._is_resizing:
            self._is_dragging = False
            self._is_resizing = False
            self.config_mgr.save()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
