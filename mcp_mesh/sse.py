"""Server-Sent Events (SSE) and HTTP Transport for mcp-mesh.

Enables remote, containerized, and shared multi-agent access to the gateway
using standard HTTP and SSE protocols (Zero external dependencies).
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

from .core import JSONRPCRequest, JSONRPCResponse
from .proxy import MCPMeshGateway


class SSEClientConnection:
    """Represents an active client SSE subscription stream."""

    def __init__(self, session_id: str, handler: Optional[BaseHTTPRequestHandler] = None) -> None:
        self.session_id = session_id
        self.handler = handler
        self.active = True
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []

    def send_event(self, event_type: str, data: Any) -> bool:
        """Writes an SSE formatted event to the client socket and local event buffer."""
        if not self.active:
            return False
        with self._lock:
            self._events.append({"event": event_type, "data": data})
            if self.handler and hasattr(self.handler, "wfile"):
                try:
                    payload_data = json.dumps(data) if not isinstance(data, str) else data
                    payload = f"event: {event_type}\ndata: {payload_data}\n\n"
                    self.handler.wfile.write(payload.encode("utf-8"))
                    self.handler.wfile.flush()
                except Exception:
                    self.active = False
                    return False
            return True

    def get_event(self, timeout: float = 0.5) -> Optional[dict[str, Any]]:
        """Retrieves the oldest queued event, if any."""
        with self._lock:
            if self._events:
                return self._events.pop(0)
        return None

    def close(self) -> None:
        """Closes the client session."""
        self.active = False


SSESession = SSEClientConnection


class MCPMeshSSEHandler(BaseHTTPRequestHandler):
    """HTTP request handler implementing the Model Context Protocol SSE specification."""

    gateway: MCPMeshGateway
    sessions: Dict[str, SSEClientConnection] = {}
    sessions_lock = threading.Lock()

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/health" or path == "/":
            self._send_json_response(200, {
                "status": "healthy",
                "service": "mcp-mesh",
                "version": "1.1.0",
                "transport": "sse",
                "tools_indexed": len(self.gateway.indexer.tools),
            })
            return

        if path == "/sse":
            self._handle_sse_connect()
            return

        self.send_error(404, "Endpoint not found.")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/message":
            self._handle_message_post(parsed)
            return

        self.send_error(404, "Endpoint not found.")

    def _handle_sse_connect(self) -> None:
        """Opens persistent SSE connection and sends the endpoint notification."""
        session_id = uuid.uuid4().hex
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        client_conn = SSEClientConnection(session_id, self)
        with self.sessions_lock:
            self.sessions[session_id] = client_conn

        # Send initial endpoint event as mandated by MCP spec
        endpoint_uri = f"/message?sessionId={session_id}"
        client_conn.send_event("endpoint", endpoint_uri)

        # Keep socket open and send keep-alive heartbeats
        try:
            while client_conn.active:
                time.sleep(15)
                if not client_conn.send_event("ping", "{}"):
                    break
        except Exception:
            pass
        finally:
            with self.sessions_lock:
                if session_id in self.sessions:
                    del self.sessions[session_id]

    def _handle_message_post(self, parsed: urllib.parse.ParseResult) -> None:
        """Receives JSON-RPC request and dispatches to the gateway."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self.send_error(400, "Empty request body.")
            return

        body_raw = self.rfile.read(content_length).decode("utf-8")
        try:
            req_data = json.loads(body_raw)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON payload.")
            return

        req = JSONRPCRequest.from_dict(req_data)
        res = self.gateway.dispatch_request(req)

        # Check if query parameter specifies active session to stream response over SSE
        qs = urllib.parse.parse_qs(parsed.query)
        session_id = qs.get("sessionId", [""])[0]

        if res is not None:
            res_dict = res.to_dict()
            with self.sessions_lock:
                client = self.sessions.get(session_id)
                if client and client.active:
                    client.send_event("message", json.dumps(res_dict))

            # Also return direct HTTP 200 response
            self._send_json_response(200, res_dict)
        else:
            self.send_response(202)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

    def _send_json_response(self, code: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        # Override default noisy stderr logging
        pass


def make_sse_handler(registry_or_gateway: Any, mode: str = "lazy") -> type[MCPMeshSSEHandler]:
    """Factory creating an MCPMeshSSEHandler bound to a specific gateway or registry."""
    if isinstance(registry_or_gateway, MCPMeshGateway):
        gw = registry_or_gateway
    else:
        gw = MCPMeshGateway(registry=registry_or_gateway, mode=mode)

    class BoundSSEHandler(MCPMeshSSEHandler):
        gateway = gw
        sessions: Dict[str, SSEClientConnection] = {}
        sessions_lock = threading.Lock()

    return BoundSSEHandler


def run_sse_server(
    gateway: Optional[MCPMeshGateway] = None,
    registry: Optional[Any] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    mode: str = "lazy",
) -> None:
    """Starts the MCP SSE gateway HTTP server."""
    if gateway is None:
        from .registry import DownstreamRegistry
        reg = registry or DownstreamRegistry()
        gateway = MCPMeshGateway(registry=reg, mode=mode)

    handler_cls = make_sse_handler(gateway, mode=mode)
    server = HTTPServer((host, port), handler_cls)
    sys.stderr.write(f"[mcp-mesh] SSE & HTTP Gateway running on http://{host}:{port}\n")
    sys.stderr.write(f"[mcp-mesh] SSE Endpoint: http://{host}:{port}/sse\n")
    sys.stderr.flush()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[mcp-mesh] Shutting down SSE server...\n")
    finally:
        server.server_close()
