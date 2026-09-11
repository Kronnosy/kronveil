"""Mobile LAN Web Companion & Touch Stream Deck Server for Kronos Veil.

Provides a zero-dependency local HTTP and Server-Sent Events (SSE) server.
Allows streamers to use any smartphone, tablet, or secondary device on their local Wi-Fi
as a touch-screen Stream Deck, telemetry monitor, and live chat viewer.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import socket
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, Signal

from kronos_veil.chat.base import ChatMessage

logger = logging.getLogger("KronosVeil.WebCompanion")


def get_local_lan_ip() -> str:
    """Detect local LAN IPv4 address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to public DNS to determine default route outbound interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class WebCompanionBridge(QObject):
    """Thread-safe Qt bridge for routing companion web actions to the main application."""

    action_requested = Signal(str, dict)  # action_name, params


class CompanionRequestHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests and Server-Sent Events (SSE) streams."""

    server: "CompanionHttpServer"  # type hint for parent server

    def handle(self) -> None:
        """Handle incoming requests with graceful suppression of abrupt client disconnects."""
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError, OSError) as exc:
            logger.debug("Companion client connection aborted: %s", exc)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stdout access logs to keep terminal clean."""
        logger.debug("%s - " + format, self.address_string(), *args)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path in ("/", "/index.html"):
            self._serve_web_app()
        elif path == "/api/status":
            self._serve_status()
        elif path == "/api/events":
            self._serve_sse_stream()
        elif path == "/api/qa":
            self._serve_qa()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/action":
            self._handle_action()
        elif path == "/api/qa":
            self._handle_qa_action()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _serve_web_app(self) -> None:
        """Serves the mobile-optimized single-page application."""
        html_content = self.server.companion_server.get_html_content()
        body = html_content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_status(self) -> None:
        """Returns JSON status snapshot."""
        status_data = self.server.companion_server.get_status_snapshot()
        body = json.dumps(status_data).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _serve_qa(self) -> None:
        """Returns JSON list of active Q&A questions."""
        qa_data = self.server.companion_server.get_qa_items()
        body = json.dumps(qa_data).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _handle_action(self) -> None:
        """Executes a streamer control action from the mobile web app."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception as exc:
            self._send_json_response(HTTPStatus.BAD_REQUEST, {"error": f"Invalid JSON: {exc}"})
            return

        # Validate PIN
        configured_pin = self.server.companion_server.pin.strip()
        client_pin = str(payload.get("pin", "")).strip()

        if configured_pin and client_pin != configured_pin:
            self._send_json_response(HTTPStatus.UNAUTHORIZED, {"error": "Invalid companion PIN"})
            return

        action = payload.get("action", "")
        params = payload.get("params", {})

        if not action:
            self._send_json_response(HTTPStatus.BAD_REQUEST, {"error": "Missing action"})
            return

        # Check for QA actions triggered via /api/action
        if action in ("qa_answer", "answer_question"):
            self.server.companion_server.execute_qa_action("answer", params.get("id", ""))
        elif action in ("qa_dismiss", "dismiss_question"):
            self.server.companion_server.execute_qa_action("dismiss", params.get("id", ""))
        elif action in ("qa_clear", "clear_qa"):
            self.server.companion_server.execute_qa_action("clear", "")

        # Emit action via Qt bridge to main thread
        self.server.companion_server.bridge.action_requested.emit(action, params)
        self._send_json_response(HTTPStatus.OK, {"status": "ok", "action": action})

    def _handle_qa_action(self) -> None:
        """Handles question answering and dismissal from mobile companion."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception as exc:
            self._send_json_response(HTTPStatus.BAD_REQUEST, {"error": f"Invalid JSON: {exc}"})
            return

        configured_pin = self.server.companion_server.pin.strip()
        client_pin = str(payload.get("pin", "")).strip()

        if configured_pin and client_pin != configured_pin:
            self._send_json_response(HTTPStatus.UNAUTHORIZED, {"error": "Invalid companion PIN"})
            return

        action = str(payload.get("action", "")).strip().lower()
        q_id = str(payload.get("id", "")).strip()

        if not action:
            self._send_json_response(HTTPStatus.BAD_REQUEST, {"error": "Missing QA action"})
            return

        success = self.server.companion_server.execute_qa_action(action, q_id)
        self._send_json_response(HTTPStatus.OK, {"status": "ok", "action": action, "id": q_id, "success": success})

    def _serve_sse_stream(self) -> None:
        """Maintains a persistent Server-Sent Events stream for real-time mobile updates."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._send_cors_headers()
        self.end_headers()

        client_queue: queue.Queue = queue.Queue(maxsize=100)
        self.server.companion_server.register_sse_client(client_queue)

        # Send initial status
        initial_status = self.server.companion_server.get_status_snapshot()
        self._write_sse_event("status", initial_status)

        try:
            while self.server.companion_server.is_running:
                try:
                    event_type, event_data = client_queue.get(timeout=1.0)
                    self._write_sse_event(event_type, event_data)
                except queue.Empty:
                    # Keep-alive heartbeat comment
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            logger.debug("SSE client disconnected.")
        finally:
            self.server.companion_server.unregister_sse_client(client_queue)

    def _write_sse_event(self, event_type: str, data: Any) -> None:
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
        self.wfile.write(payload)
        self.wfile.flush()

    def _send_json_response(self, status: HTTPStatus, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)


class CompanionHttpServer(ThreadingHTTPServer):
    """Custom ThreadingHTTPServer keeping a reference to the CompanionServer orchestrator."""

    def __init__(self, server_address: tuple, request_handler_class: type, companion_server: "WebCompanionServer"):
        self.companion_server = companion_server
        self.daemon_threads = True
        super().__init__(server_address, request_handler_class)

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Gracefully handle client disconnects (ConnectionAbortedError/ConnectionResetError) without dumping tracebacks."""
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type and issubclass(exc_type, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError)):
            logger.debug("Companion client %s disconnected: %s", client_address, exc_val)
            return
        super().handle_error(request, client_address)


