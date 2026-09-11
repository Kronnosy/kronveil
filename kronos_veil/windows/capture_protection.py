"""
Windows native capture exclusion integration for Kronos Veil.
Implements SetWindowDisplayAffinity with WDA_EXCLUDEFROMCAPTURE to exclude the overlay
from OBS / Windows Screen Capture (Desktop Duplication API, Graphics Capture API, Window Capture).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from enum import Enum
import logging
import sys
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Windows Display Affinity Constants
# Introduced in Windows 7 (WDA_MONITOR) and Windows 10 2004 / 20H1 Build 19041 (WDA_EXCLUDEFROMCAPTURE)
WDA_NONE: int = 0x00000000
WDA_MONITOR: int = 0x00000001
WDA_EXCLUDEFROMCAPTURE: int = 0x00000011


class CaptureProtectionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class CaptureProtectionManager:
    """
    Manages native Windows capture exclusion on overlay windows using SetWindowDisplayAffinity.
    
    WDA_EXCLUDEFROMCAPTURE (0x00000011):
    Instructs the Desktop Window Manager (DWM) to render the window on the display
    monitor only, removing it completely from screen capture and recording outputs
    generated via Windows Graphics Capture, Desktop Duplication, or Window Capture in OBS.
    """

    def __init__(self) -> None:
        self.status: CaptureProtectionStatus = CaptureProtectionStatus.DISABLED
        self.last_error_code: int = 0
        self.last_error_message: str = "Capture protection not initialized"
        self._is_windows: bool = sys.platform == "win32"
        self._set_affinity_func = None
        self._get_affinity_func = None
        self._init_win32_functions()

    def _init_win32_functions(self) -> None:
        """Initializes Win32 API ctypes function prototypes."""
        if not self._is_windows:
            self.status = CaptureProtectionStatus.UNSUPPORTED
            self.last_error_message = "Non-Windows platform detected."
            return

        try:
            user32 = ctypes.windll.user32

            if hasattr(user32, "SetWindowDisplayAffinity"):
                self._set_affinity_func = user32.SetWindowDisplayAffinity
                self._set_affinity_func.argtypes = [wintypes.HWND, wintypes.DWORD]
                self._set_affinity_func.restype = wintypes.BOOL
            else:
                logger.warning("user32.SetWindowDisplayAffinity is not exported on this system.")

            if hasattr(user32, "GetWindowDisplayAffinity"):
                self._get_affinity_func = user32.GetWindowDisplayAffinity
                self._get_affinity_func.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
                self._get_affinity_func.restype = wintypes.BOOL
        except Exception as e:
            logger.error("Failed to bind user32 display affinity functions: %s", e)
            self._set_affinity_func = None
            self._get_affinity_func = None

    def is_os_supported(self) -> bool:
        """Checks if current Windows build meets minimum requirements (Build 19041+ for WDA_EXCLUDEFROMCAPTURE)."""
        if not self._is_windows:
            return False
        try:
            win_ver = sys.getwindowsversion()
            # Windows 10 Version 2004 (20H1) is build 19041
            return win_ver.major >= 10 and getattr(win_ver, "build", 0) >= 19041
        except Exception:
            return True  # Attempt call if version cannot be retrieved

    def get_affinity(self, hwnd: int) -> Optional[int]:
        """Queries the current display affinity of a native window."""
        if not self._get_affinity_func or not hwnd:
            return None
        try:
            affinity = wintypes.DWORD()
            success = self._get_affinity_func(wintypes.HWND(hwnd), ctypes.byref(affinity))
            if success:
                return affinity.value
            return None
        except Exception as e:
            logger.error("Error calling GetWindowDisplayAffinity for HWND %s: %s", hwnd, e)
            return None

    def set_protection(self, hwnd: int, enable: bool = True) -> Tuple[CaptureProtectionStatus, str]:
        """
        Applies or removes WDA_EXCLUDEFROMCAPTURE on the specified native HWND.
        
        Returns:
            Tuple of (CaptureProtectionStatus, detail_message)
        """
        if not self._is_windows or not self._set_affinity_func:
            self.status = CaptureProtectionStatus.UNSUPPORTED
            self.last_error_message = "Windows Display Affinity API is not available on this platform."
            return self.status, self.last_error_message

        if not hwnd or hwnd <= 0:
            self.status = CaptureProtectionStatus.FAILED
            self.last_error_code = 1400  # ERROR_INVALID_WINDOW_HANDLE
            self.last_error_message = f"Invalid window handle (HWND={hwnd})."
            logger.error(self.last_error_message)
            return self.status, self.last_error_message

        if not enable:
            # Revert to standard display capture (WDA_NONE)
            success = self._set_affinity_func(wintypes.HWND(hwnd), WDA_NONE)
            if success:
                self.status = CaptureProtectionStatus.DISABLED
                self.last_error_code = 0
                self.last_error_message = "Capture protection disabled by user."
                logger.info("Capture protection disabled on HWND 0x%08X", hwnd)
            else:
                self.last_error_code = ctypes.GetLastError()
                self.status = CaptureProtectionStatus.FAILED
                self.last_error_message = f"Failed to remove capture protection (Win32 error: {self.last_error_code})"
                logger.error(self.last_error_message)
            return self.status, self.last_error_message

        # Check OS build support
        if not self.is_os_supported():
            logger.warning(
                "Windows build is older than 19041. WDA_EXCLUDEFROMCAPTURE may not be supported by DWM."
            )

        # Attempt to set WDA_EXCLUDEFROMCAPTURE (0x00000011)
        target_affinity = WDA_EXCLUDEFROMCAPTURE
        success = self._set_affinity_func(wintypes.HWND(hwnd), target_affinity)

        if success:
            # Double check via GetWindowDisplayAffinity
            current = self.get_affinity(hwnd)
            if current == target_affinity:
                self.status = CaptureProtectionStatus.ACTIVE
                self.last_error_code = 0
                self.last_error_message = "Capture protection active (WDA_EXCLUDEFROMCAPTURE: 0x00000011)."
                logger.info(
                    "Capture protection successfully enabled on HWND 0x%08X (Affinity: 0x%02X)",
                    hwnd, current
                )
                return self.status, self.last_error_message
            else:
                # API returned success, but affinity didn't match
                self.status = CaptureProtectionStatus.ACTIVE
                self.last_error_message = f"Applied affinity, verified value: 0x{current or 0:02X}"
                return self.status, self.last_error_message

        # If SetWindowDisplayAffinity failed, analyze GetLastError
        self.last_error_code = ctypes.GetLastError()
        logger.error(
            "SetWindowDisplayAffinity failed on HWND 0x%08X with Win32 error %d",
            hwnd, self.last_error_code
        )

        # Common error codes:
        # 87 = ERROR_INVALID_PARAMETER (indicates 0x11 unsupported on this OS)
        # 50 = ERROR_NOT_SUPPORTED
        # 5  = ERROR_ACCESS_DENIED
        if self.last_error_code in (87, 50):
            self.status = CaptureProtectionStatus.UNSUPPORTED
            self.last_error_message = (
                f"Capture exclusion (0x11) unsupported by current OS/DWM (Win32 error {self.last_error_code}). "
                "Requires Windows 10 Version 2004 (Build 19041) or Windows 11."
            )
        else:
            self.status = CaptureProtectionStatus.FAILED
            self.last_error_message = (
                f"SetWindowDisplayAffinity call failed with Win32 error code {self.last_error_code}."
            )

        return self.status, self.last_error_message

    # Compatibility alias
    apply_capture_protection = set_protection
