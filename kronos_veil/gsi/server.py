"""
CS2 Game State Integration (GSI) HTTP Server.
Receives Valve GSI JSON payloads on a lightweight local endpoint,
parses telemetry, and emits Qt signals and callback notifications.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from kronos_veil.gsi.models import GameState

logger = logging.getLogger("KronosVeil.GSI")


class GsiBridge(QObject):
    """Qt signal bridge for CS2 Game State Integration events."""

    state_updated = Signal(object)  # GameState
    round_phase_changed = Signal(str)  # "freezetime", "live", "over", etc.
    bomb_state_changed = Signal(str)  # "planted", "defused", "exploded", ""
    player_health_changed = Signal(int)  # 0..100
    player_death = Signal()  # emitted when local player dies
    raw_payload_received = Signal(dict)
    server_status_changed = Signal(bool, str)  # (is_running, message_or_url)


class GsiRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Valve GSI JSON POST payloads."""

    server: "GsiHttpServer"

    def handle(self) -> None:
        """Gracefully handle abrupt disconnects without tracebacks."""
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError, OSError) as exc:
            logger.debug("GSI client connection aborted: %s", exc)

    def log_message(self, format: str, *args: Any) -> None:
        """Redirect request logging to debug level to prevent console spam."""
        logger.debug("%s - " + format, self.address_string(), *args)

    def do_GET(self) -> None:
        """Health check endpoint for diagnostic verification."""
        body = json.dumps({
            "service": "Kronos Veil GSI Server",
            "status": "running",
            "port": self.server.gsi_server.port,
            "in_game": self.server.gsi_server.current_state.is_in_game,
        }).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        """Process incoming Valve CS2 Game State Integration JSON payload."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json_response(HTTPStatus.BAD_REQUEST, {"error": "Empty payload"})
            return

        try:
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            logger.warning("Failed to decode GSI JSON payload: %s", exc)
            self._send_json_response(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON"})
            return

        # Optional Auth Token Verification
        expected_token = self.server.gsi_server.auth_token.strip()
        if expected_token:
            auth_obj = payload.get("auth", {}) if isinstance(payload, dict) else {}
            client_token = str(auth_obj.get("token", "")).strip() if isinstance(auth_obj, dict) else ""
            if client_token != expected_token:
                logger.warning("GSI payload rejected: invalid auth token '%s'", client_token)
                self._send_json_response(HTTPStatus.UNAUTHORIZED, {"error": "Invalid auth token"})
                return

        # Parse GameState and notify server
        try:
            game_state = GameState.from_json(payload)
            self.server.gsi_server.process_game_state(game_state, payload)
            self._send_json_response(HTTPStatus.OK, {"status": "ok"})
        except Exception as exc:
            logger.error("Error processing GSI game state: %s", exc, exc_info=True)
            self._send_json_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal processing error"})

    def _send_json_response(self, status: HTTPStatus, data: Dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GsiHttpServer(ThreadingHTTPServer):
    """Threaded HTTP server for CS2 GSI."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], request_handler_class: type[GsiRequestHandler], gsi_server: "GsiServer") -> None:
        self.gsi_server = gsi_server
        super().__init__(server_address, request_handler_class)

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type and issubclass(exc_type, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError)):
            logger.debug("GSI client %s disconnected: %s", client_address, exc_val)
            return
        super().handle_error(request, client_address)


class GsiServer:
    """Manages the background CS2 Game State Integration server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 31337, auth_token: str = "") -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.bridge = GsiBridge()
        self.is_running = False

        self._server: Optional[GsiHttpServer] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._listeners: List[Callable[[GameState], None]] = []

        self.current_state = GameState()
        self._last_phase: str = ""
        self._last_bomb: Optional[str] = None
        self._last_health: int = 100
        self._was_alive: bool = True

    def add_listener(self, callback: Callable[[GameState], None]) -> None:
        """Register a callback invoked whenever a new GameState is received."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[GameState], None]) -> None:
        """Unregister a GameState callback."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def get_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def process_game_state(self, state: GameState, raw_payload: Dict[str, Any]) -> None:
        """Update internal state and emit granular Qt signals & callbacks."""
        prev_health = self._last_health
        prev_phase = self._last_phase
        prev_bomb = self._last_bomb
        prev_alive = self._was_alive

        with self._lock:
            self.current_state = state
            self._last_phase = state.round.phase
            self._last_bomb = state.round.bomb
            self._last_health = state.player.health
            self._was_alive = state.player.is_alive
            listeners_snapshot = list(self._listeners)

        # Emit main state signals
        self.bridge.raw_payload_received.emit(raw_payload)
        self.bridge.state_updated.emit(state)

        # Trigger phase change signal
        if state.round.phase and state.round.phase != prev_phase:
            self.bridge.round_phase_changed.emit(state.round.phase)

        # Trigger bomb state signal
        current_bomb = state.round.bomb or ""
        if current_bomb != (prev_bomb or ""):
            self.bridge.bomb_state_changed.emit(current_bomb)

        # Trigger health change signal
        if state.player.health != prev_health:
            self.bridge.player_health_changed.emit(state.player.health)

        # Trigger player death signal
        if prev_alive and not state.player.is_alive and state.player.activity == "playing":
            self.bridge.player_death.emit()

        # Invoke callback listeners
        for listener in listeners_snapshot:
            try:
                listener(state)
            except Exception as exc:
                logger.error("Error in GSI listener callback: %s", exc)

    def start(self) -> bool:
        """Start the GSI HTTP server on a background daemon thread."""
        if self.is_running:
            logger.info("GSI Server is already running on %s", self.get_url())
            return True

        try:
            self._server = GsiHttpServer((self.host, self.port), GsiRequestHandler, self)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="GSI-Server-Thread")
            self._thread.start()
            self.is_running = True
            logger.info("CS2 GSI Server running on %s", self.get_url())
            self.bridge.server_status_changed.emit(True, self.get_url())
            return True
        except Exception as exc:
            logger.error("Failed to start GSI Server on %s:%d: %s", self.host, self.port, exc)
            self.is_running = False
            self.bridge.server_status_changed.emit(False, str(exc))
            return False

    def stop(self) -> None:
        """Gracefully stop the GSI HTTP server."""
        if not self.is_running or not self._server:
            return

        self.is_running = False
        server = self._server
        self._server = None

        def _shutdown():
            try:
                server.shutdown()
                server.server_close()
            except Exception as exc:
                logger.debug("Error during GSI server shutdown: %s", exc)

        shutdown_thread = threading.Thread(target=_shutdown, daemon=True)
        shutdown_thread.start()
        shutdown_thread.join(timeout=2.0)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

        logger.info("CS2 GSI Server stopped.")
        self.bridge.server_status_changed.emit(False, "Stopped")