class WebCompanionServer:
    """Manages the background HTTP / SSE server for the mobile web companion."""

    def __init__(self, port: int = 8989, pin: str = "7749") -> None:
        self.port = port
        self.pin = pin
        self.bridge = WebCompanionBridge()
        self.is_running = False

        self._server: Optional[CompanionHttpServer] = None
        self._thread: Optional[threading.Thread] = None
        self._sse_clients: Set[queue.Queue] = set()
        self._clients_lock = threading.Lock()

        # Cached latest state for quick sync
        self._status_cache: Dict[str, Any] = {
            "locked": False,
            "click_through": False,
            "obs_connected": False,
            "obs_streaming": False,
            "obs_recording": False,
            "bitrate": 0,
            "fps": 0.0,
            "dropped_frames": 0,
            "uptime": "00:00:00",
            "scenes": [],
            "current_scene": "",
            "pin_required": bool(self.pin.strip()),
            "version": "1.3.0",
            "hype": {
                "velocity": 0.0,
                "threshold": 3.5,
                "is_spike": False,
                "is_cooldown": False,
            },
            "clutch": {
                "state": "idle",
                "is_active": False,
                "reason": "",
                "bomb": "",
            },
            "qa_count": 0,
        }

        self.deck_mgr: Optional[Any] = None
        self.hype_detector: Optional[Any] = None
        self.clutch_manager: Optional[Any] = None

    def start(self) -> bool:
        """Start the companion HTTP server in a background daemon thread."""
        if self.is_running:
            return True

        try:
            self._server = CompanionHttpServer(("0.0.0.0", self.port), CompanionRequestHandler, self)
            self.is_running = True
            self._thread = threading.Thread(target=self._run_server, name="KronosVeil-WebCompanion", daemon=True)
            self._thread.start()
            logger.info("Web Companion Server started on http://%s:%d (PIN: %s)", self.get_lan_ip(), self.port, self.pin)
            return True
        except Exception as exc:
            logger.error("Failed to start Web Companion Server on port %d: %s", self.port, exc)
            self.is_running = False
            return False

    def _run_server(self) -> None:
        if self._server:
            try:
                self._server.serve_forever()
            except Exception as exc:
                logger.debug("Companion server shut down: %s", exc)

    def stop(self) -> None:
        """Stop the companion server and disconnect all clients."""
        self.is_running = False
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception as exc:
                logger.debug("Error stopping server: %s", exc)
            self._server = None

        with self._clients_lock:
            self._sse_clients.clear()
        logger.info("Web Companion Server stopped.")

    def get_lan_ip(self) -> str:
        return get_local_lan_ip()

    def get_url(self) -> str:
        return f"http://{self.get_lan_ip()}:{self.port}"

    def update_status(self, updates: Dict[str, Any]) -> None:
        """Update cached status and push telemetry update to connected mobile devices."""
        self._status_cache.update(updates)
        self._status_cache["pin_required"] = bool(self.pin.strip())
        self.broadcast_event("status", self._status_cache)

    def get_status_snapshot(self) -> Dict[str, Any]:
        return dict(self._status_cache)

    def register_sse_client(self, q: queue.Queue) -> None:
        with self._clients_lock:
            self._sse_clients.add(q)

    def unregister_sse_client(self, q: queue.Queue) -> None:
        with self._clients_lock:
            self._sse_clients.discard(q)

    def broadcast_event(self, event_type: str, data: Any) -> None:
        """Dispatch an SSE event to all connected clients."""
        with self._clients_lock:
            dead_queues = []
            for q in self._sse_clients:
                try:
                    q.put_nowait((event_type, data))
                except queue.Full:
                    dead_queues.append(q)
            for dq in dead_queues:
                self._sse_clients.discard(dq)

    def broadcast_chat_message(self, msg: ChatMessage) -> None:
        """Send new chat message to all connected companion devices."""
        data = {
            "id": msg.id,
            "username": msg.username,
            "message": msg.message,
            "timestamp": msg.timestamp,
            "color": msg.color,
            "badges": msg.badges,
            "platform": getattr(msg, "platform", "demo"),
            "is_system": msg.is_system,
        }
        self.broadcast_event("chat", data)

    def attach_question_deck(self, deck_mgr: Any) -> None:
        """Connects QuestionDeckManager signals to companion server."""
        self.deck_mgr = deck_mgr
        deck_mgr.question_added.connect(self._on_qa_updated)
        deck_mgr.question_updated.connect(self._on_qa_updated)
        deck_mgr.question_removed.connect(lambda _: self._on_qa_updated())
        deck_mgr.deck_cleared.connect(self._on_qa_updated)
        self._on_qa_updated()

    def attach_hype_detector(self, hype_detector: Any) -> None:
        """Connects HypeDetector signals to companion server."""
        self.hype_detector = hype_detector
        hype_detector.velocity_updated.connect(self._on_hype_velocity_updated)
        hype_detector.hype_spike_detected.connect(self._on_hype_spike_detected)

    def attach_clutch_manager(self, clutch_manager: Any) -> None:
        """Connects ClutchManager signals to companion server."""
        self.clutch_manager = clutch_manager
        clutch_manager.state_changed.connect(self._on_clutch_state_changed)
        clutch_manager.bomb_state_changed.connect(self._on_clutch_bomb_changed)

    def _on_qa_updated(self, *args: Any) -> None:
        items = self.get_qa_items()
        self._status_cache["qa_count"] = len([q for q in items if not q.get("is_answered") and not q.get("is_dismissed")])
        self.broadcast_event("qa", {"questions": items})
        self.broadcast_event("qa_update", {"questions": items})

    def _on_hype_velocity_updated(self, velocity: float) -> None:
        thresh = getattr(self.hype_detector, "threshold", 3.5) if self.hype_detector else 3.5
        cooldown = getattr(self.hype_detector, "is_on_cooldown", False) if self.hype_detector else False
        payload = {
            "velocity": round(velocity, 2),
            "threshold": thresh,
            "is_spike": velocity >= thresh,
            "is_cooldown": cooldown,
        }
        self._status_cache["hype"] = payload
        self.broadcast_event("hype", payload)

    def _on_hype_spike_detected(self, event: Any) -> None:
        payload = {
            "velocity": round(getattr(event, "velocity", 0.0), 2),
            "threshold": getattr(event, "threshold", 3.5),
            "message_count": getattr(event, "message_count", 0),
            "window_seconds": getattr(event, "window_seconds", 15),
            "is_spike": True,
            "is_cooldown": True,
        }
        self._status_cache["hype"] = payload
        self.broadcast_event("hype", payload)

    def _on_clutch_state_changed(self, state: str) -> None:
        is_active = (state.lower() == "clutch")
        reason = getattr(self.clutch_manager, "active_reason", "") if self.clutch_manager else ""
        bomb = getattr(self.clutch_manager, "_last_bomb_state", "") if self.clutch_manager else ""
        payload = {
            "state": state,
            "is_active": is_active,
            "reason": reason,
            "bomb": bomb,
        }
        self._status_cache["clutch"] = payload
        self.broadcast_event("clutch", payload)

    def _on_clutch_bomb_changed(self, bomb_state: str) -> None:
        if "clutch" in self._status_cache:
            self._status_cache["clutch"]["bomb"] = bomb_state
        self.broadcast_event("clutch", self._status_cache.get("clutch", {}))

    def get_qa_items(self) -> List[Dict[str, Any]]:
        """Returns JSON-serializable list of questions from attached QuestionDeckManager."""
        if self.deck_mgr:
            questions = self.deck_mgr.get_active_questions(include_answered=True, include_dismissed=False)
            return [q.to_dict() if hasattr(q, "to_dict") else vars(q) for q in questions]
        return []

    def execute_qa_action(self, action: str, q_id: str) -> bool:
        """Executes answer, dismiss, or clear on QuestionDeckManager or emits bridge signal."""
        act_lower = action.lower()
        if self.deck_mgr:
            if act_lower in ("answer", "answered"):
                res = bool(self.deck_mgr.mark_answered(q_id))
                self._on_qa_updated()
                return res
            elif act_lower in ("dismiss", "dismissed"):
                res = bool(self.deck_mgr.dismiss_question(q_id))
                self._on_qa_updated()
                return res
            elif act_lower == "clear":
                self.deck_mgr.clear()
                self._on_qa_updated()
                return True
        self.bridge.action_requested.emit(f"qa_{act_lower}", {"id": q_id})
        return True

    def get_html_content(self) -> str:
        """Returns the single-page responsive mobile web companion application."""
        template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
        if os.path.isfile(template_path):
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as exc:
                logger.debug("Failed reading template file: %s", exc)
        return EMBEDDED_WEB_APP_HTML


