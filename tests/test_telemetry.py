"""Unit tests for the SQLite TelemetryLedger module."""

import tempfile
import unittest
from pathlib import Path
from mcp_mesh.telemetry import TelemetryLedger


class TestTelemetryLedger(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_telemetry.db"
        self.ledger = TelemetryLedger(db_path=self.db_path)

    def tearDown(self):
        self.ledger.close()
        self.tmp_dir.cleanup()

    def test_schema_initialization(self):
        """Verifies database file and tables are created correctly."""
        self.assertTrue(self.db_path.exists())
        summary = self.ledger.get_summary()
        self.assertEqual(summary["total_calls"], 0)
        self.assertEqual(summary["total_tokens_saved"], 0)

    def test_session_lifecycle(self):
        """Verifies session recording in the database."""
        self.ledger.start_session(session_id="session-1", mode="lazy", server_count=3, tool_count=15)
        rows = self.ledger.query("SELECT * FROM sessions WHERE session_id = 'session-1'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["mode"], "lazy")
        self.assertEqual(rows[0]["server_count"], 3)
        self.assertEqual(rows[0]["tool_count"], 15)

    def test_call_logging_and_summary(self):
        """Tests call metrics recording and summary aggregation."""
        self.ledger.log_call(
            server_id="github",
            tool_name="create_issue",
            latency_ms=45.2,
            success=True,
            cache_hit=False,
            tokens_baseline=5000,
            tokens_mesh=380,
            tokens_saved=4620,
            session_id="s1",
        )
        self.ledger.log_call(
            server_id="github",
            tool_name="create_issue",
            latency_ms=12.1,
            success=True,
            cache_hit=True,
            tokens_baseline=5000,
            tokens_mesh=380,
            tokens_saved=4620,
            session_id="s1",
        )

        summary = self.ledger.get_summary()
        self.assertEqual(summary["total_calls"], 2)
        self.assertEqual(summary["successful_calls"], 2)
        self.assertEqual(summary["cache_hits"], 1)
        self.assertEqual(summary["cache_hit_ratio_percent"], 50.0)
        self.assertEqual(summary["total_tokens_saved"], 9240)
        self.assertGreater(summary["estimated_dollars_saved"], 0.0)

    def test_tool_cooccurrence(self):
        """Tests recording and querying tool co-occurrence graphs."""
        self.ledger.record_cooccurrence("git::status", "git::commit")
        self.ledger.record_cooccurrence("git::status", "git::commit")
        self.ledger.record_cooccurrence("git::status", "git::diff")

        related = self.ledger.get_related_tools("git::status")
        self.assertGreaterEqual(len(related), 2)
        # git::commit should have count 2
        self.assertEqual(related[0][0], "git::commit")
        self.assertEqual(related[0][1], 2)

    def test_custom_sql_query(self):
        """Tests read-only query execution."""
        self.ledger.log_call("postgres", "query", 30.0, True, False, 1000, 100, 900)
        results = self.ledger.query("SELECT server_id, COUNT(*) as cnt FROM calls GROUP BY server_id")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["server_id"], "postgres")
        self.assertEqual(results[0]["cnt"], 1)

    def test_security_read_only_sql(self):
        """Verifies that non-SELECT statements are rejected."""
        with self.assertRaises(ValueError):
            self.ledger.query("DROP TABLE calls;")


if __name__ == "__main__":
    unittest.main()
