"""Unit tests for mcp_mesh/proxy.py (MCP Protocol Gateway).
"""

import json
import unittest
from mcp_mesh.core import ToolDefinition
from mcp_mesh.proxy import MCPMeshGateway
from mcp_mesh.registry import DownstreamRegistry


class TestProxyGateway(unittest.TestCase):
    def setUp(self):
        self.registry = DownstreamRegistry()

        def sample_dispatch(tool_name: str, args: dict) -> str:
            if tool_name == "calc_sum":
                return str(args.get("a", 0) + args.get("b", 0))
            return "ok"

        self.t1 = ToolDefinition(
            name="calc_sum",
            server_id="math_server",
            description="Add two integers together.",
            category="math",
            input_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        )
        self.registry.register_mock_server("math_server", [self.t1], dispatcher=sample_dispatch)
        self.gateway = MCPMeshGateway(registry=self.registry, mode="lazy")

    def test_initialize_handshake(self):
        msg = json.dumps({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
            "id": 1,
        })
        res_line = self.gateway.handle_message(msg)
        self.assertIsNotNone(res_line)
        res = json.loads(res_line)

        self.assertEqual(res["id"], 1)
        self.assertIn("serverInfo", res["result"])
        self.assertEqual(res["result"]["serverInfo"]["name"], "mcp-mesh")

    def test_tools_list_lazy_meta_tools(self):
        msg = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 2})
        res_line = self.gateway.handle_message(msg)
        res = json.loads(res_line)

        tools = res["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        # Lazy mode must expose the 4 meta-tools
        self.assertIn("mesh_search_tools", tool_names)
        self.assertIn("mesh_describe_tool", tool_names)
        self.assertIn("mesh_invoke_tool", tool_names)
        self.assertIn("mesh_status", tool_names)

    def test_tools_call_mesh_search(self):
        call_msg = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "mesh_search_tools",
                "arguments": {"query": "add integers together"},
            },
            "id": 3,
        })
        res_line = self.gateway.handle_message(call_msg)
        res = json.loads(res_line)

        self.assertNotIn("error", res)
        text = res["result"]["content"][0]["text"]
        self.assertIn("calc_sum", text)
        self.assertIn("math_server", text)

    def test_tools_call_mesh_describe(self):
        call_msg = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "mesh_describe_tool",
                "arguments": {"server": "math_server", "tool_name": "calc_sum"},
            },
            "id": 4,
        })
        res_line = self.gateway.handle_message(call_msg)
        res = json.loads(res_line)

        self.assertNotIn("error", res)
        text = res["result"]["content"][0]["text"]
        schema = json.loads(text)
        self.assertEqual(schema["name"], "calc_sum")
        self.assertIn("properties", schema["inputSchema"])

    def test_tools_call_mesh_invoke(self):
        call_msg = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "mesh_invoke_tool",
                "arguments": {
                    "server": "math_server",
                    "tool_name": "calc_sum",
                    "arguments": {"a": 40, "b": 2},
                },
            },
            "id": 5,
        })
        res_line = self.gateway.handle_message(call_msg)
        res = json.loads(res_line)

        self.assertNotIn("error", res)
        result_content = res["result"]["content"][0]["text"]
        self.assertEqual(result_content, "42")

    def test_direct_tool_call_fallback(self):
        # Even if client calls tool directly without meta-wrapper, gateway routes it
        call_msg = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "calc_sum",
                "arguments": {"a": 10, "b": 5},
            },
            "id": 6,
        })
        res_line = self.gateway.handle_message(call_msg)
        res = json.loads(res_line)

        self.assertNotIn("error", res)
        self.assertEqual(res["result"]["content"][0]["text"], "15")

    def test_passthrough_mode(self):
        pt_gateway = MCPMeshGateway(registry=self.registry, mode="passthrough")
        msg = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 7})
        res_line = pt_gateway.handle_message(msg)
        res = json.loads(res_line)

        tools = res["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("calc_sum", tool_names)


if __name__ == "__main__":
    unittest.main()
