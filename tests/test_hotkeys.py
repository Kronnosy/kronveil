"""Unit tests for hotkey parsing and modifier translation."""

import pytest
from kronos_veil.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    parse_hotkey_string,
)


def test_parse_default_hotkey():
    parsed = parse_hotkey_string("Ctrl+Shift+F10")
    assert parsed is not None
    mods, vk = parsed
    assert mods == (MOD_NOREPEAT | MOD_CONTROL | MOD_SHIFT)
    assert vk == 0x79  # VK_F10 (0x70 + 9)


def test_parse_alt_shift_key():
    parsed = parse_hotkey_string("Alt+Shift+F11")
    assert parsed is not None
    mods, vk = parsed
    assert mods == (MOD_NOREPEAT | MOD_ALT | MOD_SHIFT)
    assert vk == 0x7A  # VK_F11 (0x70 + 10)


def test_parse_invalid_hotkey():
    assert parse_hotkey_string("") is None
    assert parse_hotkey_string("JustCtrlOnly+") is None
