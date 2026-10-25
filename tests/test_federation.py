"""
Unit tests for FederationManager and System MCP Config Aggregation.
Verifies loop prevention, multi-client config loading, concurrent discovery, and predictive pre-warming.
"""

import unittest
import tempfile
import json
from pathlib import Path

from mcp_mesh.core import ToolDefinition, DownstreamServerConfig
from mcp_mesh.registry import DownstreamRegistry
from mcp_mesh.federation import (
    FederationManager,
    discover_system_mcp_configs,
    is_mesh_gateway_command,
)
from mcp_mesh.proxy import MCPMeshGateway


class TestFederationManager(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.registry = DownstreamRegistry()
        self.federation = FederationManager(registry=self.registry)

    def tearDown(self):
        self.registry.shutdown_all()
        self.tmp_dir.cleanup()

    def test_is_mesh_gateway_command(self):
        # Should identify self-referencing commands
        self.assertTrue(is_mesh_gateway_command("python", ["-m", "mcp_mesh.cli", "run"]))
        self.assertTrue(is_mesh_gateway_command("mcp-mesh", ["run"]))
        self.assertTrue(is_mesh_gateway_command("mcp_mesh", ["proxy"]))

        # Non-mesh commands should be False
        self.assertFalse(is_mesh_gateway_command("python", ["-m", "ghost_hunter.server"]))
        self.assertFalse(is_mesh_gateway_command("npx", ["-y", "@modelcontextprotocol/server-github"]))

    def test_load_federated_servers_with_loop_prevention(self):
        # Create a mock client config containing both a valid server and a self-reference
        mock_cfg = {
            "mcpServers": {
                "ghost_hunter": {
                    "command": "python",
                    "args": ["-m", "ghost_hunter.server"],
                    "description": "Ghost Job Hunter Server"
                },
                "mcp_mesh_self": {
                    "command": "python",
                    "args": ["-m", "mcp_mesh.cli", "run"],
                    "description": "Should be ignored to prevent circular loop"
                }
            }
        }
        cfg_file = self.tmp_path / "mock_client_config.json"
        cfg_file.write_text(json.dumps(mock_cfg), encoding="utf-8")

        res = self.federation.load_federated_servers(
            auto_discover=False,
            custom_configs=[cfg_file]
        )

        self.assertEqual(res.get("custom_1"), 1)
        # ghost_hunter should be registered
        self.assertIn("ghost_hunter", self.registry.configs)
        # mcp_mesh_self should NOT be registered
        self.assertNotIn("mcp_mesh_self", self.registry.configs)

    def test_concurrent_tool_discovery_with_mocks(self):
        # Register 2 mock servers
        tools_s1 = [
            ToolDefinition(
                name="query_db",
                server_id="db_server",
                description="Query postgres SQL database tables",
                input_schema={"type": "object"}
            )
        ]
        tools_s2 = [
            ToolDefinition(
                name="send_alert",
                server_id="alert_server",
                description="Send webhook alert notification to Slack",
                input_schema={"type": "object"}
            )
        ]
        self.registry.register_mock_server("db_server", tools_s1, lambda t, a: "db_ok")
        self.registry.register_mock_server("alert_server", tools_s2, lambda t, a: "alert_ok")

        # In mock servers, tools are pre-registered in indexer
        self.assertEqual(self.registry.indexer.get_metrics()["total_tools"], 2)

        # Search query across federated tools
        matches = self.registry.indexer.search("postgres database", limit=2)
        self.assertGreaterEqual(len(matches), 1)
        self.assertEqual(matches[0][0].name, "query_db")

    def test_predictive_prewarm(self):
        # Register a mock server
        tools = [
            ToolDefinition(
                name="audit_code",
                server_id="linter",
                description="Audit source code for security flaws",
                input_schema={"type": "object"}
            )
        ]
        self.registry.register_mock_server("linter", tools)

        # Test prewarm
        candidate_matches = [(tools[0], 0.95)]
        self.federation.predictive_prewarm_candidates(candidate_matches)
        self.assertIn("linter", self.federation.prewarmed_servers)

    def test_gateway_invoke_without_explicit_server(self):
        # Gateway should auto-resolve server if tool_name is unique or formatted as server::tool
        tools = [
            ToolDefinition(
                name="unique_action",
                server_id="custom_service",
                description="Perform unique action",
                input_schema={"type": "object"}
            )
        ]
        self.registry.register_mock_server("custom_service", tools, lambda t, a: "action_completed")

        gateway = MCPMeshGateway(registry=self.registry)

        # Invoke passing only tool_name (omitting server)
        res = gateway._exec_mesh_invoke(
            req_id="test-1",
            args={"tool_name": "unique_action", "arguments": {}}
        )
        self.assertNotIn("error", res.to_dict())
        self.assertEqual(res.result.get("content", [{}])[0].get("text"), "action_completed")

        # Invoke passing namespaced tool_name
        res_namespaced = gateway._exec_mesh_invoke(
            req_id="test-2",
            args={"tool_name": "custom_service::unique_action", "arguments": {}}
        )
        self.assertNotIn("error", res_namespaced.to_dict())


if __name__ == "__main__":
    unittest.main()
