"""Tests for Mobile LAN Web Companion server and QR Code generation."""

import json
import time
import urllib.request

from kronos_veil.chat.base import ChatMessage
from kronos_veil.web.companion import WebCompanionServer, get_local_lan_ip
from kronos_veil.web.qr import generate_qr_matrix, generate_qr_svg


def test_qr_code_generation():
    url = "http://192.168.1.50:8989"
    matrix = generate_qr_matrix(url)
    assert len(matrix) == 29
    assert len(matrix[0]) == 29

    svg = generate_qr_svg(url)
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "rect" in svg


def test_local_lan_ip_detection():
    ip = get_local_lan_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0


def test_web_companion_server_lifecycle_and_endpoints(qapp):
    server = WebCompanionServer(port=18989, pin="1234")
    started = server.start()
    assert started is True
    assert server.is_running is True

    time.sleep(0.3)

    try:
        # Test GET / (HTML App)
        with urllib.request.urlopen("http://127.0.0.1:18989/") as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "\u2726 KRONOS VEIL" in content

        # Test GET /api/status
        with urllib.request.urlopen("http://127.0.0.1:18989/api/status") as resp:
            assert resp.status == 200
            status_data = json.loads(resp.read().decode("utf-8"))
            assert "locked" in status_data
            assert status_data["pin_required"] is True

        # Test POST /api/action without or invalid PIN -> 401
        req_bad = urllib.request.Request(
            "http://127.0.0.1:18989/api/action",
            data=json.dumps({"action": "toggle_lock", "pin": "0000"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req_bad)
            assert False, "Should have returned 401"
        except urllib.error.HTTPError as err:
            assert err.code == 401

        # Test POST /api/action with valid PIN -> 200
        dispatched_actions = []
        server.bridge.action_requested.connect(lambda act, par: dispatched_actions.append((act, par)))

        req_good = urllib.request.Request(
            "http://127.0.0.1:18989/api/action",
            data=json.dumps({"action": "toggle_lock", "pin": "1234"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_good) as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode("utf-8"))
            assert body["status"] == "ok"

        # Allow Qt cross-thread queued signal delivery
        qapp.processEvents()
        time.sleep(0.1)
        qapp.processEvents()

        assert len(dispatched_actions) == 1
        assert dispatched_actions[0][0] == "toggle_lock"

        # Test broadcast_chat_message
        test_msg = ChatMessage(username="CompanionUser", message="Testing companion chat!", platform="twitch")
        server.broadcast_chat_message(test_msg)

    finally:
        server.stop()
        assert server.is_running is False


def test_companion_server_error_suppression(monkeypatch):
    import sys
    from kronos_veil.web.companion import CompanionHttpServer, WebCompanionServer, CompanionRequestHandler

    comp = WebCompanionServer(port=8998)
    server = CompanionHttpServer(("127.0.0.1", 0), CompanionRequestHandler, comp)
    try:
        # Simulate ConnectionAbortedError in sys.exc_info()
        monkeypatch.setattr(sys, "exc_info", lambda: (ConnectionAbortedError, ConnectionAbortedError("WinError 10053"), None))
        # Must return cleanly without raising or calling super().handle_error
        server.handle_error(None, ("127.0.0.1", 12345))
    finally:
        server.server_close()
