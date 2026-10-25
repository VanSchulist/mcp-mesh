"""Unit tests for mcp-mesh Server-Sent Events (SSE) remote transport."""

from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import HTTPServer

from mcp_mesh.core import ToolDefinition
from mcp_mesh.registry import DownstreamRegistry
from mcp_mesh.sse import SSESession, make_sse_handler


class TestSSESession(unittest.TestCase):
    """Test suite for SSESession lifecycle and event dispatching."""

    def test_session_lifecycle(self) -> None:
        session = SSESession(session_id="test-session-1")
        self.assertEqual(session.session_id, "test-session-1")
        self.assertTrue(session.active)

        # Enqueue events
        session.send_event("test_event", {"message": "hello world"})
        evt = session.get_event(timeout=0.1)
        self.assertIsNotNone(evt)
        self.assertEqual(evt["event"], "test_event")
        self.assertEqual(evt["data"], {"message": "hello world"})

        # Close session
        session.close()
        self.assertFalse(session.active)


class TestSSETransportServer(unittest.TestCase):
    """End-to-end integration test for the HTTP/SSE gateway server."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = DownstreamRegistry()
        cls.tool = ToolDefinition(
            name="test_tool",
            server_id="test_srv",
            description="A test tool",
            input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        )
        cls.registry.indexer.register_tool(cls.tool)

        handler_cls = make_sse_handler(cls.registry, mode="lazy")
        # Bind to port 0 for dynamic ephemeral port allocation
        cls.server = HTTPServer(("127.0.0.1", 0), handler_cls)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_endpoint(self) -> None:
        req = urllib.request.Request(f"{self.base_url}/health")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "healthy")
            self.assertIn("version", data)

    def test_message_initialize(self) -> None:
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
        data_bytes = json.dumps(init_payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/message",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res["id"], 1)
            self.assertIn("serverInfo", res["result"])
            self.assertEqual(res["result"]["serverInfo"]["name"], "mcp-mesh")

    def test_message_tools_list_lazy(self) -> None:
        list_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        data_bytes = json.dumps(list_payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/message",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res["id"], 2)
            tools = res["result"]["tools"]
            # Lazy mode exposes the 3 meta-tools
            tool_names = [t["name"] for t in tools]
            self.assertIn("mesh_search_tools", tool_names)
            self.assertIn("mesh_describe_tool", tool_names)
            self.assertIn("mesh_invoke_tool", tool_names)

    def test_dns_rebinding_host_header_rejected(self) -> None:
        req = urllib.request.Request(f"{self.base_url}/health")
        req.add_header("Host", "attacker-dns-rebind.example.org")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=2.0)
        self.assertEqual(ctx.exception.code, 403)
        err_msg = ctx.exception.read().decode("utf-8")
        self.assertIn("DNS rebinding rejected", err_msg)

    def test_oversized_payload_rejected(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/message",
            data=b"{}",
            headers={"Content-Length": str(15 * 1024 * 1024), "Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=2.0)
            self.fail("Expected HTTP 413 or connection abort for oversized payload")
        except urllib.error.HTTPError as ctx:
            self.assertEqual(ctx.code, 413)
        except (ConnectionAbortedError, ConnectionResetError):
            # On Windows TCP stacks, immediate server close on oversized Content-Length
            # may trigger WinError 10053/10054 before response headers are fully consumed.
            pass


class TestSSESecurity(unittest.TestCase):
    """Security regression test suite for host binding and authentication guards."""

    def test_non_loopback_refusal_without_token(self) -> None:
        from mcp_mesh.sse import run_sse_server
        with self.assertRaises(ValueError) as ctx:
            run_sse_server(host="0.0.0.0", port=9999)
        self.assertIn("Refusing to bind mcp-mesh to non-loopback", str(ctx.exception))

    def test_loopback_host_detection(self) -> None:
        from mcp_mesh.sse import is_loopback_host
        self.assertTrue(is_loopback_host("127.0.0.1"))
        self.assertTrue(is_loopback_host("localhost"))
        self.assertTrue(is_loopback_host("::1"))
        self.assertFalse(is_loopback_host("0.0.0.0"))
        self.assertFalse(is_loopback_host("::"))
        self.assertFalse(is_loopback_host("192.168.1.50"))


class TestSSEAuthenticatedServer(unittest.TestCase):
    """Integration test suite for Bearer token enforcement and CORS origin controls."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = DownstreamRegistry()
        cls.tool = ToolDefinition(
            name="secure_tool",
            server_id="secure_srv",
            description="A secure tool",
            input_schema={"type": "object", "properties": {"cmd": {"type": "string"}}},
        )
        cls.registry.indexer.register_tool(cls.tool)
        cls.secret = "super-secret-mcp-token-xyz123"

        handler_cls = make_sse_handler(
            cls.registry,
            mode="lazy",
            auth_token=cls.secret,
            allowed_origins=["https://dashboard.example.com"],
        )
        cls.server = HTTPServer(("127.0.0.1", 0), handler_cls)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_unauthenticated_request_rejected(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/message",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=2.0)
        self.assertEqual(ctx.exception.code, 401)
        self.assertIn("Bearer", ctx.exception.headers.get("WWW-Authenticate", ""))
        err_body = ctx.exception.read().decode("utf-8")
        self.assertNotIn(self.secret, err_body)
        self.assertIn("Unauthorized", err_body)

    def test_invalid_token_rejected(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/message",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer wrong-token-456",
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=2.0)
        self.assertEqual(ctx.exception.code, 401)

    def test_valid_bearer_token_accepted(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/message",
            data=json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/list", "params": {}}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.secret}",
            },
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["id"], 10)
            self.assertIn("tools", data["result"])

    def test_valid_query_param_token_accepted(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/message?token={self.secret}",
            data=json.dumps({"jsonrpc": "2.0", "id": 11, "method": "tools/list", "params": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["id"], 11)

    def test_unauthenticated_sse_connect_rejected(self) -> None:
        req = urllib.request.Request(f"{self.base_url}/sse")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=2.0)
        self.assertEqual(ctx.exception.code, 401)

    def test_cors_rejects_unauthorized_origin(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/message",
            method="OPTIONS",
            headers={"Origin": "https://evil.com"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=2.0)
        self.assertEqual(ctx.exception.code, 403)

    def test_cors_allows_configured_origin(self) -> None:
        req = urllib.request.Request(
            f"{self.base_url}/message",
            method="OPTIONS",
            headers={"Origin": "https://dashboard.example.com"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "https://dashboard.example.com")

    def test_options_preflight_does_not_bypass_post_auth(self) -> None:
        req_opt = urllib.request.Request(
            f"{self.base_url}/message",
            method="OPTIONS",
            headers={"Origin": "https://dashboard.example.com"},
        )
        with urllib.request.urlopen(req_opt, timeout=2.0) as resp_opt:
            self.assertEqual(resp_opt.status, 204)

        req_post = urllib.request.Request(
            f"{self.base_url}/message",
            data=json.dumps({"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": "https://dashboard.example.com",
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_post, timeout=2.0)
        self.assertEqual(ctx.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