_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")
_loaded_template = None
if os.path.isfile(_TEMPLATE_PATH):
    try:
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as _f:
            _loaded_template = _f.read()
    except Exception:
        pass

EMBEDDED_WEB_APP_HTML = _loaded_template or """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Kronos Veil Companion</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(22, 27, 44, 0.85);
      --card-border: rgba(0, 229, 255, 0.2);
      --accent: #00e5ff;
      --accent-glow: rgba(0, 229, 255, 0.35);
      --text: #f0f6fc;
      --text-muted: #8b949e;
      --danger: #ff4757;
      --warning: #ffa502;
      --success: #2ed573;
      --twitch: #9146ff;
      --kick: #53fc18;
      --yt: #ff0000;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      user-select: none;
      overflow-x: hidden;
    }
    header {
      background: rgba(11, 15, 25, 0.95);
      backdrop-filter: blur(12px);
      padding: 12px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--card-border);
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 1rem;
      font-weight: 800;
      color: var(--accent);
      letter-spacing: 0.5px;
    }
    .status-pill {
      font-size: 0.75rem;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 12px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: rgba(255, 255, 255, 0.08);
    }
    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--text-muted);
    }
    .status-dot.online { background: var(--success); box-shadow: 0 0 6px var(--success); }
    .nav-tabs {
      display: flex;
      background: rgba(16, 21, 35, 0.9);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .nav-tab {
      flex: 1;
      padding: 12px 8px;
      text-align: center;
      font-weight: 700;
      font-size: 0.85rem;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s;
    }
    .nav-tab.active {
      color: var(--accent);
      border-bottom: 2px solid var(--accent);
      background: rgba(0, 229, 255, 0.05);
    }
    main {
      flex: 1;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .tab-content { display: none; }
    .tab-content.active { display: flex; flex-direction: column; gap: 14px; }
    
    /* Deck Grid */
    .deck-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }
    .deck-btn {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 18px 12px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 8px;
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--text);
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      transition: transform 0.1s, background 0.2s, border-color 0.2s;
    }
    .deck-btn:active {
      transform: scale(0.96);
    }
    .deck-btn .btn-icon { font-size: 1.8rem; }
    .deck-btn .btn-sub { font-size: 0.72rem; color: var(--text-muted); font-weight: 500; }
    .deck-btn.active {
      border-color: var(--accent);
      background: rgba(0, 229, 255, 0.15);
      box-shadow: 0 0 16px var(--accent-glow);
    }
    .deck-btn.live {
      border-color: var(--danger);
      background: rgba(255, 71, 87, 0.18);
    }

    /* Telemetry Cards */
    .stats-row {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 12px;
    }
    .stat-title { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 700; }
    .stat-value { font-size: 1.25rem; font-weight: 800; color: var(--accent); margin-top: 4px; }
    
    /* Live Chat Container */
    #chat-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      height: calc(100vh - 160px);
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .chat-row {
      font-size: 0.88rem;
      line-height: 1.35;
      word-break: break-word;
      padding: 6px 8px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.03);
    }
    .plat-badge {
      font-size: 0.65rem;
      font-weight: 800;
      padding: 1px 4px;
      border-radius: 3px;
      margin-right: 4px;
      vertical-align: middle;
    }
    .plat-twitch { background: var(--twitch); color: #fff; }
    .plat-kick { background: var(--kick); color: #000; }
    .plat-youtube { background: var(--yt); color: #fff; }
    .user-name { font-weight: 700; margin-right: 4px; }

    /* PIN Modal */
    #pin-modal {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(11, 15, 25, 0.95);
      backdrop-filter: blur(16px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 999;
      padding: 20px;
    }
    .modal-box {
      background: var(--card-bg);
      border: 1px solid var(--accent);
      border-radius: 16px;
      padding: 24px;
      width: 100%;
      max-width: 320px;
      text-align: center;
      box-shadow: 0 0 24px var(--accent-glow);
    }
    .modal-box h2 { font-size: 1.2rem; margin-bottom: 8px; color: var(--accent); }
    .modal-box p { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 16px; }
    .pin-input {
      width: 100%;
      font-size: 1.8rem;
      text-align: center;
      letter-spacing: 6px;
      padding: 10px;
      border-radius: 10px;
      border: 1px solid var(--accent);
      background: rgba(0, 0, 0, 0.4);
      color: #fff;
      margin-bottom: 16px;
    }
    .submit-btn {
      width: 100%;
      padding: 12px;
      border-radius: 10px;
      background: var(--accent);
      color: #000;
      font-weight: 800;
      font-size: 1rem;
      border: none;
      cursor: pointer;
    }
  </style>
</head>
<body>

  <!-- PIN Modal -->
  <div id="pin-modal" style="display: none;">
    <div class="modal-box">
      <h2>✦ KRONOS VEIL</h2>
      <p>Enter 4-Digit Companion PIN</p>
      <input type="password" id="pin-input" class="pin-input" maxlength="6" inputmode="numeric" placeholder="****">
      <button class="submit-btn" onclick="savePin()">PAIR DEVICE</button>
    </div>
  </div>

  <header>
    <div class="brand">
      <span>✦</span> KRONOS VEIL
    </div>
    <div class="status-pill">
      <div id="conn-dot" class="status-dot"></div>
      <span id="conn-text">Connecting...</span>
    </div>
  </header>

  <nav class="nav-tabs">
    <div class="nav-tab active" onclick="switchTab('deck')">🎮 DECK</div>
    <div class="nav-tab" onclick="switchTab('chat')">💬 LIVE CHAT</div>
    <div class="nav-tab" onclick="switchTab('stats')">📊 STATS</div>
  </nav>

  <main>
    <!-- DECK TAB -->
    <div id="tab-deck" class="tab-content active">
      <div class="deck-grid">
        <button id="btn-lock" class="deck-btn" onclick="triggerAction('toggle_lock')">
          <span class="btn-icon">🔒</span>
          <span>Lock Mode</span>
          <span id="sub-lock" class="btn-sub">Edit Mode</span>
        </button>

        <button id="btn-clickthru" class="deck-btn" onclick="triggerAction('toggle_clickthrough')">
          <span class="btn-icon">🖱️</span>
          <span>Click-Through</span>
          <span id="sub-clickthru" class="btn-sub">Disabled</span>
        </button>

        <button id="btn-stream" class="deck-btn" onclick="triggerAction('obs_toggle_stream')">
          <span class="btn-icon">📡</span>
          <span>OBS Stream</span>
          <span id="sub-stream" class="btn-sub">Offline</span>
        </button>

        <button id="btn-record" class="deck-btn" onclick="triggerAction('obs_toggle_record')">
          <span class="btn-icon">⏺️</span>
          <span>OBS Record</span>
          <span id="sub-record" class="btn-sub">Stopped</span>
        </button>

        <button class="deck-btn" onclick="triggerAction('clear_chat')">
          <span class="btn-icon">🧹</span>
          <span>Clear Chat</span>
          <span class="btn-sub">Purge Overlay</span>
        </button>

        <button class="deck-btn" onclick="triggerAction('test_alert')">
          <span class="btn-icon">⭐</span>
          <span>Test Alert</span>
          <span class="btn-sub">Mention / Toast</span>
        </button>
      </div>

      <!-- OBS Scene Switcher Quick Bar -->
      <div id="scenes-box" style="display: none;">
        <div style="font-size: 0.8rem; color: var(--text-muted); font-weight: 700; margin-bottom: 8px;">OBS SCENES</div>
        <div id="scenes-list" style="display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px;"></div>
      </div>
    </div>

    <!-- CHAT TAB -->
    <div id="tab-chat" class="tab-content">
      <div id="chat-container">
        <div style="text-align: center; color: var(--text-muted); font-size: 0.8rem; margin-top: 20px;">
          Listening for live chat messages...
        </div>
      </div>
    </div>

    <!-- STATS TAB -->
    <div id="tab-stats" class="tab-content">
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-title">Stream Bitrate</div>
          <div id="stat-bitrate" class="stat-value">0 kbps</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Stream FPS</div>
          <div id="stat-fps" class="stat-value">0.0</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Dropped Frames</div>
          <div id="stat-dropped" class="stat-value" style="color: var(--success);">0 (0.0%)</div>
        </div>
        <div class="stat-card">
          <div class="stat-title">Uptime</div>
          <div id="stat-uptime" class="stat-value">00:00:00</div>
        </div>
      </div>
    </div>
  </main>

  <script>
    let currentTab = 'deck';
    let pin = localStorage.getItem('kv_companion_pin') || '';
    let eventSource = null;

    function switchTab(name) {
      currentTab = name;
      document.querySelectorAll('.nav-tab').forEach((t, i) => {
        t.classList.toggle('active', ['deck', 'chat', 'stats'][i] === name);
      });
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      document.getElementById(`tab-${name}`).classList.add('active');
    }

    function savePin() {
      const val = document.getElementById('pin-input').value.trim();
      pin = val;
      localStorage.setItem('kv_companion_pin', pin);
      document.getElementById('pin-modal').style.display = 'none';
      connectEvents();
    }

    function triggerAction(action, params = {}) {
      fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin, action, params })
      })
      .then(res => {
        if (res.status === 401) {
          document.getElementById('pin-modal').style.display = 'flex';
        }
        return res.json();
      })
      .catch(err => console.error('Action error:', err));
    }

    function updateStatusUI(st) {
      if (st.pin_required && !pin) {
        document.getElementById('pin-modal').style.display = 'flex';
      }

      // Lock button
      const btnLock = document.getElementById('btn-lock');
      btnLock.classList.toggle('active', st.locked);
      document.getElementById('sub-lock').innerText = st.locked ? 'Locked' : 'Edit Mode';

      // Clickthrough
      const btnClick = document.getElementById('btn-clickthru');
      btnClick.classList.toggle('active', st.click_through);
      document.getElementById('sub-clickthru').innerText = st.click_through ? 'Passthrough' : 'Disabled';

      // OBS Stream
      const btnStream = document.getElementById('btn-stream');
      btnStream.classList.toggle('live', st.obs_streaming);
      document.getElementById('sub-stream').innerText = st.obs_streaming ? 'LIVE' : 'Offline';

      // OBS Record
      const btnRecord = document.getElementById('btn-record');
      btnRecord.classList.toggle('live', st.obs_recording);
      document.getElementById('sub-record').innerText = st.obs_recording ? 'RECORDING' : 'Stopped';

      // Stats
      document.getElementById('stat-bitrate').innerText = `${st.bitrate || 0} kbps`;
      document.getElementById('stat-fps').innerText = (st.fps || 0).toFixed(1);
      const droppedEl = document.getElementById('stat-dropped');
      const dropped = st.dropped_frames || 0;
      droppedEl.innerText = `${dropped}`;
      droppedEl.style.color = dropped > 100 ? 'var(--danger)' : (dropped > 0 ? 'var(--warning)' : 'var(--success)');
      document.getElementById('stat-uptime').innerText = st.uptime || '00:00:00';

      // Scenes
      if (st.scenes && st.scenes.length > 0) {
        document.getElementById('scenes-box').style.display = 'block';
        const list = document.getElementById('scenes-list');
        list.innerHTML = '';
        st.scenes.forEach(sc => {
          const btn = document.createElement('button');
          btn.className = 'status-pill';
          btn.style.cursor = 'pointer';
          btn.style.border = sc === st.current_scene ? '1px solid var(--accent)' : '1px solid rgba(255,255,255,0.1)';
          btn.style.background = sc === st.current_scene ? 'rgba(0,229,255,0.2)' : 'rgba(255,255,255,0.05)';
          btn.style.color = sc === st.current_scene ? 'var(--accent)' : 'var(--text)';
          btn.innerText = sc;
          btn.onclick = () => triggerAction('obs_set_scene', { scene_name: sc });
          list.appendChild(btn);
        });
      }
    }

    function addChatMessage(msg) {
      const container = document.getElementById('chat-container');
      const row = document.createElement('div');
      row.className = 'chat-row';

      let platTag = '';
      if (msg.platform === 'twitch') platTag = '<span class="plat-badge plat-twitch">TW</span>';
      else if (msg.platform === 'kick') platTag = '<span class="plat-badge plat-kick">KICK</span>';
      else if (msg.platform === 'youtube') platTag = '<span class="plat-badge plat-youtube">YT</span>';

      const userColor = msg.color || '#00e5ff';
      row.innerHTML = `${platTag}<span class="user-name" style="color: ${userColor};">${msg.username}:</span> <span>${msg.message}</span>`;
      container.appendChild(row);

      // Auto scroll
      container.scrollTop = container.scrollHeight;
    }

    function connectEvents() {
      if (eventSource) eventSource.close();

      eventSource = new EventSource('/api/events');
      const dot = document.getElementById('conn-dot');
      const text = document.getElementById('conn-text');

      eventSource.onopen = () => {
        dot.className = 'status-dot online';
        text.innerText = 'Connected';
      };

      eventSource.addEventListener('status', (e) => {
        try {
          const st = JSON.parse(e.data);
          updateStatusUI(st);
        } catch (err) {}
      });

      eventSource.addEventListener('chat', (e) => {
        try {
          const msg = JSON.parse(e.data);
          addChatMessage(msg);
        } catch (err) {}
      });

      eventSource.onerror = () => {
        dot.className = 'status-dot';
        text.innerText = 'Reconnecting...';
      };
    }

    window.onload = () => {
      fetch('/api/status')
        .then(res => res.json())
        .then(st => {
          updateStatusUI(st);
          if (st.pin_required && !pin) {
            document.getElementById('pin-modal').style.display = 'flex';
          } else {
            connectEvents();
          }
        })
        .catch(() => connectEvents());
    };
  </script>
</body>
</html>
"""
