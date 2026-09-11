"""
CS2 Game State Integration (GSI) Configuration Generator and Installer.
Locates Counter-Strike 2 configuration directories via Steam registry & library folders,
and installs or updates gamestate_integration_kronosveil.cfg.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("KronosVeil.GSIInstaller")

CFG_FILENAME = "gamestate_integration_kronosveil.cfg"


def generate_cfg_content(port: int = 31337, auth_token: str = "") -> str:
    """
    Generates the Valve GSI KeyValues format configuration for Kronos Veil.
    Configures heartbeat, throttle, and subscription to player, map, and round data.
    """
    auth_block = ""
    if auth_token.strip():
        auth_block = f"""
    "auth"
    {{
        "token" "{auth_token.strip()}"
    }}"""

    return f""""KronosVeil CS2 Integration"
{{
    "uri" "http://127.0.0.1:{port}"
    "timeout" "5.0"
    "buffer"  "0.1"
    "throttle" "0.1"
    "heartbeat" "15.0"{auth_block}
    "data"
    {{
        "provider"            "1"
        "map"                 "1"
        "round"               "1"
        "player_id"           "1"
        "player_state"        "1"
        "player_weapons"      "1"
        "player_match_stats"  "1"
    }}
}}
"""


def find_steam_install_path() -> Optional[Path]:
    """Detect the root Steam installation directory on Windows or fallback OS."""
    if sys.platform == "win32":
        try:
            import winreg

            # Try HKCU
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                    steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
                    if steam_path and Path(steam_path).exists():
                        return Path(steam_path)
            except Exception:
                pass

            # Try HKLM 64-bit
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
                    install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    if install_path and Path(install_path).exists():
                        return Path(install_path)
            except Exception:
                pass
        except ImportError:
            pass

    # Standard default directory fallbacks
    common_roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
        Path(r"C:\Steam"),
        Path(r"D:\Steam"),
        Path(r"E:\Steam"),
    ]
    for p in common_roots:
        if p.exists():
            return p

    return None


def parse_library_folders(steam_path: Path) -> List[Path]:
    """Parses Steam's libraryfolders.vdf to identify all game library locations."""
    libraries: List[Path] = [steam_path]
    vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.exists():
        return libraries

    try:
        content = vdf_path.read_text(encoding="utf-8", errors="replace")
        # Match lines like: "path" "D:\\SteamLibrary"
        matches = re.findall(r'"path"\s+"([^"]+)"', content, re.IGNORECASE)
        for m in matches:
            norm_path = Path(m.replace(r"\\", os.sep))
            if norm_path.exists() and norm_path not in libraries:
                libraries.append(norm_path)
    except Exception as exc:
        logger.debug("Failed parsing libraryfolders.vdf: %s", exc)

    return libraries


def find_cs2_cfg_directories(custom_steam_path: Optional[Path | str] = None) -> List[Path]:
    """
    Searches all Steam libraries for the Counter-Strike 2 / CS:GO game cfg folder:
    '<library>/steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg'
    """
    found_paths: List[Path] = []
    steam_root = Path(custom_steam_path) if custom_steam_path else find_steam_install_path()
    if not steam_root or not steam_root.exists():
        return found_paths

    libraries = parse_library_folders(steam_root)
    for lib in libraries:
        # CS2 path structure: game/csgo/cfg
        cs2_cfg = lib / "steamapps" / "common" / "Counter-Strike Global Offensive" / "game" / "csgo" / "cfg"
        if cs2_cfg.exists():
            found_paths.append(cs2_cfg)
        else:
            # Check legacy csgo/cfg if game folder doesn't exist
            legacy_cfg = lib / "steamapps" / "common" / "Counter-Strike Global Offensive" / "csgo" / "cfg"
            if legacy_cfg.exists():
                found_paths.append(legacy_cfg)

    return found_paths


def install_cfg(
    target_dir: Optional[Path | str] = None,
    port: int = 31337,
    auth_token: str = "",
) -> Tuple[bool, str]:
    """
    Installs gamestate_integration_kronosveil.cfg to the target directory
    or auto-detected CS2 directories.
    """
    cfg_content = generate_cfg_content(port, auth_token)

    if target_dir:
        dest_dir = Path(target_dir)
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            cfg_file = dest_dir / CFG_FILENAME
            cfg_file.write_text(cfg_content, encoding="utf-8")
            logger.info("Successfully installed GSI config to %s", cfg_file)
            return True, f"Installed to {cfg_file}"
        except Exception as exc:
            logger.error("Failed installing GSI config to %s: %s", dest_dir, exc)
            return False, f"Failed writing config to {dest_dir}: {exc}"

    # Auto-detection
    detected_dirs = find_cs2_cfg_directories()
    if not detected_dirs:
        return False, "Counter-Strike 2 CFG directory not detected. Please specify game folder manually."

    installed_paths: List[Path] = []
    for d in detected_dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            cfg_file = d / CFG_FILENAME
            cfg_file.write_text(cfg_content, encoding="utf-8")
            installed_paths.append(cfg_file)
            logger.info("Installed GSI config to %s", cfg_file)
        except Exception as exc:
            logger.warning("Could not write to %s: %s", d, exc)

    if installed_paths:
        return True, f"Installed to {len(installed_paths)} directory(s): {', '.join(str(p) for p in installed_paths)}"
    return False, "Failed writing GSI config to any detected CS2 directories."


def verify_cfg_installed(target_dir: Optional[Path | str] = None) -> bool:
    """Checks whether gamestate_integration_kronosveil.cfg is present and non-empty."""
    if target_dir:
        cfg_file = Path(target_dir) / CFG_FILENAME
        return cfg_file.exists() and cfg_file.stat().st_size > 0

    detected = find_cs2_cfg_directories()
    for d in detected:
        cfg_file = d / CFG_FILENAME
        if cfg_file.exists() and cfg_file.stat().st_size > 0:
            return True
    return False


def uninstall_cfg(target_dir: Optional[Path | str] = None) -> Tuple[bool, str]:
    """Removes the Kronos Veil GSI config file if present."""
    if target_dir:
        cfg_file = Path(target_dir) / CFG_FILENAME
        if cfg_file.exists():
            try:
                cfg_file.unlink()
                return True, f"Removed {cfg_file}"
            except Exception as exc:
                return False, f"Failed removing {cfg_file}: {exc}"
        return True, "Config file does not exist."

    detected = find_cs2_cfg_directories()
    removed = 0
    for d in detected:
        cfg_file = d / CFG_FILENAME
        if cfg_file.exists():
            try:
                cfg_file.unlink()
                removed += 1
            except Exception:
                pass
    return True, f"Removed config from {removed} location(s)."
