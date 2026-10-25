"""Cross-Repository Ecosystem Integration Tests.

Verifies end-to-end compatibility between:
1. mcp-registry-cli (package discovery and target configuration writing)
2. mcp-mesh (gateway configuration loading and JSON-RPC meta-tool exposition)
3. mcp-mesh telemetry ledger (SQLite session and call recording)
4. mcp-mesh-ui (telemetry ingestion and metrics aggregation)
5. mcp-mesh-eval (benchmark scaling model and dynamic token reduction)
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

# Add sibling packages to sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
for pkg in ["mcp-mesh", "mcp-registry-cli", "mcp-mesh-ui", "mcp-mesh-eval"]:
    pkg_path = str(repo_root / pkg)
    if pkg_path not in sys.path:
        sys.path.insert(0, pkg_path)


class TestCrossEcosystemIntegration(unittest.TestCase):
    def setUp(self):
        try:
            import mcp_registry
            import mcp_mesh_ui
            import mcp_mesh_eval
        except ImportError as e:
            raise unittest.SkipTest(f"Sibling ecosystem packages not present in standalone CI: {e}")

        self.tmp_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp_dir)
        self.config_file = self.tmp_path / "mcp_mesh.json"
        self.telemetry_db = self.tmp_path / "telemetry.db"

    def tearDown(self):
        try:
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_full_lifecycle_cross_repo_workflow(self):
        # 1. mcp-registry-cli: search & install
        from mcp_registry.client import RegistryClient
        from mcp_registry.installer import MCPInstaller, TargetClient

        client = RegistryClient()
        results = client.search("sqlite")
        self.assertGreater(len(results), 0, "Failed to search registry for sqlite")
        entry = results[0]

        installer = MCPInstaller(target_type=TargetClient.MCP_MESH, custom_path=self.config_file)
        ok, msg = installer.install(entry)
        self.assertTrue(ok, f"Install failed: {msg}")
        self.assertTrue(self.config_file.exists(), "Config file not created by installer")

        # 2. mcp-mesh: load registry & inspect
        from mcp_mesh.registry import DownstreamRegistry
        from mcp_mesh.proxy import MCPMeshGateway
        from mcp_mesh.core import JSONRPCRequest

        registry = DownstreamRegistry()
        count = registry.load_config_file(str(self.config_file))
        self.assertEqual(count, 1, "DownstreamRegistry failed to load configured server")
        self.assertIn("sqlite", registry.configs)

        gateway = MCPMeshGateway(registry=registry)
        resp = gateway.dispatch_request(JSONRPCRequest(jsonrpc="2.0", id="1", method="tools/list"))
        tools = resp.result.get("tools", [])
        self.assertEqual(len(tools), 4, "Gateway did not expose exactly 4 meta-tools")
        meta_tool_names = [t["name"] for t in tools]
        self.assertIn("mesh_search_tools", meta_tool_names)
        self.assertIn("mesh_describe_tool", meta_tool_names)
        self.assertIn("mesh_invoke_tool", meta_tool_names)
        self.assertIn("mesh_status", meta_tool_names)

        # 3. Telemetry logging in mcp-mesh
        from mcp_mesh.telemetry import TelemetryLedger
        ledger = TelemetryLedger(db_path=self.telemetry_db)
        ledger.start_session(session_id="e2e-session-test", mode="federated", server_count=1, tool_count=3)
        ledger.log_call(
            server_id="sqlite",
            tool_name="read_query",
            latency_ms=15.0,
            success=True,
            cache_hit=False,
            tokens_baseline=220,
            tokens_mesh=0,
            tokens_saved=220,
        )

        # 4. mcp-mesh-ui: read telemetry & aggregate
        from mcp_mesh_ui.core import MeshTelemetryStore
        ui_store = MeshTelemetryStore(db_path=self.telemetry_db)
        summary = ui_store.get_summary()
        self.assertEqual(summary.total_calls, 1)
        self.assertEqual(summary.total_tokens_saved, 220)
        self.assertEqual(summary.successful_calls, 1)

        # 5. mcp-mesh-eval: dynamic benchmark math verification
        from mcp_mesh_eval.engine import BenchmarkHarness
        eval_tools = str(repo_root / "mcp-mesh-eval" / "evals" / "tools_60.json")
        eval_intents = str(repo_root / "mcp-mesh-eval" / "evals" / "intents_50.json")
        harness = BenchmarkHarness(tools_path=eval_tools, intents_path=eval_intents)
        eval_results = harness.run_all()
        self.assertGreater(len(eval_results), 0)
        res = eval_results[0]
        self.assertEqual(res.raw_tokens, 9790)
        self.assertEqual(res.mesh_tokens, 527)
        self.assertEqual(res.token_reduction_pct, 94.6)


if __name__ == "__main__":
    unittest.main()
