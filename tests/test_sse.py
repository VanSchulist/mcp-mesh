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


if __name__ == "__main__":
    unittest.main()
