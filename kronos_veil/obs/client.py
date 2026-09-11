"""
OBS Studio WebSocket v5 Client for Kronos Veil.
Implements the OBS WebSocket protocol v5 (RPC v1) to query live status,
bitrate, dropped frames, recording state, and stream uptime.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWebSockets import QWebSocket

logger = logging.getLogger(__name__)


@dataclass
class OBSStreamStats:
    """Live streaming metrics retrieved from OBS Studio."""
    is_connected: bool = False
    is_live: bool = False
    is_recording: bool = False
    uptime: str = "00:00:00"
    bitrate_kbps: int = 0
    dropped_frames: int = 0
    total_frames: int = 0
    dropped_percent: float = 0.0
    has_warning: bool = False  # True if dropped frames > 1% or network unstable
    fps: float = 60.0

    @property
    def kbits_per_sec(self) -> int:
        return self.bitrate_kbps

    @property
    def output_skipped_frames(self) -> int:
        return self.dropped_frames

    @property
    def uptime_formatted(self) -> str:
        return self.uptime


def compute_obs_v5_auth(password: str, salt: str, challenge: str) -> str:
    """
    Computes OBS WebSocket v5 challenge authentication response.
    Hash 1: base64(sha256(password + salt))
    Hash 2: base64(sha256(secret + challenge))
    """
    h1 = hashlib.sha256((password + salt).encode("utf-8")).digest()
    secret = base64.b64encode(h1).decode("utf-8")
    h2 = hashlib.sha256((secret + challenge).encode("utf-8")).digest()
    return base64.b64encode(h2).decode("utf-8")


class OBSWebSocketClient(QObject):
    """
    Asynchronous OBS Studio WebSocket client complying with OBS-WebSocket 5.x.
    """

    connection_changed = Signal(bool, str)  # is_connected, status_text
    stats_updated = Signal(OBSStreamStats)

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4455,
        password: str = "",
        poll_interval_ms: int = 1500,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.host = host.strip() or "localhost"
        self.port = port
        self.password = password
        self.poll_interval_ms = poll_interval_ms

        self.stats = OBSStreamStats()
        self._ws: Optional[QWebSocket] = None
        self._identified = False

        # Periodic poller when connected
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self.poll_interval_ms)
        self._poll_timer.timeout.connect(self._poll_status)

    def connect_obs(self) -> None:
        """Initiates connection to OBS WebSocket server."""
        self.disconnect_obs()

        self._ws = QWebSocket()
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_message)
        self._ws.errorOccurred.connect(self._on_error)

        ws_url = f"ws://{self.host}:{self.port}"
        logger.info("Connecting to OBS WebSocket v5 at %s...", ws_url)
        self.connection_changed.emit(False, f"Connecting to OBS ({self.host}:{self.port})...")
        self._ws.open(QUrl(ws_url))

    def disconnect_obs(self) -> None:
        """Closes connection and stops polling."""
        self._poll_timer.stop()
        self._identified = False
        if self._ws:
            self._ws.close()
            self._ws.deleteLater()
            self._ws = None
        self.stats = OBSStreamStats()
        self.connection_changed.emit(False, "Disconnected from OBS.")
        self.stats_updated.emit(self.stats)

    @Slot()
    def _on_connected(self) -> None:
        logger.info("OBS WebSocket connection opened. Awaiting OpCode 0 (Hello)...")

    @Slot()
    def _on_disconnected(self) -> None:
        logger.info("OBS WebSocket disconnected.")
        self._identified = False
        self._poll_timer.stop()
        self.stats.is_connected = False
        self.stats.is_live = False
        self.stats.is_recording = False
        self.connection_changed.emit(False, "Disconnected from OBS.")
        self.stats_updated.emit(self.stats)

    @Slot(object)
    def _on_error(self, error: object) -> None:
        err_str = str(error)
        if "ConnectionRefused" in err_str:
            user_msg = f"Connection refused on {self.host}:{self.port}. Is OBS Studio open with WebSocket enabled?"
        else:
            user_msg = f"OBS Error: {err_str}"
        logger.warning("OBS WebSocket error: %s", err_str)
        self.connection_changed.emit(False, user_msg)

    @Slot(str)
    def _on_message(self, message: str) -> None:
        try:
            packet = json.loads(message)
            op = packet.get("op")
            data = packet.get("d", {})

            # OpCode 0: Hello from OBS Server
            if op == 0:
                self._handle_hello(data)

            # OpCode 2: Identified response from OBS Server
            elif op == 2:
                self._handle_identified(data)

            # OpCode 5: Event emitted by OBS
            elif op == 5:
                self._handle_event(data)

            # OpCode 7: RequestResponse
            elif op == 7:
                self._handle_request_response(data)

        except Exception as exc:
            logger.debug("Error parsing OBS WebSocket message: %s", exc)

    def _handle_hello(self, data: Dict[str, Any]) -> None:
        """Generates OpCode 1 (Identify) with authentication if required."""
        auth_data = data.get("authentication")
        identify_data: Dict[str, Any] = {
            "rpcVersion": 1,
            "eventSubscriptions": 33,  # General (1) + Outputs (32)
        }

        if auth_data:
            challenge = auth_data.get("challenge", "")
            salt = auth_data.get("salt", "")
            auth_hash = compute_obs_v5_auth(self.password, salt, challenge)
            identify_data["authentication"] = auth_hash

        identify_packet = {
            "op": 1,
            "d": identify_data,
        }
        if self._ws:
            self._ws.sendTextMessage(json.dumps(identify_packet))

    def _handle_identified(self, data: Dict[str, Any]) -> None:
        """Authentication succeeded."""
        logger.info("OBS WebSocket Identified successfully.")
        self._identified = True
        self.stats.is_connected = True
        self.connection_changed.emit(True, "Connected to OBS Studio.")
        self._poll_status()
        self._poll_timer.start()

    def _handle_event(self, data: Dict[str, Any]) -> None:
        """Processes OBS broadcast events."""
        event_type = data.get("eventType")
        event_data = data.get("eventData", {})

        if event_type == "StreamStateChanged":
            self.stats.is_live = bool(event_data.get("outputActive", False))
            self.stats_updated.emit(self.stats)
        elif event_type == "RecordStateChanged":
            self.stats.is_recording = bool(event_data.get("outputActive", False))
            self.stats_updated.emit(self.stats)

    def _handle_request_response(self, data: Dict[str, Any]) -> None:
        """Parses output status from GetStreamStatus and GetRecordStatus."""
        req_type = data.get("requestType")
        status = data.get("requestStatus", {})
        resp_data = data.get("responseData", {})

        if status.get("result") is not True:
            return

        if req_type == "GetStreamStatus":
            self.stats.is_live = bool(resp_data.get("outputActive", False))
            self.stats.uptime = resp_data.get("outputTimecode", "00:00:00").split(".")[0]
            self.stats.bitrate_kbps = int(resp_data.get("outputKbitsPerSec", 0))
            self.stats.dropped_frames = int(resp_data.get("outputSkippedFrames", 0))
            self.stats.total_frames = int(resp_data.get("outputTotalFrames", 0))

            if self.stats.total_frames > 0:
                self.stats.dropped_percent = round(
                    (self.stats.dropped_frames / self.stats.total_frames) * 100.0, 2
                )
            else:
                self.stats.dropped_percent = 0.0

            self.stats.has_warning = self.stats.dropped_percent >= 1.0
            self.stats_updated.emit(self.stats)

        elif req_type == "GetRecordStatus":
            self.stats.is_recording = bool(resp_data.get("outputActive", False))
            self.stats_updated.emit(self.stats)

    @Slot()
    def _poll_status(self) -> None:
        """Sends periodic status inquiry packets to OBS."""
        if not self._ws or not self._identified:
            return

        self._send_request("GetStreamStatus")
        self._send_request("GetRecordStatus")

    @property
    def is_connected(self) -> bool:
        """Returns True if the client is connected and identified with OBS Studio."""
        return bool(self._ws and self._identified and self.stats.is_connected)

    def toggle_stream(self) -> None:
        """Toggles OBS streaming state."""
        if not self.is_connected:
            logger.warning("Cannot toggle stream: OBS WebSocket is not connected.")
            return
        self._send_request("ToggleStream")

    def toggle_record(self) -> None:
        """Toggles OBS recording state."""
        if not self.is_connected:
            logger.warning("Cannot toggle recording: OBS WebSocket is not connected.")
            return
        self._send_request("ToggleRecord")

    def start_stream(self) -> None:
        """Starts streaming in OBS."""
        if self.is_connected:
            self._send_request("StartStream")

    def stop_stream(self) -> None:
        """Stops streaming in OBS."""
        if self.is_connected:
            self._send_request("StopStream")

    def start_record(self) -> None:
        """Starts recording in OBS."""
        if self.is_connected:
            self._send_request("StartRecord")

    def stop_record(self) -> None:
        """Stops recording in OBS."""
        if self.is_connected:
            self._send_request("StopRecord")

    def set_current_program_scene(self, scene_name: str) -> None:
        """Switches the active program scene in OBS."""
        if not self.is_connected:
            logger.warning("Cannot switch scene: OBS WebSocket is not connected.")
            return
        self._send_request("SetCurrentProgramScene", {"sceneName": scene_name})

    def toggle_virtual_cam(self) -> None:
        """Toggles OBS virtual camera."""
        if self.is_connected:
            self._send_request("ToggleVirtualCam")

    def create_stream_marker(self, description: str = "") -> None:
        """Creates a stream marker in OBS (e.g. for Twitch or YouTube bookmarking)."""
        if self.is_connected:
            data = {"description": description} if description else {}
            self._send_request("CreateStreamMarker", data)

    def save_replay_buffer(self) -> None:
        """Saves the OBS replay buffer to disk."""
        if self.is_connected:
            self._send_request("SaveReplayBuffer")

    def _send_request(self, request_type: str, request_data: Optional[Dict[str, Any]] = None) -> None:
        if not self._ws:
            return
        packet = {
            "op": 6,
            "d": {
                "requestType": request_type,
                "requestId": str(uuid.uuid4()),
                "requestData": request_data or {},
            },
        }
        self._ws.sendTextMessage(json.dumps(packet))
