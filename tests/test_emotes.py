"""
Unit tests for Kronos Veil EmoteManager and Badge Formatter.
"""

import html
import pytest
from kronos_veil.chat.emotes import EmoteManager, BADGE_STYLES, POPULAR_EMOTES


def test_emote_manager_singleton():
    mgr1 = EmoteManager.get_instance()
    mgr2 = EmoteManager.get_instance()
    assert mgr1 is mgr2
    assert "KEKW" in mgr1.emotes
    assert "Kappa" in mgr1.emotes


def test_badge_formatting():
    mgr = EmoteManager.get_instance()
    # Test empty
    assert mgr.format_badges_html([]) == ""

    # Test single badge
    html_out = mgr.format_badges_html(["moderator"])
    assert "MOD" in html_out
    assert "#00b06f" in html_out

    # Test multiple badges (e.g. Broadcaster + VIP)
    html_multi = mgr.format_badges_html(["broadcaster", "vip"])
    assert "BROADCASTER" in html_multi
    assert "VIP" in html_multi

    # Test twitch style badge string like subscriber/12
    html_sub = mgr.format_badges_html(["subscriber/12"])
    assert "SUB" in html_sub


def test_message_formatting_emotes_disabled():
    mgr = EmoteManager.get_instance()
    raw = "Hello world <script>alert(1)</script> KEKW"
    out = mgr.format_message_html(raw, emotes_enabled=False)
    # Must escape HTML
    assert "<script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "KEKW" in out


def test_message_formatting_emotes_enabled_uncached():
    mgr = EmoteManager.get_instance()
    raw = "Nice match PogChamp and KEKW"
    out = mgr.format_message_html(raw, emotes_enabled=True)
    # If not yet on disk, it requests download and escapes the text safely
    assert "PogChamp" in out or "<img" in out
    assert "KEKW" in out or "<img" in out


def test_message_formatting_with_cached_emote(tmp_path):
    mgr = EmoteManager.get_instance()
    # Mock a fake cached file in manager's cache directory
    fake_emote_file = mgr.cache_dir / "TESTEMOTE_test.png"
    fake_emote_file.write_bytes(b"dummy image data")

    mgr.register_emote("TESTEMOTE", "https://example.com/test.png")
    # Patch get_cached_path
    original_get = mgr.get_cached_path
    mgr.get_cached_path = lambda name: str(fake_emote_file).replace("\\", "/") if name == "TESTEMOTE" else None

    try:
        out = mgr.format_message_html("Look at this TESTEMOTE right now!", emotes_enabled=True, size_px=24)
        assert "<img src=" in out
        assert "TESTEMOTE_test.png" in out
        assert 'width="24"' in out
        assert 'height="24"' in out
    finally:
        mgr.get_cached_path = original_get
        if fake_emote_file.exists():
            fake_emote_file.unlink()
