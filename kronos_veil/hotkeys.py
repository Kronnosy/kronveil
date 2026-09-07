"""
Global Windows hotkey manager for Kronos Veil.
Implements non-invasive native Windows RegisterHotKey in a background message loop
and dispatches Qt signals to ensure seamless recovery even when click-through is active.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys
import threading
from typing import Callable, Dict, Optional, Tuple

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# Win32 Constants
WM_HOTKEY: int = 0x0312
WM_QUIT: int = 0x0012

MOD_ALT: int = 0x0001
MOD_CONTROL: int = 0x0002
MOD_SHIFT: int = 0x0004
MOD_WIN: int = 0x0008
MOD_NOREPEAT: int = 0x4000

# Virtual Key Mapping
VK_MAPPING: Dict[str, int] = {
    **{f"F{i}": 0x70 + (i - 1) for i in range(1, 25)},
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "TAB": 0x09,
    "SPACE": 0x20,
    "RETURN": 0x0D,
    "ENTER": 0x0D,
    "BACKSPACE": 0x08,
    "DELETE": 0x2E,
    "INSERT": 0x2D,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
}


def parse_hotkey_string(hotkey_str: str) -> Optional[Tuple[int, int]]:
    """
    Parses hotkey definitions such as 'Ctrl+Shift+F10' into Win32 (modifiers, vk_code).
    """
    if not hotkey_str:
        return None

    parts = [p.strip().upper() for p in hotkey_str.split("+") if p.strip()]
    if not parts:
        return None

    mods = MOD_NOREPEAT
    vk_code = 0

    for part in parts:
        if part in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif part == "SHIFT":
            mods |= MOD_SHIFT
        elif part == "ALT":
            mods |= MOD_ALT
        elif part in ("WIN", "WINDOWS", "SUPER"):
            mods |= MOD_WIN
        elif part in VK_MAPPING:
            vk_code = VK_MAPPING[part]
        elif len(part) == 1 and (part.isalnum()):
            vk_code = ord(part)
        else:
            logger.warning("Unrecognized hotkey token: %s", part)

    if vk_code == 0:
        logger.error("No valid virtual key code found in hotkey string: %s", hotkey_str)
        return None

    return mods, vk_code


class HotkeyManager(QObject):
    """
    Manages global Windows hotkeys via user32.RegisterHotKey in a background message loop.
    Emits Qt Signal hotkey_pressed(action_id) when any registered combination is pressed.
    """

    hotkey_pressed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._is_windows: bool = sys.platform == "win32"
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._registered_keys: Dict[int, Tuple[str, str, int, int]] = {}  # id -> (action, name, mods, vk)
        self._id_counter: int = 1
        self._ready_event = threading.Event()

    def register_hotkey(self, action_id: str, hotkey_str: str) -> bool:
        """
        Registers a global hotkey configuration for an action (e.g. 'toggle_lock', 'Ctrl+Shift+F10').
        """
        parsed = parse_hotkey_string(hotkey_str)
        if not parsed:
            logger.error("Failed to parse hotkey: %s for action %s", hotkey_str, action_id)
            return False

        mods, vk = parsed
        hotkey_id = self._id_counter
        self._id_counter += 1

        self._registered_keys[hotkey_id] = (action_id, hotkey_str, mods, vk)
        logger.debug("Configured hotkey ID %d: %s -> %s", hotkey_id, action_id, hotkey_str)
        return True

    def start(self) -> None:
        """Starts the background thread hosting the Win32 message queue for hotkeys."""
        if not self._is_windows or not self._registered_keys:
            return

        if self._running:
            return

        self._running = True
        self._ready_event.clear()
        self._thread = threading.Thread(target=self._hotkey_loop, daemon=True, name="KV-HotkeyWorker")
        self._thread.start()
        self._ready_event.wait(timeout=2.0)

    def _hotkey_loop(self) -> None:
        """Native Windows thread procedure handling RegisterHotKey and GetMessage."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()

        # Register configured hotkeys on this thread
        active_ids = []
        for hid, (action_id, name, mods, vk) in self._registered_keys.items():
            success = user32.RegisterHotKey(None, hid, mods, vk)
            if success:
                active_ids.append(hid)
                logger.info("Successfully registered global hotkey: %s (%s)", name, action_id)
            else:
                err = ctypes.GetLastError()
                logger.warning("Failed to register global hotkey %s (%s). Win32 error: %d", name, action_id, err)

        self._ready_event.set()

        msg = wintypes.MSG()
        while self._running:
            # GetMessage blocks until a message arrives for this thread
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res <= 0:  # WM_QUIT or error
                break

            if msg.message == WM_HOTKEY:
                hotkey_id = msg.wParam
                if hotkey_id in self._registered_keys:
                    action_id, name, _, _ = self._registered_keys[hotkey_id]
                    logger.debug("Global hotkey triggered: %s (%s)", name, action_id)
                    # Dispatches cross-thread to Qt Main Thread via Signal
                    self.hotkey_pressed.emit(action_id)

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Unregister all hotkeys on exit
        for hid in active_ids:
            user32.UnregisterHotKey(None, hid)
        logger.debug("Cleaned up registered global hotkeys.")

    def stop(self) -> None:
        """Terminates the background hotkey loop safely."""
        if not self._running:
            return

        self._running = False
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception as e:
                logger.debug("Error posting WM_QUIT to hotkey worker: %s", e)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = None
