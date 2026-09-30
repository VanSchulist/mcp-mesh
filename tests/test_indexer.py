"""Unit tests for mcp_mesh/indexer.py.
"""

import unittest
from mcp_mesh.core import ToolDefinition
from mcp_mesh.indexer import ToolIndexer, tokenize


class TestIndexer(unittest.TestCase):
    def setUp(self):
        self.indexer = ToolIndexer()

        self.t1 = ToolDefinition(
            name="create_pull_request",
            server_id="github",
            description="Open a new pull request in a git repository.",
            category="git",
            input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        )
        self.t2 = ToolDefinition(
            name="query_readonly",
            server_id="postgres",
            description="Run a safe SELECT SQL statement on the relational database.",
            category="database",
            input_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
        )
        self.t3 = ToolDefinition(
            name="read_file",
            server_id="filesystem",
            description="Read text contents of a file on local disk.",
            category="filesystem",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )

        self.indexer.register_tools([self.t1, self.t2, self.t3])

    def test_tokenize(self):
        tokens = tokenize("createPullRequest_v2 on GitHub")
        self.assertIn("create", tokens)
        self.assertIn("pull", tokens)
        self.assertIn("request", tokens)
        self.assertIn("github", tokens)
        # Check stopword removal
        self.assertNotIn("on", tokens)

    def test_search_relevance(self):
        # Query matching github tool
        results_pr = self.indexer.search("pull request git", limit=2)
        self.assertGreater(len(results_pr), 0)
        top_tool, score = results_pr[0]
        self.assertEqual(top_tool.name, "create_pull_request")
        self.assertEqual(top_tool.server_id, "github")
        self.assertGreater(score, 0.0)

        # Query matching database tool
        results_sql = self.indexer.search("execute sql query", limit=2)
        self.assertGreater(len(results_sql), 0)
        self.assertEqual(results_sql[0][0].name, "query_readonly")

    def test_server_and_category_filtering(self):
        # Filter by server
        results_filtered = self.indexer.search("file", server_filter="filesystem")
        self.assertEqual(len(results_filtered), 1)
        self.assertEqual(results_filtered[0][0].server_id, "filesystem")

        # Non-matching filter returns empty
        no_results = self.indexer.search("sql", server_filter="github")
        self.assertEqual(len(no_results), 0)

    def test_get_metrics(self):
        metrics = self.indexer.get_metrics()
        self.assertEqual(metrics["total_servers"], 3)
        self.assertEqual(metrics["total_tools"], 3)
        self.assertGreater(metrics["raw_tool_tokens"], 0)
        self.assertIn("savings_percentage", metrics)

    def test_unregister_server(self):
        removed = self.indexer.unregister_server("postgres")
        self.assertEqual(removed, 1)
        self.assertIsNone(self.indexer.get_tool("postgres::query_readonly"))
        self.assertEqual(len(self.indexer.tools), 2)


if __name__ == "__main__":
    unittest.main()
