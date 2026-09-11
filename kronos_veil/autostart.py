"""Windows Auto-Start Manager for Kronos Veil.

Manages user-level auto-start on Windows boot via the HKCU Run registry key.
Does not require Administrator privileges.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("KronosVeil.AutoStart")

REG_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_APP_NAME = "KronosVeil"


def is_autostart_supported() -> bool:
    """Return True if running on Windows with winreg available."""
    if sys.platform != "win32":
        return False
    try:
        import winreg  # noqa: F401
        return True
    except ImportError:
        return False


def get_application_command(custom_path: str | None = None) -> str:
    """Determine the command line to launch this application on boot."""
    if custom_path:
        return f'"{os.path.abspath(custom_path)}"'

    if getattr(sys, "frozen", False):
        # Compiled via PyInstaller
        return f'"{sys.executable}"'

    # Running from source with python main.py
    main_py = os.path.abspath(sys.argv[0])
    return f'"{sys.executable}" "{main_py}"'


def is_autostart_enabled(app_name: str = DEFAULT_APP_NAME) -> bool:
    """Check if the application is registered in HKCU Run."""
    if not is_autostart_supported():
        return False

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_SUBKEY,
            0,
            winreg.KEY_READ,
        ) as key:
            winreg.QueryValueEx(key, app_name)
            return True
    except (FileNotFoundError, OSError):
        return False
    except Exception as exc:
        logger.warning("Failed to check autostart registry key: %s", exc)
        return False


def set_autostart(
    enabled: bool,
    app_name: str = DEFAULT_APP_NAME,
    custom_path: str | None = None,
) -> bool:
    """Enable or disable auto-start on Windows boot.

    Args:
        enabled: True to register in HKCU Run, False to remove.
        app_name: Registry value name.
        custom_path: Optional explicit executable path.

    Returns:
        True if the operation succeeded, False otherwise.
    """
    if not is_autostart_supported():
        logger.debug("Auto-start is not supported on this platform.")
        return False

    import winreg

    try:
        if enabled:
            cmd = get_application_command(custom_path)
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REG_SUBKEY,
                0,
                winreg.KEY_WRITE,
            ) as key:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            logger.info("Auto-start enabled for %s -> %s", app_name, cmd)
            return True
        else:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REG_SUBKEY,
                0,
                winreg.KEY_WRITE,
            ) as key:
                try:
                    winreg.DeleteValue(key, app_name)
                    logger.info("Auto-start disabled for %s", app_name)
                except FileNotFoundError:
                    # Already removed
                    pass
            return True
    except Exception as exc:
        logger.error("Failed to set autostart (%s): %s", enabled, exc)
        return False
