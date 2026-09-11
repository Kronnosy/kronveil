"""
Unit tests for Mobile LAN Web Companion upgrades in v1.3:
Q&A Deck endpoints, Hype meter, and Clutch Mode telemetry.
"""

import json
import time
import urllib.request
import pytest
from PySide6.QtWidgets import QApplication

from kronos_veil.chat.hype import HypeDetector, HypeSpikeEvent
from kronos_veil.chat.questions import QuestionDeckManager, QuestionItem
from kronos_veil.config import AppSettings
from kronos_veil.gsi.clutch_manager import ClutchManager
from kronos_veil.web.companion import WebCompanionServer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_companion_qa_endpoints_and_status(qapp):
    server = WebCompanionServer(port=18991, pin="7749")
    deck_mgr = QuestionDeckManager()
    hype_detector = HypeDetector()
    clutch_mgr = ClutchManager()

    server.attach_question_deck(deck_mgr)
    server.attach_hype_detector(hype_detector)
    server.attach_clutch_manager(clutch_mgr)

    started = server.start()
    assert started is True
    time.sleep(0.3)

    try:
        # 1. Add question to deck
        q1 = QuestionItem(id="qa-101", author="GamerGuy", text="What mouse sensitivity?", platform="twitch")
        q2 = QuestionItem(id="qa-102", author="StreamSniper", text="Can I play with you?", platform="kick")
        deck_mgr.add_question(q1)
        deck_mgr.add_question(q2)
        qapp.processEvents()

        # 2. Test GET /api/qa
        with urllib.request.urlopen("http://127.0.0.1:18991/api/qa") as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert len(data) == 2
            ids = [item["id"] for item in data]
            assert "qa-101" in ids
            assert "qa-102" in ids

        # 3. Test POST /api/qa: Answer question with wrong PIN -> 401
        req_bad_pin = urllib.request.Request(
            "http://127.0.0.1:18991/api/qa",
            data=json.dumps({"pin": "0000", "action": "answer", "id": "qa-101"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req_bad_pin)
            assert False, "Should fail with 401"
        except urllib.error.HTTPError as err:
            assert err.code == 401

        # 4. Test POST /api/qa: Answer question with valid PIN -> 200
        req_answer = urllib.request.Request(
            "http://127.0.0.1:18991/api/qa",
            data=json.dumps({"pin": "7749", "action": "answer", "id": "qa-101"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_answer) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res["status"] == "ok"
            assert res["success"] is True

        qapp.processEvents()
        assert q1.is_answered is True

        # 5. Test POST /api/qa: Dismiss question with valid PIN
        req_dismiss = urllib.request.Request(
            "http://127.0.0.1:18991/api/qa",
            data=json.dumps({"pin": "7749", "action": "dismiss", "id": "qa-102"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_dismiss) as resp:
            assert resp.status == 200

        qapp.processEvents()
        assert q2.is_dismissed is True

        # 6. Test GET /api/status includes Hype, Clutch, and QA counts
        with urllib.request.urlopen("http://127.0.0.1:18991/api/status") as resp:
            assert resp.status == 200
            st = json.loads(resp.read().decode("utf-8"))
            assert "hype" in st
            assert "clutch" in st
            assert "qa_count" in st
            assert st["version"] == "1.3.0"

        # 7. Test HTML App template serving contains Q&A and Hype elements
        with urllib.request.urlopen("http://127.0.0.1:18991/") as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
            assert "Smart Q&A Deck" in html
            assert "Live Hype Velocity" in html
            assert "CS2 & Clutch State" in html
            assert "loadQAQuestions" in html

        # 8. Test action via POST /api/action: qa_clear
        q3 = QuestionItem(id="qa-103", author="Third", text="Test question?", platform="demo")
        deck_mgr.add_question(q3)
        assert deck_mgr.count() > 0

        req_clear = urllib.request.Request(
            "http://127.0.0.1:18991/api/action",
            data=json.dumps({"pin": "7749", "action": "qa_clear", "params": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req_clear) as resp:
            assert resp.status == 200
        qapp.processEvents()
        assert deck_mgr.count() == 0

    finally:
        server.stop()
        assert server.is_running is False
