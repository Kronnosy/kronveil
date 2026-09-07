"""Unit tests for Win32 window styles and click-through flags."""

from unittest.mock import MagicMock
import pytest
from kronos_veil.windows.window_styles import (
    WindowStyleManager,
    WS_EX_LAYERED,
    WS_EX_TOOLWINDOW,
    WS_EX_TRANSPARENT,
)


def test_window_styles_click_through_toggle():
    mgr = WindowStyleManager()
    base_style = 0x00000000

    # Mock Get/Set calls
    mgr.get_extended_style = MagicMock(return_value=base_style)
    mgr.set_extended_style = MagicMock(return_value=True)

    # Enable click-through
    res = mgr.set_click_through(9999, enable=True)
    assert res is True
    mgr.set_extended_style.assert_called_with(9999, base_style | WS_EX_TRANSPARENT | WS_EX_LAYERED)

    # Disable click-through
    mgr.get_extended_style.return_value = base_style | WS_EX_TRANSPARENT | WS_EX_LAYERED
    res = mgr.set_click_through(9999, enable=False)
    assert res is True
    mgr.set_extended_style.assert_called_with(9999, base_style | WS_EX_LAYERED)


def test_is_click_through_check():
    mgr = WindowStyleManager()
    mgr.get_extended_style = MagicMock(return_value=WS_EX_TRANSPARENT | WS_EX_LAYERED)
    assert mgr.is_click_through(1234) is True

    mgr.get_extended_style = MagicMock(return_value=WS_EX_LAYERED)
    assert mgr.is_click_through(1234) is False
