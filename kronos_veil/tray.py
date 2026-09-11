"""
System Tray integration for Kronos Veil.
Maintains persistent access to overlay controls even when click-through mode is active.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

logger = logging.getLogger(__name__)


def create_default_icon(size: int = 64) -> QIcon:
    """Generates a sleek, high-DPI procedural Kronos Veil HUD icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Dark background shield / hexagon
    painter.setBrush(QColor(15, 23, 42))
    painter.setPen(QColor(0, 229, 255))
    painter.drawRoundedRect(4, 4, size - 8, size - 8, 12, 12)

    # Stylized "KV" text
    painter.setPen(QColor(0, 229, 255))
    font = QFont("Segoe UI", int(size * 0.32), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), 0x0004 | 0x0080, "KV")  # AlignHCenter | AlignVCenter

    painter.end()
    return QIcon(pixmap)


class TrayManager(QObject):
    """Manages the Windows taskbar notification area (System Tray) icon and menu."""

    show_overlay_requested = Signal()
    hide_overlay_requested = Signal()
    edit_mode_requested = Signal()
    lock_mode_requested = Signal()
    toggle_click_through_requested = Signal()
    toggle_capture_protection_requested = Signal()
    open_settings_requested = Signal()
    toggle_hud_requested = Signal()
    toggle_event_deck_requested = Signal()
    toggle_qa_deck_requested = Signal()
    switch_profile_requested = Signal(str)
    send_demo_message_requested = Signal()
    clear_chat_requested = Signal()
    copy_companion_url_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.tray_icon = QSystemTrayIcon(self)

        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            self.tray_icon.setIcon(create_default_icon())

        self.tray_icon.setToolTip("Kronos Veil — Streamer Chat Overlay")
        self._init_menu()
        self.tray_icon.show()

    def _init_menu(self) -> None:
        self.menu = QMenu()
        self.menu.setStyleSheet(
            "QMenu { background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; padding: 4px; } "
            "QMenu::item { padding: 5px 20px; border-radius: 3px; } "
            "QMenu::item:selected { background-color: #0284c7; color: #ffffff; } "
            "QMenu::separator { height: 1px; background: #334155; margin: 4px 6px; }"
        )

        # Title / Brand Action
        title_action = QAction("✦ Kronos Veil v1.3", self.menu)
        title_action.setEnabled(False)
        self.menu.addAction(title_action)
        self.menu.addSeparator()

        # Visibility
        self.act_show = QAction("Show Overlay", self.menu)
        self.act_show.triggered.connect(self.show_overlay_requested.emit)
        self.menu.addAction(self.act_show)

        self.act_hide = QAction("Hide Overlay", self.menu)
        self.act_hide.triggered.connect(self.hide_overlay_requested.emit)
        self.menu.addAction(self.act_hide)

        self.menu.addSeparator()

        # Operational Modes
        self.act_edit = QAction("Edit Overlay (Unlock)", self.menu)
        self.act_edit.triggered.connect(self.edit_mode_requested.emit)
        self.menu.addAction(self.act_edit)

        self.act_lock = QAction("Lock Overlay (Ctrl+Shift+F10)", self.menu)
        self.act_lock.triggered.connect(self.lock_mode_requested.emit)
        self.menu.addAction(self.act_lock)

        self.act_clickthrough = QAction("Click-Through Mode", self.menu)
        self.act_clickthrough.setCheckable(True)
        self.act_clickthrough.triggered.connect(self.toggle_click_through_requested.emit)
        self.menu.addAction(self.act_clickthrough)

        self.act_capture = QAction("Capture Protection (OBS Privacy)", self.menu)
        self.act_capture.setCheckable(True)
        self.act_capture.triggered.connect(self.toggle_capture_protection_requested.emit)
        self.menu.addAction(self.act_capture)

        # Modular Windows
        self.act_hud = QAction("Toggle Mini-HUD Bar", self.menu)
        self.act_hud.setCheckable(True)
        self.act_hud.triggered.connect(self.toggle_hud_requested.emit)
        self.menu.addAction(self.act_hud)

        self.act_event_deck = QAction("Toggle Stream Events Deck", self.menu)
        self.act_event_deck.setCheckable(True)
        self.act_event_deck.triggered.connect(self.toggle_event_deck_requested.emit)
        self.menu.addAction(self.act_event_deck)

        self.act_qa_deck = QAction("Toggle Smart Q&A Deck", self.menu)
        self.act_qa_deck.setCheckable(True)
        self.act_qa_deck.triggered.connect(self.toggle_qa_deck_requested.emit)
        self.menu.addAction(self.act_qa_deck)

        self.menu.addSeparator()

        # Profiles Submenu
        self.profiles_menu = QMenu("🕹️ Game Profiles", self.menu)
        for prof_name in ["Default", "Valorant", "League of Legends", "Counter-Strike 2"]:
            act_prof = QAction(prof_name, self.profiles_menu)
            act_prof.triggered.connect(lambda checked=False, p=prof_name: self.switch_profile_requested.emit(p))
            self.profiles_menu.addAction(act_prof)
        self.menu.addMenu(self.profiles_menu)

        self.menu.addSeparator()

        # Chat actions
        act_demo = QAction("Send Demo Message", self.menu)
        act_demo.triggered.connect(self.send_demo_message_requested.emit)
        self.menu.addAction(act_demo)

        act_clear = QAction("Clear Chat", self.menu)
        act_clear.triggered.connect(self.clear_chat_requested.emit)
        self.menu.addAction(act_clear)

        act_companion = QAction("📱 Copy Mobile Companion URL", self.menu)
        act_companion.triggered.connect(self.copy_companion_url_requested.emit)
        self.menu.addAction(act_companion)

        act_settings = QAction("Settings...", self.menu)
        act_settings.triggered.connect(self.open_settings_requested.emit)
        self.menu.addAction(act_settings)

        self.menu.addSeparator()

        # Exit
        act_exit = QAction("Exit Kronos Veil", self.menu)
        act_exit.triggered.connect(self.exit_requested.emit)
        self.menu.addAction(act_exit)

        self.tray_icon.setContextMenu(self.menu)

    def update_states(
        self,
        locked: bool,
        click_through: bool,
        capture_protected: bool,
        hud_visible: bool = True,
        event_deck_visible: bool = True,
        qa_deck_visible: bool = False,
    ) -> None:
        """Updates checkmarks and state hints in tray menu."""
        self.act_clickthrough.setChecked(click_through)
        self.act_capture.setChecked(capture_protected)
        self.act_hud.setChecked(hud_visible)
        self.act_event_deck.setChecked(event_deck_visible)
        self.act_qa_deck.setChecked(qa_deck_visible)
        self.act_edit.setEnabled(locked)
        self.act_lock.setEnabled(not locked)
