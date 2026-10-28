"""Server-Sent Events (SSE) and HTTP Transport for mcp-mesh.

Enables remote, containerized, and shared multi-agent access to the gateway
using standard HTTP and SSE protocols (Zero external dependencies).
Includes Bearer token authentication and CORS origin controls.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional

from .core import JSONRPCRequest, JSONRPCResponse
from .proxy import MCPMeshGateway


def is_loopback_host(host: str) -> bool:
    """Returns True if the host is a local loopback address (e.g. 127.0.0.1, localhost, ::1)."""
    h = host.strip().lower()
    if h in ("127.0.0.1", "localhost", "::1", "ip6-localhost", "ip6-loopback"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_loopback
    except ValueError:
        return False


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
    auth_token: Optional[str] = None
    allowed_origins: Optional[List[str]] = None
    MAX_REQUEST_BODY_BYTES: int = 10 * 1024 * 1024  # 10 MB payload limit

    def _verify_host_header(self) -> bool:
        """Protects against DNS rebinding attacks by validating the Host header."""
        host_header = self.headers.get("Host", "").strip()
        if not host_header:
            self.send_error(400, "Missing required Host header.")
            return False

        # Extract hostname, handling IPv6 literals like [::1]:8000
        if host_header.startswith("["):
            hostname = host_header.split("]")[0].lstrip("[")
        else:
            hostname = host_header.split(":")[0]

        # Valid loopback hostnames are always permitted
        if is_loopback_host(hostname):
            return True

        # If server is bound to a specific non-loopback host
        server_host = getattr(self.server, "server_address", (None,))[0]
        if server_host and hostname == server_host:
            return True

        # If Bearer token authentication is enabled, remote access is protected
        if self.auth_token is not None:
            return True

        # Otherwise reject untrusted external Host header to prevent DNS rebinding
        self.send_error(403, "Invalid Host header: DNS rebinding rejected.")
        return False

    def _get_cors_origin_header(self) -> Optional[str]:
        """Determines the appropriate Access-Control-Allow-Origin value for the request."""
        origin = self.headers.get("Origin", "")
        if not origin:
            return None

        # User-configured allowed origins list
        if self.allowed_origins is not None:
            if "*" in self.allowed_origins:
                return "*"
            if origin in self.allowed_origins:
                return origin
            return None

        # Default: allow local loopback origins (localhost, 127.0.0.1, [::1] on any port)
        parsed_origin = urllib.parse.urlparse(origin)
        hostname = (parsed_origin.hostname or "").lower()
        if hostname in ("127.0.0.1", "localhost", "::1"):
            return origin
        try:
            if hostname and ipaddress.ip_address(hostname).is_loopback:
                return origin
        except ValueError:
            pass

        return None

    def _set_cors_headers(self, matched_origin: Optional[str] = None) -> None:
        """Applies CORS headers if the Origin header is authorized."""
        origin = matched_origin or self._get_cors_origin_header()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Vary", "Origin")

    def _verify_auth(self) -> bool:
        """Validates Bearer token authentication if auth_token is configured."""
        if self.auth_token is None:
            return True

        # Check Authorization: Bearer <token>
        auth_header = self.headers.get("Authorization", "")
        token_candidate = None
        if auth_header.startswith("Bearer "):
            token_candidate = auth_header[7:].strip()

        # Check query parameter ?token=<token>
        if not token_candidate:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            tokens = qs.get("token", [])
            if tokens:
                token_candidate = tokens[0]

        # Timing-attack safe comparison
        if token_candidate and hmac.compare_digest(token_candidate, self.auth_token):
            return True

        # Return 401 Unauthorized without leaking any token
        payload = json.dumps({
            "jsonrpc": "2.0",
            "error": {
                "code": -32000,
                "message": "Unauthorized: Invalid or missing authentication token.",
            },
        }).encode("utf-8")
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("WWW-Authenticate", 'Bearer realm="mcp-mesh"')
        self._set_cors_headers()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        return False

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        if not self._verify_host_header():
            return

        matched = self._get_cors_origin_header()
        req_origin = self.headers.get("Origin")
        if req_origin and not matched:
            self.send_error(403, "CORS origin not allowed.")
            return

        self.send_response(204)
        if matched:
            self._set_cors_headers(matched)
        self.end_headers()

    def do_GET(self) -> None:
        if not self._verify_host_header():
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/health" or path == "/":
            self._send_json_response(200, {
                "status": "healthy",
                "service": "mcp-mesh",
                "version": "1.4.0",
                "transport": "sse",
                "tools_indexed": len(self.gateway.indexer.tools),
                "auth_required": self.auth_token is not None,
            })
            return

        if path == "/sse":
            if not self._verify_auth():
                return
            self._handle_sse_connect()
            return

        self.send_error(404, "Endpoint not found.")

    def do_POST(self) -> None:
        if not self._verify_host_header():
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/message":
            if not self._verify_auth():
                return
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
        self._set_cors_headers()
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

        if content_length > self.MAX_REQUEST_BODY_BYTES:
            self.send_error(413, "Payload Too Large: JSON-RPC body exceeds 10MB limit.")
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
        raw_session_id = qs.get("sessionId", [""])[0]
        # Sanitize session_id to alphanumeric characters
        session_id = raw_session_id if raw_session_id.isalnum() else ""

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
            self._set_cors_headers()
            self.end_headers()

    def _send_json_response(self, code: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._set_cors_headers()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        # Override default noisy stderr logging
        pass


def make_sse_handler(
    registry_or_gateway: Any,
    mode: str = "lazy",
    auth_token: Optional[str] = None,
    allowed_origins: Optional[List[str]] = None,
) -> type[MCPMeshSSEHandler]:
    """Factory creating an MCPMeshSSEHandler bound to a specific gateway or registry."""
    if isinstance(registry_or_gateway, MCPMeshGateway):
        gw = registry_or_gateway
    else:
        gw = MCPMeshGateway(registry=registry_or_gateway, mode=mode)

    _auth = auth_token
    _origins = allowed_origins

    class BoundSSEHandler(MCPMeshSSEHandler):
        gateway = gw
        sessions: Dict[str, SSEClientConnection] = {}
        sessions_lock = threading.Lock()
        auth_token = _auth
        allowed_origins = _origins

    return BoundSSEHandler


def run_sse_server(
    gateway: Optional[MCPMeshGateway] = None,
    registry: Optional[Any] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    mode: str = "lazy",
    auth_token: Optional[str] = None,
    allowed_origins: Optional[List[str]] = None,
    insecure_no_auth: bool = False,
) -> None:
    """Starts the MCP SSE gateway HTTP server.

    Security:
        - If host is non-loopback (e.g. 0.0.0.0), auth_token is mandatory unless
          insecure_no_auth is explicitly set to True.
        - Origins are restricted to local loopback interfaces by default.
    """
    if not is_loopback_host(host) and not auth_token and not insecure_no_auth:
        raise ValueError(
            f"Security Error: Refusing to bind mcp-mesh to non-loopback interface '{host}' "
            f"without authentication. Provide an auth token via --token / MCP_MESH_AUTH_TOKEN "
            f"or pass --insecure-no-auth if this is an isolated network."
        )

    if gateway is None:
        from .registry import DownstreamRegistry
        reg = registry or DownstreamRegistry()
        gateway = MCPMeshGateway(registry=reg, mode=mode)

    handler_cls = make_sse_handler(
        gateway,
        mode=mode,
        auth_token=auth_token,
        allowed_origins=allowed_origins,
    )
    server = HTTPServer((host, port), handler_cls)
    auth_status = "ENABLED (Bearer token required)" if auth_token else "DISABLED (local loopback mode)"
    sys.stderr.write(f"[mcp-mesh] SSE & HTTP Gateway running on http://{host}:{port}\n")
    sys.stderr.write(f"[mcp-mesh] Authentication: {auth_status}\n")
    sys.stderr.write(f"[mcp-mesh] SSE Endpoint: http://{host}:{port}/sse\n")
    sys.stderr.flush()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[mcp-mesh] Shutting down SSE server...\n")
    finally:
        server.server_close()
