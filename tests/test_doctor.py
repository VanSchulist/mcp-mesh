"""Unit tests for mcp-mesh doctor diagnostic health checker."""

from __future__ import annotations

import os
import tempfile
import unittest
from mcp_mesh.doctor import HealthCheckItem, MCPDoctor


class TestMCPDoctor(unittest.TestCase):
    """Test suite for MCPDoctor system and upstream server diagnostics."""

    def test_health_check_item(self) -> None:
        item = HealthCheckItem(
            category="Test",
            name="CheckItem",
            status="OK",
            message="All good",
            latency_ms=1.5,
        )
        self.assertEqual(item.category, "Test")
        self.assertEqual(item.status, "OK")
        self.assertEqual(item.latency_ms, 1.5)

    def test_doctor_without_config(self) -> None:
        doctor = MCPDoctor(config_path=None)
        results = doctor.run_all()
        self.assertTrue(len(results) > 0)
        
        # Verify python runtime check exists and passes
        py_checks = [r for r in results if r.name == "Python Version"]
        self.assertEqual(len(py_checks), 1)
        self.assertEqual(py_checks[0].status, "OK")

        # Verify report string generation
        report = doctor.format_report()
        self.assertIn("mcp-mesh doctor", report)
        self.assertIn("Diagnostic Summary", report)

    def test_doctor_with_valid_config(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("""{
                "mcpServers": {
                    "test_srv": {
                        "command": "python",
                        "args": ["-c", "print('hello')"]
                    }
                }
            }""")
            config_path = f.name

        try:
            doctor = MCPDoctor(config_path=config_path)
            results = doctor.run_all()
            srv_checks = [r for r in results if "test_srv" in r.name]
            self.assertTrue(len(srv_checks) > 0)
        finally:
            if os.path.exists(config_path):
                os.remove(config_path)

    def test_doctor_with_invalid_config(self) -> None:
        doctor = MCPDoctor(config_path="non_existent_config_file_12345.json")
        results = doctor.run_all()
        config_fails = [r for r in results if r.status == "FAIL" and "Config File" in r.name]
        self.assertEqual(len(config_fails), 1)
        self.assertTrue(doctor.has_errors)


if __name__ == "__main__":
    unittest.main()
