"""
Application Orchestrator for Kronos Veil.
Initializes and coordinates the Overlay, Settings Window, Tray, Hotkey Manager, and Chat Providers.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from kronos_veil.chat.base import ChatMessage, ChatProvider
from kronos_veil.chat.demo import DemoChatProvider
from kronos_veil.chat.twitch import TwitchChatProvider
from kronos_veil.chat.youtube import YouTubeChatProvider
from kronos_veil.config import ConfigManager
from kronos_veil.hotkeys import HotkeyManager
from kronos_veil.overlay import OverlayWindow
from kronos_veil.settings_window import SettingsWindow
from kronos_veil.tray import TrayManager
from kronos_veil.windows.capture_protection import CaptureProtectionManager
from kronos_veil.windows.window_styles import WindowStyleManager

logger = logging.getLogger(__name__)


class KronosVeilApp(QObject):
    """Core controller coordinating all Kronos Veil subsystems."""

    def __init__(self, qapp: QApplication, config_path: Optional[str] = None) -> None:
        super().__init__()
        self.qapp = qapp

        # 1. Configuration & Win32 Managers
        self.config_mgr = ConfigManager(config_path)
        self.settings = self.config_mgr.settings
        self.capture_mgr = CaptureProtectionManager()
        self.style_mgr = WindowStyleManager()

        # 2. Multi-monitor position sanitation
        self._sanitize_screen_positions()

        # 3. Create Windows & UI Elements
        self.overlay = OverlayWindow(self.config_mgr, self.capture_mgr, self.style_mgr)
        self.settings_window = SettingsWindow(self.config_mgr, self.capture_mgr)
        self.tray = TrayManager(self)

        # 4. Global Hotkeys
        self.hotkeys = HotkeyManager(self)
        self._setup_hotkeys()

        # 5. Chat Provider Management
        self.current_provider: Optional[ChatProvider] = None
        self._init_chat_provider()

        # 6. Wire All Signals
        self._wire_signals()

        # 7. First Launch Setup or Standard Startup
        self._handle_startup()

    def _sanitize_screen_positions(self) -> None:
        """Validates that saved window coordinates are within currently active screens."""
        screens = []
        for s in QGuiApplication.screens():
            geo = s.geometry()
            screens.append((geo.x(), geo.y(), geo.width(), geo.height()))

        if screens:
            self.config_mgr.sanitize_coordinates(screens)

    def _setup_hotkeys(self) -> None:
        """Configures and activates global hotkey listeners."""
        self.hotkeys.register_hotkey("toggle_lock", self.settings.hotkey_toggle_lock)
        self.hotkeys.register_hotkey("toggle_clickthrough", self.settings.hotkey_toggle_clickthrough)
        self.hotkeys.register_hotkey("peek", self.settings.hotkey_peek)
        self.hotkeys.hotkey_pressed.connect(self._on_hotkey_triggered)
        self.hotkeys.start()

    def _init_chat_provider(self) -> None:
        """Instantiates the chat provider defined in settings."""
        if self.current_provider:
            self.current_provider.disconnect_chat()
            self.current_provider.message_received.disconnect(self._on_message_received)
            self.current_provider.deleteLater()

        provider_type = self.settings.chat_provider

        if provider_type == "twitch":
            self.current_provider = TwitchChatProvider(channel=self.settings.twitch_channel)
        elif provider_type == "youtube":
            self.current_provider = YouTubeChatProvider(video_id=self.settings.youtube_video_id)
        else:
            self.current_provider = DemoChatProvider()

        self.current_provider.message_received.connect(self._on_message_received)
        self.current_provider.status_changed.connect(self._on_chat_status_changed)
        self.current_provider.connect_chat()
        logger.info("Initialized chat provider: %s", provider_type)

    def _wire_signals(self) -> None:
        # Tray signals
        self.tray.show_overlay_requested.connect(self.overlay.show)
        self.tray.hide_overlay_requested.connect(self.overlay.hide)
        self.tray.edit_mode_requested.connect(lambda: self.set_locked_mode(False))
        self.tray.lock_mode_requested.connect(lambda: self.set_locked_mode(True))
        self.tray.toggle_click_through_requested.connect(self._toggle_click_through)
        self.tray.toggle_capture_protection_requested.connect(self._toggle_capture_protection)
        self.tray.open_settings_requested.connect(self._open_settings)
        self.tray.send_demo_message_requested.connect(self._send_demo_message)
        self.tray.clear_chat_requested.connect(self.overlay.clear_chat)
        self.tray.exit_requested.connect(self.shutdown)

        # Overlay signals
        self.overlay.open_settings_requested.connect(self._open_settings)
        self.overlay.mode_changed.connect(self._on_mode_changed)

        # Settings window signals
        self.settings_window.settings_changed.connect(self._on_settings_updated)
        self.settings_window.demo_message_requested.connect(self._send_demo_message)
        self.settings_window.clear_chat_requested.connect(self.overlay.clear_chat)
        self.settings_window.capture_test_toggled.connect(self.overlay.set_capture_test_mode)
        self.settings_window.reset_position_requested.connect(self._reset_overlay_position)
        self.settings_window.provider_reconnect_requested.connect(self._init_chat_provider)

    def _handle_startup(self) -> None:
        """Manages first launch onboarding or standard overlay display."""
        self.overlay.show()
        self.tray.update_states(
            locked=self.overlay.is_locked(),
            click_through=self.overlay.is_click_through(),
            capture_protected=self.settings.capture_protection,
        )

        if self.settings.first_launch:
            logger.info("First launch detected: starting in Edit Mode with initial demo messages.")
            self.overlay.set_locked(False)
            # Inject initial sample messages so the user immediately sees the visual styling
            QTimer.singleShot(400, self._seed_initial_messages)

    def _seed_initial_messages(self) -> None:
        """Injects a pleasant welcome message and demo chat lines."""
        welcome_msg = ChatMessage(
            username="KronosVeil",
            message="Welcome to Kronos Veil! Drag and resize this chat, then press Ctrl+Shift+F10 to lock it.",
            color="#00e5ff",
            is_system=True,
        )
        self.overlay.add_message(welcome_msg)

        demo1 = ChatMessage(username="CyberSamurai", message="yo streamer! GL HF in the match!", color="#ff007f")
        demo2 = ChatMessage(username="PixelKnight", message="chat is looking clean and private", color="#b388ff")
        self.overlay.add_message(demo1)
        self.overlay.add_message(demo2)

    def _on_hotkey_triggered(self, action_id: str) -> None:
        logger.info("Handling hotkey action: %s", action_id)
        if action_id == "toggle_lock":
            new_locked = not self.overlay.is_locked()
            self.set_locked_mode(new_locked)
        elif action_id == "toggle_clickthrough":
            self._toggle_click_through()
        elif action_id == "peek":
            # Momentarily raise overlay and bring topmost
            hwnd = int(self.overlay.winId())
            if hwnd:
                self.style_mgr.ensure_topmost(hwnd)

    def set_locked_mode(self, locked: bool) -> None:
        self.overlay.set_locked(locked)
        if not locked:
            # Entering Edit Mode: disable click-through so user can click/drag/resize
            self.overlay.set_click_through(False)
        else:
            # Entering Locked Mode: restore user's preferred click-through setting
            if self.settings.click_through:
                self.overlay.set_click_through(True)

        self.tray.update_states(
            locked=self.overlay.is_locked(),
            click_through=self.overlay.is_click_through(),
            capture_protected=self.settings.capture_protection,
        )
        self.settings_window.refresh_from_settings()

    def _toggle_click_through(self) -> None:
        new_state = not self.overlay.is_click_through()
        self.overlay.set_click_through(new_state)
        self.tray.update_states(
            locked=self.overlay.is_locked(),
            click_through=new_state,
            capture_protected=self.settings.capture_protection,
        )
        self.settings_window.refresh_from_settings()

    def _toggle_capture_protection(self) -> None:
        new_state = not self.settings.capture_protection
        self.settings.capture_protection = new_state
        self.config_mgr.save()
        hwnd = int(self.overlay.winId())
        if hwnd:
            self.capture_mgr.set_protection(hwnd, new_state)
        self.tray.update_states(
            locked=self.overlay.is_locked(),
            click_through=self.overlay.is_click_through(),
            capture_protected=new_state,
        )
        self.settings_window.refresh_from_settings()

    def _open_settings(self) -> None:
        self.settings_window.refresh_from_settings()
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _send_demo_message(self) -> None:
        if isinstance(self.current_provider, DemoChatProvider):
            self.current_provider.send_manual_message(
                text="Test chat reaction from Kronos Veil! 🚀",
                username="LiveViewer",
                color="#00ffff",
            )
        else:
            msg = ChatMessage(
                username="LiveViewer",
                message="Test chat reaction from Kronos Veil! 🚀",
                color="#00ffff",
                is_test=True,
            )
            self.overlay.add_message(msg)

    def _reset_overlay_position(self) -> None:
        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            geo = primary_screen.geometry()
            new_x = geo.x() + 80
            new_y = geo.y() + 100
            self.overlay.move(new_x, new_y)
            self.settings.overlay_x = new_x
            self.settings.overlay_y = new_y
            self.config_mgr.save()

    def _on_mode_changed(self, locked: bool) -> None:
        self.tray.update_states(
            locked=locked,
            click_through=self.overlay.is_click_through(),
            capture_protected=self.settings.capture_protection,
        )

    def _on_settings_updated(self) -> None:
        self.overlay.apply_settings_changes()
        self.tray.update_states(
            locked=self.overlay.is_locked(),
            click_through=self.overlay.is_click_through(),
            capture_protected=self.settings.capture_protection,
        )

    def _on_message_received(self, msg: ChatMessage) -> None:
        self.overlay.add_message(msg)

    def _on_chat_status_changed(self, status: str, detail: str) -> None:
        logger.info("Chat Status: %s - %s", status, detail)

    def shutdown(self) -> None:
        logger.info("Initiating graceful application shutdown...")
        self.hotkeys.stop()
        if self.current_provider:
            self.current_provider.disconnect_chat()
        self.config_mgr.save()
        self.qapp.quit()
