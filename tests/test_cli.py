"""Unit tests for mcp_mesh/cli.py.
"""

import io
import sys
import unittest
from unittest.mock import patch
from mcp_mesh.cli import cmd_demo, cmd_doctor, cmd_search, cmd_stats, load_demo_tools
import argparse


class TestCLI(unittest.TestCase):
    def test_load_demo_tools(self):
        tools = load_demo_tools()
        self.assertGreater(len(tools), 8)
        server_ids = set(t.server_id for t in tools)
        self.assertIn("github", server_ids)
        self.assertIn("postgres", server_ids)
        self.assertIn("filesystem", server_ids)

    def test_cmd_demo(self):
        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            cmd_demo(argparse.Namespace())
        output = captured_out.getvalue()
        self.assertIn("mcp-mesh", output)
        self.assertIn("Immediate Token Savings", output)
        self.assertIn("Agent intent", output)

    def test_cmd_stats(self):
        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            cmd_stats(argparse.Namespace(config=""))
        output = captured_out.getvalue()
        self.assertIn("AGGREGATION & TOKEN ECONOMY REPORT", output)
        self.assertIn("Turn-0 baseline", output)

    def test_cmd_search(self):
        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            cmd_search(argparse.Namespace(query="git pull request", limit=2))
        output = captured_out.getvalue()
        self.assertIn("create_pull_request", output)

    def test_cmd_doctor(self):
        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            cmd_doctor(argparse.Namespace(config=""))
        output = captured_out.getvalue()
        self.assertIn("mcp-mesh doctor", output)
        self.assertIn("Runtime", output)


if __name__ == "__main__":
    unittest.main()
