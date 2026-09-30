"""Unit tests for mcp_mesh/registry.py.
"""

import os
import tempfile
import unittest
import json
from mcp_mesh.core import ToolDefinition
from mcp_mesh.registry import DownstreamRegistry


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = DownstreamRegistry()

    def test_mock_server_registration_and_call(self):
        def sample_dispatcher(tool_name: str, args: dict) -> str:
            if tool_name == "echo":
                return f"Echoed: {args.get('msg')}"
            return "Unknown"

        tool = ToolDefinition(
            name="echo",
            server_id="echo_server",
            description="Echo a test message back to caller.",
            input_schema={"type": "object", "properties": {"msg": {"type": "string"}}},
        )

        self.registry.register_mock_server("echo_server", [tool], dispatcher=sample_dispatcher)

        # Tool was added to indexer
        indexed = self.registry.indexer.get_tool("echo_server::echo")
        self.assertIsNotNone(indexed)

        # Call tool via registry
        res = self.registry.call_tool("echo_server", "echo", {"msg": "Hello Existential Cloud"})
        self.assertIn("result", res)
        self.assertIn("Echoed: Hello Existential Cloud", res["result"]["content"][0]["text"])

    def test_load_config_file(self):
        config_data = {
            "mcpServers": {
                "mock_git": {
                    "command": "python",
                    "args": ["-c", "print('mock')"],
                    "description": "Mock Git",
                }
            }
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            json.dump(config_data, f)
            temp_path = f.name

        try:
            count = self.registry.load_config_file(temp_path)
            self.assertEqual(count, 1)
            self.assertIn("mock_git", self.registry.configs)
            self.assertEqual(self.registry.configs["mock_git"].command, "python")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
