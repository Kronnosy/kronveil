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

from kronos_veil.chat.aggregator import UnifiedChatProvider
from kronos_veil.chat.base import ChatMessage, ChatProvider
from kronos_veil.chat.demo import DemoChatProvider
from kronos_veil.chat.kick import KickChatProvider
from kronos_veil.chat.hype import HypeDetector, HypeSpikeEvent
from kronos_veil.chat.questions import QuestionDeckManager
from kronos_veil.chat.twitch import TwitchChatProvider
from kronos_veil.chat.youtube import YouTubeChatProvider
from kronos_veil.config import ConfigManager
from kronos_veil.event_deck import EventDeckWindow
from kronos_veil.gsi.clutch_manager import ClutchManager
from kronos_veil.gsi.server import GsiServer
from kronos_veil.hotkeys import HotkeyManager
from kronos_veil.hud import MiniHudWindow
from kronos_veil.obs.client import OBSStreamStats, OBSWebSocketClient
from kronos_veil.overlay import OverlayWindow
from kronos_veil.profiles import GameProfile, ProfileManager
from kronos_veil.question_deck import QuestionDeckWindow
from kronos_veil.settings_window import SettingsWindow
from kronos_veil.toast import ToastWindow
from kronos_veil.tray import TrayManager
from kronos_veil.web import WebCompanionServer, get_local_lan_ip
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

        # 3. Create Profiles Manager
        self.profile_mgr = ProfileManager(getattr(self.settings, "profiles", None))
        self.profile_mgr.auto_switch_enabled = getattr(self.settings, "auto_profile_enabled", True)

        # 4. Create Windows & UI Elements
        self.overlay = OverlayWindow(self.config_mgr, self.capture_mgr, self.style_mgr)
        self.hud = MiniHudWindow(self.config_mgr, self.capture_mgr, self.style_mgr)
        self.event_deck = EventDeckWindow(self.config_mgr, self.capture_mgr, self.style_mgr)
        self.settings_window = SettingsWindow(self.config_mgr, self.capture_mgr, self.profile_mgr)
        self.toast = ToastWindow(self.config_mgr, self.capture_mgr, self.style_mgr)
        self.tray = TrayManager(self)

        # Web Companion Server
        self.web_companion = WebCompanionServer(
            port=getattr(self.settings, "web_companion_port", 8989),
            pin=getattr(self.settings, "web_companion_pin", "7749"),
        )
        if getattr(self.settings, "web_companion_enabled", True):
            self.web_companion.start()

        self._prev_is_live: bool = False
        self._prev_is_recording: bool = False
        self._prev_has_warning: bool = False

        # 4. OBS WebSocket Client
        self.obs_client = OBSWebSocketClient(
            host=self.settings.obs_host,
            port=self.settings.obs_port,
            password=self.settings.obs_password,
        )

        # 4b. v1.3 Intelligence Engines & Surfaces
        self.qa_deck_mgr = QuestionDeckManager(
            qa_max_items=getattr(self.settings, "qa_max_items", 20),
            qa_auto_expire_seconds=getattr(self.settings, "qa_auto_expire_seconds", 300),
        )
        self.qa_deck = QuestionDeckWindow(
            self.config_mgr,
            self.capture_mgr,
            self.style_mgr,
            deck_mgr=self.qa_deck_mgr,
        )

        self.hype_detector = HypeDetector(
            settings=self.settings,
            obs_client=self.obs_client,
        )

        self.gsi_server = GsiServer(
            port=getattr(self.settings, "gsi_port", 31337),
            auth_token=getattr(self.settings, "gsi_auth_token", ""),
        )
        self.clutch_manager = ClutchManager(settings=self.settings)
        self.clutch_manager.attach_gsi_server(self.gsi_server)
        if getattr(self.settings, "gsi_enabled", False):
            self.gsi_server.start()

        # Connect Companion Server with Intelligence Engines
        self.web_companion.attach_question_deck(self.qa_deck_mgr)
        self.web_companion.attach_hype_detector(self.hype_detector)
        self.web_companion.attach_clutch_manager(self.clutch_manager)

        # 5. Global Hotkeys
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
            try:
                self.current_provider.message_received.disconnect(self._on_message_received)
            except Exception:
                pass
            self.current_provider.deleteLater()

        if getattr(self.settings, "multistream_enabled", False):
            self.current_provider = UnifiedChatProvider(self.settings)
        else:
            provider_type = self.settings.chat_provider
            if provider_type == "twitch":
                self.current_provider = TwitchChatProvider(channel=self.settings.twitch_channel)
            elif provider_type == "kick":
                self.current_provider = KickChatProvider(channel=getattr(self.settings, "kick_channel", ""))
            elif provider_type == "youtube":
                self.current_provider = YouTubeChatProvider(video_id=self.settings.youtube_video_id)
            else:
                self.current_provider = DemoChatProvider()

        self.current_provider.message_received.connect(self._on_message_received)
        self.current_provider.status_changed.connect(self._on_chat_status_changed)
        self.current_provider.connect_chat()
        logger.info(
            "Initialized chat provider: %s",
            "multistream" if getattr(self.settings, "multistream_enabled", False) else self.settings.chat_provider,
        )

    def _wire_signals(self) -> None:
        # Tray signals
        self.tray.show_overlay_requested.connect(self.overlay.show)
        self.tray.hide_overlay_requested.connect(self.overlay.hide)
        self.tray.edit_mode_requested.connect(lambda: self.set_locked_mode(False))
        self.tray.lock_mode_requested.connect(lambda: self.set_locked_mode(True))
        self.tray.toggle_click_through_requested.connect(self._toggle_click_through)
        self.tray.toggle_capture_protection_requested.connect(self._toggle_capture_protection)
        self.tray.toggle_hud_requested.connect(self._toggle_hud_visibility)
        self.tray.toggle_event_deck_requested.connect(self._toggle_event_deck_visibility)
        self.tray.switch_profile_requested.connect(self.profile_mgr.apply_profile)
        self.tray.open_settings_requested.connect(self._open_settings)
        self.tray.send_demo_message_requested.connect(self._send_demo_message)
        self.tray.clear_chat_requested.connect(self.overlay.clear_chat)
        self.tray.exit_requested.connect(self.shutdown)

        # Overlay signals
        self.overlay.open_settings_requested.connect(self._open_settings)
        self.overlay.mode_changed.connect(self._on_mode_changed)
        self.overlay.mention_detected.connect(self._on_mention_detected)
        self.overlay.settings_changed.connect(self._on_settings_updated)

        # Settings window signals
        self.settings_window.settings_changed.connect(self._on_settings_updated)
        self.settings_window.demo_message_requested.connect(self._send_demo_message)
        self.settings_window.clear_chat_requested.connect(self.overlay.clear_chat)
        self.settings_window.capture_test_toggled.connect(self.overlay.set_capture_test_mode)
        self.settings_window.reset_position_requested.connect(self._reset_overlay_position)
        self.settings_window.provider_reconnect_requested.connect(self._init_chat_provider)
        self.settings_window.obs_connect_requested.connect(self._reconnect_obs)
        self.settings_window.hud_toggled.connect(self._set_hud_enabled)
        self.settings_window.hud_lock_toggled.connect(self.hud.set_locked)
        self.settings_window.reset_hud_position_requested.connect(self._reset_hud_position)

        # Modular widgets signals
        self.settings_window.event_deck_toggled.connect(self._set_event_deck_enabled)
        self.settings_window.event_deck_lock_toggled.connect(self.event_deck.set_locked)
        self.settings_window.reset_event_deck_position_requested.connect(self._reset_event_deck_position)
        self.settings_window.simulate_event_requested.connect(self.event_deck.event_service._generate_random_event)

        # Intelligence & Q&A deck signals
        self.settings_window.gsi_toggled.connect(self._on_gsi_toggled)
        self.settings_window.qa_deck_toggled.connect(self._set_qa_deck_enabled)
        self.settings_window.qa_deck_lock_toggled.connect(self.qa_deck.set_locked)
        self.settings_window.reset_qa_deck_position_requested.connect(self._reset_qa_deck_position)
        self.settings_window.clear_qa_deck_requested.connect(self.qa_deck_mgr.clear)
        self.settings_window.simulate_clutch_requested.connect(self._simulate_clutch_mode)
        self.settings_window.simulate_hype_requested.connect(self._simulate_hype_spike)

        # Profiles signals
        self.settings_window.profile_applied.connect(self.profile_mgr.apply_profile)
        self.settings_window.save_current_profile_requested.connect(self._save_current_windows_to_profile)
        self.profile_mgr.profile_applied.connect(self._on_profile_applied)

        # OBS Client signals
        self.obs_client.stats_updated.connect(self._on_obs_stats_updated)
        self.obs_client.connection_changed.connect(self.settings_window.update_obs_status)

        # Modular windows mode change signals
        self.hud.mode_changed.connect(self._on_hud_mode_changed)
        self.event_deck.mode_changed.connect(lambda l: self._update_tray_states())
        self.qa_deck.mode_changed.connect(lambda l: self._update_tray_states())
        self.tray.toggle_qa_deck_requested.connect(self._toggle_qa_deck_visibility)

        # GSI & Clutch Mode signals
        self.clutch_manager.opacity_target_changed.connect(self.overlay.on_clutch_opacity_changed)
        self.clutch_manager.clutch_started.connect(self._on_clutch_started)
        self.clutch_manager.clutch_ended.connect(self._on_clutch_ended)
        self.clutch_manager.bomb_state_changed.connect(self.hud.update_bomb_state)
        self.gsi_server.bridge.state_updated.connect(self.hud.update_gsi_state)

        # Hype Spike Engine signals
        self.hype_detector.velocity_updated.connect(lambda v: self.hud.update_hype(v))
        self.hype_detector.hype_spike_detected.connect(self._on_hype_spike)

        # Web Companion signals
        self.tray.copy_companion_url_requested.connect(self._copy_companion_url)
        self.settings_window.companion_restart_requested.connect(self._restart_companion)
        self.web_companion.bridge.action_requested.connect(self._on_companion_action)

    def _handle_startup(self) -> None:
        """Manages first launch onboarding or standard overlay display."""
        self.overlay.show()
        if getattr(self.settings, "hud_enabled", True):
            self.hud.show()
        if getattr(self.settings, "event_deck_enabled", True):
            self.event_deck.show()
        if getattr(self.settings, "qa_deck_enabled", False):
            self.qa_deck.show()

        if self.profile_mgr.auto_switch_enabled:
            self.profile_mgr.start_monitoring()

        if getattr(self.settings, "obs_enabled", False):
            self.obs_client.connect_obs()

        self._update_tray_states()

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

        self._update_tray_states()
        self.settings_window.refresh_from_settings()

    def _toggle_click_through(self) -> None:
        new_state = not self.overlay.is_click_through()
        self.overlay.set_click_through(new_state)
        self._update_tray_states()
        self.settings_window.refresh_from_settings()

    def _toggle_capture_protection(self) -> None:
        new_state = not self.settings.capture_protection
        self.settings.capture_protection = new_state
        self.config_mgr.save()
        for win in (self.overlay, self.hud, self.event_deck, self.qa_deck):
            hwnd = int(win.winId())
            if hwnd:
                self.capture_mgr.set_protection(hwnd, new_state)
        self._update_tray_states()
        self.settings_window.refresh_from_settings()

    def _toggle_hud_visibility(self) -> None:
        new_visible = not self.hud.isVisible()
        self._set_hud_enabled(new_visible)

    def _set_hud_enabled(self, enabled: bool) -> None:
        self.settings.hud_enabled = enabled
        self.config_mgr.save()
        if enabled:
            self.hud.show()
        else:
            self.hud.hide()
        self._update_tray_states()
        self.settings_window.refresh_from_settings()

    def _reset_hud_position(self) -> None:
        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            geo = primary_screen.geometry()
            new_x = geo.x() + 60
            new_y = geo.y() + 30
            self.hud.move(new_x, new_y)
            self.settings.hud_x = new_x
            self.settings.hud_y = new_y
            self.config_mgr.save()

    def _toggle_event_deck_visibility(self) -> None:
        new_vis = not self.event_deck.isVisible()
        self._set_event_deck_enabled(new_vis)

    def _set_event_deck_enabled(self, enabled: bool) -> None:
        self.settings.event_deck_enabled = enabled
        self.config_mgr.save()
        if enabled:
            self.event_deck.show()
        else:
            self.event_deck.hide()
        self._update_tray_states()
        self.settings_window.refresh_from_settings()

    def _reset_event_deck_position(self) -> None:
        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            geo = primary_screen.geometry()
            new_x = geo.x() + 60
            new_y = geo.y() + 80
            self.event_deck.move(new_x, new_y)
            self.settings.event_deck_x = new_x
            self.settings.event_deck_y = new_y
            self.config_mgr.save()

    def _toggle_qa_deck_visibility(self) -> None:
        new_vis = not self.qa_deck.isVisible()
        self._set_qa_deck_enabled(new_vis)

    def _set_qa_deck_enabled(self, enabled: bool) -> None:
        self.settings.qa_deck_enabled = enabled
        self.config_mgr.save()
        if enabled:
            self.qa_deck.show()
        else:
            self.qa_deck.hide()
        self._update_tray_states()
        self.settings_window.refresh_from_settings()

    def _reset_qa_deck_position(self) -> None:
        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            geo = primary_screen.geometry()
            new_x = geo.x() + 60
            new_y = geo.y() + 140
            self.qa_deck.move(new_x, new_y)
            self.settings.qa_deck_x = new_x
            self.settings.qa_deck_y = new_y
            self.config_mgr.save()

    def _on_profile_applied(self, profile: GameProfile) -> None:
        """Adapts window geometries and styling when a game profile becomes active."""
        self.overlay.move(profile.overlay_x, profile.overlay_y)
        self.overlay.resize(profile.overlay_width, profile.overlay_height)
        self.settings.overlay_x = profile.overlay_x
        self.settings.overlay_y = profile.overlay_y
        self.settings.overlay_width = profile.overlay_width
        self.settings.overlay_height = profile.overlay_height

        self.hud.move(profile.hud_x, profile.hud_y)
        self.settings.hud_x = profile.hud_x
        self.settings.hud_y = profile.hud_y

        self.event_deck.move(profile.event_deck_x, profile.event_deck_y)
        self.settings.event_deck_x = profile.event_deck_x
        self.settings.event_deck_y = profile.event_deck_y

        if profile.theme_preset and profile.theme_preset != self.settings.theme_preset:
            self.settings.theme_preset = profile.theme_preset
            self.overlay._apply_theme_styling()
            self.hud._apply_theme_styling()
            self.event_deck._apply_theme_styling()

        self.config_mgr.save()
        if getattr(self.settings, "toast_enabled", True):
            self.toast.show_toast(
                title=f"Profile: {profile.name}",
                message=f"Auto-switched layout for {profile.name}",
                icon="🕹️",
                level="info",
            )
        self.settings_window.refresh_from_settings()

    def _save_current_windows_to_profile(self, profile_name: str) -> None:
        """Saves current desktop geometries to the specified profile."""
        prof = self.profile_mgr.get_profile(profile_name)
        if not prof:
            prof = GameProfile(name=profile_name)

        prof.overlay_x = self.overlay.x()
        prof.overlay_y = self.overlay.y()
        prof.overlay_width = self.overlay.width()
        prof.overlay_height = self.overlay.height()

        prof.hud_x = self.hud.x()
        prof.hud_y = self.hud.y()

        prof.event_deck_x = self.event_deck.x()
        prof.event_deck_y = self.event_deck.y()

        prof.theme_preset = self.settings.theme_preset
        self.profile_mgr.add_or_update_profile(prof)
        self.settings.profiles = self.profile_mgr.export_data()
        self.config_mgr.save()

    def _update_tray_states(self) -> None:
        """Synchronizes tray menu check states with all managed windows."""
        self.tray.update_states(
            locked=self.overlay.is_locked(),
            click_through=self.overlay.is_click_through(),
            capture_protected=self.settings.capture_protection,
            hud_visible=self.hud.isVisible(),
            event_deck_visible=self.event_deck.isVisible(),
            qa_deck_visible=self.qa_deck.isVisible() if hasattr(self, "qa_deck") else False,
        )

    def _reconnect_obs(self) -> None:
        self.obs_client.host = getattr(self.settings, "obs_host", "localhost")
        self.obs_client.port = getattr(self.settings, "obs_port", 4455)
        self.obs_client.password = getattr(self.settings, "obs_password", "")
        self.obs_client.connect_obs()

    def _on_hud_mode_changed(self, locked: bool) -> None:
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
            hud_visible=self.hud.isVisible(),
            event_deck_visible=self.event_deck.isVisible(),
            qa_deck_visible=self.qa_deck.isVisible() if hasattr(self, "qa_deck") else False,
        )
        if hasattr(self, "web_companion"):
            self.web_companion.update_status({
                "locked": locked,
                "click_through": self.overlay.is_click_through(),
            })

    def _on_obs_stats_updated(self, stats: OBSStreamStats) -> None:
        """Updates Mini-HUD and triggers in-game toast alerts on state changes."""
        self.hud.update_stats(stats)
        if hasattr(self, "web_companion"):
            self.web_companion.update_status({
                "obs_connected": getattr(self.obs_client, "is_connected", False),
                "obs_streaming": stats.is_live,
                "obs_recording": stats.is_recording,
                "bitrate": stats.kbits_per_sec,
                "fps": stats.fps,
                "dropped_frames": stats.output_skipped_frames,
                "uptime": stats.uptime_formatted,
            })

        if getattr(self.settings, "toast_enabled", True):
            if stats.is_live and not self._prev_is_live:
                self.toast.show_toast("OBS Broadcast", "Stream is now LIVE!", icon="🔴", level="danger")
            elif not stats.is_live and self._prev_is_live:
                self.toast.show_toast("OBS Broadcast", "Stream has ended.", icon="⚪", level="info")

            if stats.is_recording and not self._prev_is_recording:
                self.toast.show_toast("OBS Recording", "Recording started", icon="⏺️", level="danger")
            elif not stats.is_recording and self._prev_is_recording:
                self.toast.show_toast("OBS Recording", "Recording stopped", icon="⏹️", level="info")

            if stats.has_warning and not self._prev_has_warning:
                self.toast.show_toast(
                    "OBS Network Warning",
                    f"Dropped frames detected ({stats.dropped_percent}%)",
                    icon="⚠️",
                    level="warning",
                )

        self._prev_is_live = stats.is_live
        self._prev_is_recording = stats.is_recording
        self._prev_has_warning = stats.has_warning

    def _on_mention_detected(self, username: str, message: str) -> None:
        """Displays an in-game toast whenever the streamer is mentioned in chat."""
        if getattr(self.settings, "toast_enabled", True):
            self.toast.show_toast(
                title=f"Mention from @{username}",
                message=message,
                icon="💬",
                level="mention",
            )

    def _on_settings_updated(self) -> None:
        self.overlay.apply_settings_changes()
        self.hud.apply_layout_mode()
        self.event_deck._apply_theme_styling()
        if hasattr(self, "qa_deck"):
            self.qa_deck._apply_theme_styling()
        if hasattr(self, "clutch_manager"):
            self.clutch_manager.update_settings(self.settings)
        if hasattr(self, "hype_detector"):
            self.hype_detector.settings = self.settings
        if hasattr(self, "qa_deck_mgr"):
            self.qa_deck_mgr.qa_max_items = getattr(self.settings, "qa_max_items", 20)
            self.qa_deck_mgr.qa_auto_expire_seconds = getattr(self.settings, "qa_auto_expire_seconds", 300)
        self._update_tray_states()

    def _on_gsi_toggled(self, enabled: bool) -> None:
        if enabled:
            self.gsi_server.port = getattr(self.settings, "gsi_port", 31337)
            self.gsi_server.auth_token = getattr(self.settings, "gsi_auth_token", "")
            self.gsi_server.start()
        else:
            self.gsi_server.stop()

    def _simulate_clutch_mode(self) -> None:
        if hasattr(self, "clutch_manager"):
            if self.clutch_manager.is_clutch_active:
                self.clutch_manager._disengage_clutch("simulation_ended")
            else:
                self.clutch_manager._engage_clutch("simulation_clutch")
                QTimer.singleShot(
                    4000,
                    lambda: self.clutch_manager._disengage_clutch("simulation_ended")
                    if self.clutch_manager.is_clutch_active
                    else None,
                )

    def _simulate_hype_spike(self) -> None:
        if hasattr(self, "hype_detector"):
            self.hype_detector.simulate_spike(force=True)

    def _on_message_received(self, msg: ChatMessage) -> None:
        self.overlay.add_message(msg)
        if hasattr(self, "web_companion"):
            self.web_companion.broadcast_chat_message(msg)
        if hasattr(self, "qa_deck_mgr"):
            self.qa_deck_mgr.process_message(msg)
        if hasattr(self, "hype_detector"):
            self.hype_detector.process_message(msg)

    def _on_clutch_started(self, reason: str) -> None:
        logger.info("Clutch Mode engaged: %s", reason)
        if getattr(self.settings, "toast_enabled", True):
            self.toast.show_toast(
                title="🛡️ CLUTCH SILENCE",
                message=f"Chat dimmed for focus ({reason.replace('_', ' ')}).",
                icon="🛡️",
                level="warning",
                duration_sec=2.5,
            )

    def _on_clutch_ended(self, reason: str) -> None:
        logger.info("Clutch Mode disengaged: %s", reason)

    def _on_hype_spike(self, event: HypeSpikeEvent) -> None:
        logger.info("Hype spike detected: %.1f msgs/s", event.velocity)
        self.hud.update_hype(event.velocity, is_spike=True)
        if getattr(self.settings, "toast_enabled", True):
            clip_info = " (OBS Auto-Clip Saved!)" if getattr(event, "auto_clipped", False) else ""
            self.toast.show_toast(
                title="🔥 HYPE SPIKE!",
                message=f"Chat velocity reached {event.velocity:.1f} msgs/s!{clip_info}",
                icon="🔥",
                level="hype",
            )

    def _on_companion_action(self, action: str, params: dict) -> None:
        logger.info("Companion Action requested: %s (params: %s)", action, params)
        if action == "toggle_lock":
            self.set_locked_mode(not self.overlay.is_locked())
        elif action == "toggle_clickthrough":
            self._toggle_click_through()
        elif action == "clear_chat":
            self.overlay.clear_chat()
        elif action == "test_alert":
            self._send_demo_message()
        elif action == "obs_toggle_stream":
            if self.obs_client.is_connected:
                self.obs_client.toggle_stream()
            elif getattr(self.settings, "toast_enabled", True):
                self.toast.show_toast("OBS Studio", "OBS Studio is not connected.", icon="📡", level="warning")
        elif action == "obs_toggle_record":
            if self.obs_client.is_connected:
                self.obs_client.toggle_record()
            elif getattr(self.settings, "toast_enabled", True):
                self.toast.show_toast("OBS Studio", "OBS Studio is not connected.", icon="📡", level="warning")
        elif action == "obs_set_scene":
            sc_name = params.get("scene_name", "")
            if sc_name:
                if self.obs_client.is_connected:
                    self.obs_client.set_current_program_scene(sc_name)
                elif getattr(self.settings, "toast_enabled", True):
                    self.toast.show_toast("OBS Studio", "OBS Studio is not connected.", icon="📡", level="warning")

        if hasattr(self, "web_companion"):
            self.web_companion.update_status({
                "locked": self.overlay.is_locked(),
                "click_through": self.overlay.is_click_through(),
                "obs_connected": getattr(self.obs_client, "is_connected", False),
            })

    def _copy_companion_url(self) -> None:
        if hasattr(self, "web_companion"):
            url = self.web_companion.get_url()
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(url)
                if getattr(self.settings, "toast_enabled", True):
                    self.toast.show_toast(
                        title="Mobile Companion",
                        message=f"URL copied: {url}",
                        icon="📱",
                        level="info",
                    )

    def _restart_companion(self) -> None:
        if hasattr(self, "web_companion"):
            self.web_companion.stop()
            self.web_companion.port = getattr(self.settings, "web_companion_port", 8989)
            self.web_companion.pin = getattr(self.settings, "web_companion_pin", "7749")
            if getattr(self.settings, "web_companion_enabled", True):
                self.web_companion.start()

    def _on_chat_status_changed(self, status: str, detail: str) -> None:
        logger.info("Chat Status: %s - %s", status, detail)

    def shutdown(self) -> None:
        logger.info("Initiating graceful application shutdown...")
        if hasattr(self, "web_companion"):
            self.web_companion.stop()
        self.profile_mgr.stop_monitoring()
        self.hotkeys.stop()
        self.obs_client.disconnect_obs()
        self.hud.close()
        self.event_deck.close()
        if hasattr(self, "qa_deck"):
            self.qa_deck.close()
        if hasattr(self, "gsi_server"):
            self.gsi_server.stop()
        if hasattr(self, "hype_detector"):
            self.hype_detector.reset()
        self.toast.close()
        if self.current_provider:
            self.current_provider.disconnect_chat()
        self.config_mgr.save()
        self.qapp.quit()
