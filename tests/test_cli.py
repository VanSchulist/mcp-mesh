"""Unit tests for mcp_mesh/cli.py and shell completions.
"""

from __future__ import annotations

import argparse
import io
import sys
import unittest
from unittest.mock import patch

from mcp_mesh.cli import (
    cmd_completion,
    cmd_demo,
    cmd_doctor,
    cmd_search,
    cmd_stats,
    load_demo_tools,
)
from mcp_mesh.completion import generate_completion_script


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

    def test_cmd_completion_bash(self):
        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            cmd_completion(argparse.Namespace(shell="bash"))
        output = captured_out.getvalue()
        self.assertIn("_mcp_mesh_completion()", output)
        self.assertIn("complete -F _mcp_mesh_completion mcp-mesh", output)
        self.assertIn("run stats search inspect doctor sse monitor demo completion", output)

    def test_cmd_completion_zsh(self):
        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            cmd_completion(argparse.Namespace(shell="zsh"))
        output = captured_out.getvalue()
        self.assertIn("#compdef mcp-mesh", output)
        self.assertIn("_describe -t commands", output)
        self.assertIn("'completion:Generate shell auto-completion scripts'", output)

    def test_cmd_completion_powershell(self):
        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            cmd_completion(argparse.Namespace(shell="powershell"))
        output = captured_out.getvalue()
        self.assertIn("Register-ArgumentCompleter -Native -CommandName mcp-mesh", output)
        self.assertIn("System.Management.Automation.CompletionResult", output)

    def test_cmd_completion_pwsh(self):
        captured_out = io.StringIO()
        with patch("sys.stdout", captured_out):
            cmd_completion(argparse.Namespace(shell="pwsh"))
        output = captured_out.getvalue()
        self.assertIn("Register-ArgumentCompleter -Native -CommandName mcp-mesh", output)

    def test_cmd_completion_invalid_shell(self):
        captured_err = io.StringIO()
        with patch("sys.stderr", captured_err), self.assertRaises(SystemExit):
            cmd_completion(argparse.Namespace(shell="fish"))
        err_output = captured_err.getvalue()
        self.assertIn("Unsupported shell", err_output)

    def test_generate_completion_script_unsupported(self):
        with self.assertRaises(ValueError):
            generate_completion_script("unsupported_shell")


if __name__ == "__main__":
    unittest.main()
