"""Unit tests for mcp-mesh real-time terminal monitor (mcp_mesh.monitor)."""

import unittest
from mcp_mesh.monitor import TerminalMonitor, run_monitor


class TestTerminalMonitor(unittest.TestCase):
    """Verifies the TerminalMonitor accounting and frame rendering."""

    def setUp(self) -> None:
        self.monitor = TerminalMonitor(servers=["test_git", "test_db"])

    def test_initial_state(self) -> None:
        self.assertEqual(self.monitor.total_queries, 0)
        self.assertEqual(self.monitor.total_invocations, 0)
        self.assertEqual(self.monitor.raw_tokens_burned, 0)
        self.assertEqual(self.monitor.mesh_tokens_burned, 0)
        self.assertEqual(len(self.monitor.events), 0)

    def test_record_search(self) -> None:
        self.monitor.record_search("find commit", ["test_git::log"], 1.5)
        self.assertEqual(self.monitor.total_queries, 1)
        self.assertEqual(len(self.monitor.events), 1)
        ev = self.monitor.events[0]
        self.assertEqual(ev["type"], "SEARCH")
        self.assertIn("find commit", ev["detail"])
        self.assertEqual(ev["latency"], 1.5)

    def test_record_invocation_and_economy(self) -> None:
        self.monitor.record_invocation("query_sql", "test_db", 2.2, cache_hit=True)
        self.assertEqual(self.monitor.total_invocations, 1)
        self.assertEqual(self.monitor.cache_hits, 1)
        self.assertEqual(self.monitor.cache_misses, 0)
        self.assertEqual(self.monitor.raw_tokens_burned, 13200)
        self.assertEqual(self.monitor.mesh_tokens_burned, 380)

        # Record a second miss
        self.monitor.record_invocation("get_file", "test_git", 1.1, cache_hit=False)
        self.assertEqual(self.monitor.total_invocations, 2)
        self.assertEqual(self.monitor.cache_misses, 1)
        self.assertEqual(self.monitor.raw_tokens_burned, 26400)
        self.assertEqual(self.monitor.mesh_tokens_burned, 760)

    def test_render_frame_contains_key_elements(self) -> None:
        self.monitor.record_search("test search", ["tool1"], 0.5)
        self.monitor.record_invocation("tool1", "serverA", 1.0, cache_hit=True)
        frame = self.monitor.render_frame()

        self.assertIn("MCP-MESH REAL-TIME AGENT TELEMETRY MONITOR", frame)
        self.assertIn("TOKEN ECONOMY METER", frame)
        self.assertIn("Net Tokens Saved", frame)
        self.assertIn("RECENT ROUTING EVENTS", frame)
        self.assertIn("serverA::tool1 (LRU Hit)", frame)

    def test_run_monitor_iterations(self) -> None:
        # Run 2 ticks in mock mode with tiny interval
        run_monitor(iterations=2, interval=0.01, mock=True)


if __name__ == "__main__":
    unittest.main()
