"""
Unit tests for OBS WebSocket v5 Client and authentication.
"""

import json
import pytest
from PySide6.QtCore import QCoreApplication
from kronos_veil.obs.client import OBSWebSocketClient, OBSStreamStats, compute_obs_v5_auth


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_compute_obs_v5_auth():
    password = "supersecretpassword"
    salt = "dGVzdHNhbHQ="
    challenge = "dGVzdGNoYWxsZW5nZQ=="
    auth_str = compute_obs_v5_auth(password, salt, challenge)
    assert isinstance(auth_str, str)
    assert len(auth_str) > 0


def test_obs_client_initialization(qapp):
    client = OBSWebSocketClient(host="127.0.0.1", port=4455, password="test")
    assert client.host == "127.0.0.1"
    assert client.port == 4455
    assert not client.stats.is_connected
    assert not client.stats.is_live


def test_obs_stream_status_response_parsing(qapp):
    client = OBSWebSocketClient()
    updated_stats = []
    client.stats_updated.connect(updated_stats.append)

    # Simulate OpCode 7 (RequestResponse) for GetStreamStatus
    response_packet = {
        "op": 7,
        "d": {
            "requestType": "GetStreamStatus",
            "requestId": "req-1",
            "requestStatus": {"result": True, "code": 100},
            "responseData": {
                "outputActive": True,
                "outputTimecode": "01:23:45.678",
                "outputDuration": 5025678,
                "outputKbitsPerSec": 6250,
                "outputSkippedFrames": 12,
                "outputTotalFrames": 10000,
            }
        }
    }

    client._on_message(json.dumps(response_packet))

    assert len(updated_stats) == 1
    stats: OBSStreamStats = updated_stats[0]
    assert stats.is_live is True
    assert stats.uptime == "01:23:45"
    assert stats.bitrate_kbps == 6250
    assert stats.dropped_frames == 12
    assert stats.total_frames == 10000
    assert stats.dropped_percent == 0.12
    assert stats.has_warning is False


def test_obs_dropped_frames_warning_threshold(qapp):
    client = OBSWebSocketClient()
    updated_stats = []
    client.stats_updated.connect(updated_stats.append)

    # Severe frame drops (> 1.0%)
    response_packet = {
        "op": 7,
        "d": {
            "requestType": "GetStreamStatus",
            "requestId": "req-2",
            "requestStatus": {"result": True, "code": 100},
            "responseData": {
                "outputActive": True,
                "outputTimecode": "00:10:00.000",
                "outputKbitsPerSec": 2100,
                "outputSkippedFrames": 250,
                "outputTotalFrames": 5000,  # 5.0% dropped
            }
        }
    }

    client._on_message(json.dumps(response_packet))

    assert len(updated_stats) == 1
    stats: OBSStreamStats = updated_stats[0]
    assert stats.dropped_percent == 5.0
    assert stats.has_warning is True


def test_obs_event_handling(qapp):
    client = OBSWebSocketClient()

    # StreamStateChanged event
    stream_event = {
        "op": 5,
        "d": {
            "eventType": "StreamStateChanged",
            "eventData": {
                "outputActive": True,
                "outputState": "OBS_WEBSOCKET_OUTPUT_STARTED"
            }
        }
    }
    client._on_message(json.dumps(stream_event))
    assert client.stats.is_live is True

    # RecordStateChanged event
    rec_event = {
        "op": 5,
        "d": {
            "eventType": "RecordStateChanged",
            "eventData": {
                "outputActive": True,
                "outputState": "OBS_WEBSOCKET_OUTPUT_STARTED"
            }
        }
    }
    client._on_message(json.dumps(rec_event))
    assert client.stats.is_recording is True


def test_obs_client_commands_and_connection_property(qapp):
    client = OBSWebSocketClient()
    assert client.is_connected is False

    # Calling control methods while disconnected must not raise exceptions
    client.toggle_stream()
    client.toggle_record()
    client.start_stream()
    client.stop_stream()
    client.start_record()
    client.stop_record()
    client.set_current_program_scene("Gameplay Scene")
    client.toggle_virtual_cam()
    client.create_stream_marker("Highlight clip")
    client.save_replay_buffer()

    # Verify compatibility aliases on OBSStreamStats
    stats = OBSStreamStats(bitrate_kbps=6000, dropped_frames=15, uptime="02:15:30", fps=60.0)
    assert stats.kbits_per_sec == 6000
    assert stats.output_skipped_frames == 15
    assert stats.uptime_formatted == "02:15:30"
    assert stats.fps == 60.0


def test_obs_client_stream_marker_and_replay_buffer_connected(qapp, monkeypatch):
    client = OBSWebSocketClient()
    client._ws = True  # Mock active websocket
    client._identified = True
    client.stats.is_connected = True
    sent_requests = []

    def mock_send_request(req_type, req_data=None):
        sent_requests.append((req_type, req_data))

    monkeypatch.setattr(client, "_send_request", mock_send_request)

    # 1. Create stream marker with description
    client.create_stream_marker("Clutch ace 1v3")
    assert len(sent_requests) == 1
    assert sent_requests[0] == ("CreateStreamMarker", {"description": "Clutch ace 1v3"})

    # 2. Create stream marker without description
    client.create_stream_marker()
    assert len(sent_requests) == 2
    assert sent_requests[1] == ("CreateStreamMarker", {})

    # 3. Save replay buffer
    client.save_replay_buffer()
    assert len(sent_requests) == 3
    assert sent_requests[2] == ("SaveReplayBuffer", None)

