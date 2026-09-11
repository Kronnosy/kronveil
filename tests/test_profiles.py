"""
Unit tests for Per-Game Auto-Switching Profiles & ProfileManager.
"""

import pytest
from kronos_veil.profiles import (
    GameProfile,
    ProfileManager,
    detect_foreground_window,
    get_default_preset_profiles,
)


def test_game_profile_matching():
    prof = GameProfile(
        name="Valorant",
        process_names=["valorant-win64-shipping.exe", "valorant.exe"],
        window_titles=["VALORANT"],
    )

    # Process match
    assert prof.matches("VALORANT-Win64-Shipping.exe", "") is True
    assert prof.matches("C:\\Riot Games\\Valorant.exe", "") is True
    assert prof.matches("cs2.exe", "") is False

    # Window title match
    assert prof.matches("unknown.exe", "VALORANT (v10.0)") is True
    assert prof.matches("notepad.exe", "Untitled - Notepad") is False


def test_game_profile_serialization():
    prof = GameProfile(
        name="CustomGame",
        process_names=["custom.exe"],
        overlay_x=200,
        overlay_y=300,
        theme_preset="neon",
    )
    data = prof.to_dict()
    assert data["name"] == "CustomGame"
    assert data["overlay_x"] == 200
    assert data["theme_preset"] == "neon"

    restored = GameProfile.from_dict(data)
    assert restored.name == "CustomGame"
    assert restored.overlay_x == 200
    assert restored.theme_preset == "neon"


def test_profile_manager_operations():
    mgr = ProfileManager()
    assert "Default" in mgr.profiles
    assert "Valorant" in mgr.profiles
    assert "Counter-Strike 2" in mgr.profiles

    # Switch profile
    switched = []
    mgr.profile_applied.connect(lambda p: switched.append(p.name))
    assert mgr.apply_profile("Valorant") is True
    assert mgr.active_profile_name == "Valorant"
    assert "Valorant" in switched

    # Add new profile
    new_prof = GameProfile(name="Apex Legends", process_names=["r5apex.exe"])
    mgr.add_or_update_profile(new_prof)
    assert mgr.get_profile("Apex Legends") is not None

    # Delete custom profile
    assert mgr.delete_profile("Apex Legends") is True
    assert mgr.get_profile("Apex Legends") is None

    # Cannot delete Default
    assert mgr.delete_profile("Default") is False


def test_detect_foreground_window_safe():
    exe, title = detect_foreground_window()
    assert isinstance(exe, str)
    assert isinstance(title, str)
