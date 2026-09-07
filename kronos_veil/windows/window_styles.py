"""
Windows native extended window style helpers for Kronos Veil.
Implements click-through (WS_EX_TRANSPARENT), tool window behavior (WS_EX_TOOLWINDOW),
non-activating display (WS_EX_NOACTIVATE), and topmost z-ordering (HWND_TOPMOST).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# Win32 Constants
GWL_EXSTYLE: int = -20

# Extended Window Styles
WS_EX_TOPMOST: int = 0x00000008
WS_EX_TRANSPARENT: int = 0x00000020  # Passes mouse clicks through to window underneath
WS_EX_TOOLWINDOW: int = 0x00000080   # Prevents taskbar and Alt+Tab presence
WS_EX_LAYERED: int = 0x00080000      # Layered window, enables transparency and hit-test pass
WS_EX_NOACTIVATE: int = 0x08000000   # Window does not take focus when shown or clicked

# SetWindowPos Constants
HWND_TOPMOST: int = -1
HWND_NOTOPMOST: int = -2
SWP_NOSIZE: int = 0x0001
SWP_NOMOVE: int = 0x0002
SWP_NOACTIVATE: int = 0x0010
SWP_SHOWWINDOW: int = 0x0040
SWP_FRAMECHANGED: int = 0x0020


class WindowStyleManager:
    """Manages low-level Win32 window styles for the overlay window."""

    def __init__(self) -> None:
        self._is_windows: bool = sys.platform == "win32"
        self._get_long_ptr = None
        self._set_long_ptr = None
        self._set_window_pos = None
        self._init_win32_functions()

    def _init_win32_functions(self) -> None:
        if not self._is_windows:
            return

        try:
            user32 = ctypes.windll.user32

            # Determine whether GetWindowLongPtrW or GetWindowLongW should be used (64-bit vs 32-bit)
            if hasattr(user32, "GetWindowLongPtrW"):
                self._get_long_ptr = user32.GetWindowLongPtrW
                self._get_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int]
                self._get_long_ptr.restype = ctypes.c_longlong
            else:
                self._get_long_ptr = user32.GetWindowLongW
                self._get_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int]
                self._get_long_ptr.restype = wintypes.LONG

            if hasattr(user32, "SetWindowLongPtrW"):
                self._set_long_ptr = user32.SetWindowLongPtrW
                self._set_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
                self._set_long_ptr.restype = ctypes.c_longlong
            else:
                self._set_long_ptr = user32.SetWindowLongW
                self._set_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
                self._set_long_ptr.restype = wintypes.LONG

            self._set_window_pos = user32.SetWindowPos
            self._set_window_pos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            self._set_window_pos.restype = wintypes.BOOL
        except Exception as e:
            logger.error("Failed to bind Win32 user32 window style functions: %s", e)

    def get_extended_style(self, hwnd: int) -> Optional[int]:
        """Retrieves the current GWL_EXSTYLE bitmask for the specified window handle."""
        if not self._is_windows or not self._get_long_ptr or not hwnd:
            return None
        try:
            return int(self._get_long_ptr(wintypes.HWND(hwnd), GWL_EXSTYLE))
        except Exception as e:
            logger.error("Failed to get GWL_EXSTYLE for HWND 0x%08X: %s", hwnd, e)
            return None

    def set_extended_style(self, hwnd: int, new_style: int) -> bool:
        """Sets the GWL_EXSTYLE bitmask for the specified window handle."""
        if not self._is_windows or not self._set_long_ptr or not hwnd:
            return False
        try:
            res = self._set_long_ptr(wintypes.HWND(hwnd), GWL_EXSTYLE, new_style)
            # Notify DWM/Windows that window frame/styles changed
            if self._set_window_pos:
                self._set_window_pos(
                    wintypes.HWND(hwnd),
                    wintypes.HWND(0),
                    0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED
                )
            return True
        except Exception as e:
            logger.error("Failed to set GWL_EXSTYLE for HWND 0x%08X: %s", hwnd, e)
            return False

    def configure_overlay_styles(self, hwnd: int) -> bool:
        """
        Applies baseline styles to make the window a floating tool window that stays on top
        and does not appear in the taskbar or steal focus.
        """
        current_style = self.get_extended_style(hwnd)
        if current_style is None:
            return False

        # Add WS_EX_TOOLWINDOW and WS_EX_LAYERED
        new_style = current_style | WS_EX_TOOLWINDOW | WS_EX_LAYERED
        success = self.set_extended_style(hwnd, new_style)
        self.ensure_topmost(hwnd)
        return success

    def set_click_through(self, hwnd: int, enable: bool) -> bool:
        """
        Enables or disables click-through behavior using WS_EX_TRANSPARENT.
        
        When WS_EX_TRANSPARENT is set along with WS_EX_LAYERED, mouse hit-tests pass
        directly through the overlay window to whatever application is behind it.
        """
        current_style = self.get_extended_style(hwnd)
        if current_style is None:
            return False

        if enable:
            new_style = current_style | WS_EX_TRANSPARENT | WS_EX_LAYERED
            logger.info("Enabling click-through on HWND 0x%08X (added WS_EX_TRANSPARENT)", hwnd)
        else:
            new_style = (current_style & ~WS_EX_TRANSPARENT) | WS_EX_LAYERED
            logger.info("Disabling click-through on HWND 0x%08X (removed WS_EX_TRANSPARENT)", hwnd)

        return self.set_extended_style(hwnd, new_style)

    def is_click_through(self, hwnd: int) -> bool:
        """Checks if the WS_EX_TRANSPARENT style flag is currently set on the window."""
        current_style = self.get_extended_style(hwnd)
        if current_style is None:
            return False
        return bool(current_style & WS_EX_TRANSPARENT)

    def ensure_topmost(self, hwnd: int) -> bool:
        """Ensures the window remains topmost without stealing focus."""
        if not self._is_windows or not self._set_window_pos or not hwnd:
            return False
        try:
            return bool(
                self._set_window_pos(
                    wintypes.HWND(hwnd),
                    wintypes.HWND(HWND_TOPMOST),
                    0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
                )
            )
        except Exception as e:
            logger.error("Failed to set HWND_TOPMOST on 0x%08X: %s", hwnd, e)
            return False
