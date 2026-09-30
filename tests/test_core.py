"""Unit tests for mcp_mesh/core.py.
"""

import unittest
from mcp_mesh.core import (
    JSONRPCRequest,
    JSONRPCResponse,
    ToolDefinition,
    ToolParameter,
    compact_tool_signature,
    estimate_tokens,
)


class TestCoreModels(unittest.TestCase):
    def test_estimate_tokens(self):
        # Empty string
        self.assertEqual(estimate_tokens(""), 0)

        # Basic string
        text = "Hello world this is an MCP protocol test."
        tokens = estimate_tokens(text)
        self.assertGreater(tokens, 5)

        # Dictionary / JSON
        payload = {"method": "tools/call", "params": {"name": "query_db", "sql": "SELECT 1;"}}
        tokens_dict = estimate_tokens(payload)
        self.assertGreater(tokens_dict, 10)

    def test_tool_definition_parsing(self):
        schema = {
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repo owner"},
                "repo": {"type": "string", "description": "Repo name"},
                "count": {"type": "integer", "description": "Max count", "default": 10},
            },
            "required": ["owner", "repo"],
        }
        tool = ToolDefinition(
            name="list_issues",
            server_id="github",
            description="List open issues for a repository.",
            input_schema=schema,
        )

        self.assertEqual(tool.qualified_name, "github::list_issues")
        self.assertEqual(len(tool.parameters), 3)
        self.assertTrue(tool.parameters["owner"].required)
        self.assertTrue(tool.parameters["repo"].required)
        self.assertFalse(tool.parameters["count"].required)
        self.assertGreater(tool.raw_token_count, 15)

        sig = tool.to_compact_signature()
        self.assertIn("github::list_issues", sig)
        self.assertIn("owner: string", sig)
        self.assertIn("count?: integer", sig)

    def test_json_rpc_envelopes(self):
        # Request serialization
        req = JSONRPCRequest(method="initialize", params={"version": "1.0"}, id=101)
        req_dict = req.to_dict()
        self.assertEqual(req_dict["jsonrpc"], "2.0")
        self.assertEqual(req_dict["method"], "initialize")
        self.assertEqual(req_dict["id"], 101)

        # Response result serialization
        res_ok = JSONRPCResponse.make_result(req_id=101, result={"status": "ok"})
        res_line = res_ok.to_json_line()
        self.assertIn('"result": {"status": "ok"}', res_line)
        self.assertIn('"id": 101', res_line)

        # Response error serialization
        res_err = JSONRPCResponse.make_error(req_id=102, code=-32601, message="Method not found")
        self.assertIsNotNone(res_err.error)
        self.assertEqual(res_err.error["code"], -32601)


if __name__ == "__main__":
    unittest.main()
