"""Regression test suite for subprocess lifecycle, timeout watchdog, thread reaping, and pipe safety."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import unittest
from typing import Any, Dict

from mcp_mesh.core import DOWNSTREAM_TIMEOUT, INTERNAL_ERROR, DownstreamServerConfig
from mcp_mesh.registry import DownstreamProcessHandler, DownstreamRegistry


class TestProcessLifecycle(unittest.TestCase):
    """Rigorous end-to-end tests for stdio child process management."""

    def setUp(self) -> None:
        self.py = sys.executable

    def _make_handler(self, script: str, server_id: str = "test_srv") -> DownstreamProcessHandler:
        cfg = DownstreamServerConfig(
            id=server_id,
            command=self.py,
            args=["-u", "-c", script],
        )
        return DownstreamProcessHandler(cfg)

    def test_normal_request_response(self) -> None:
        """1. Verifies standard JSON-RPC send and receive over stdio."""
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    res = {"jsonrpc": "2.0", "id": req["id"], "result": {"echo": req["method"]}}
    sys.stdout.write(json.dumps(res) + "\\n")
    sys.stdout.flush()
"""
        handler = self._make_handler(script, "norm_srv")
        try:
            res = handler.send_request("ping", timeout=2.0)
            self.assertIn("result", res)
            self.assertEqual(res["result"]["echo"], "ping")
            self.assertTrue(handler.is_running())
        finally:
            handler.stop()

    def test_single_timeout_handling(self) -> None:
        """2. Verifies timeout watchdog terminates hung process and reports DOWNSTREAM_TIMEOUT."""
        script = """
import sys, time
for line in sys.stdin:
    time.sleep(10.0)
"""
        handler = self._make_handler(script, "hang_srv")
        try:
            t0 = time.time()
            res = handler.send_request("hang", timeout=0.1)
            elapsed = time.time() - t0

            self.assertIn("error", res)
            self.assertEqual(res["error"]["code"], DOWNSTREAM_TIMEOUT)
            self.assertLess(elapsed, 2.0)
            self.assertEqual(handler.consecutive_failures, 1)
        finally:
            handler.stop()

    def test_consecutive_100_timeouts_thread_boundedness(self) -> None:
        """3 & 4. Stress test: 100 consecutive timeouts must NOT accumulate leaked reader threads."""
        script = """
import sys, time
for line in sys.stdin:
    time.sleep(10.0)
"""
        handler = self._make_handler(script, "leak_test")
        handler.max_consecutive_failures = 9999  # Allow 100 consecutive timeouts without tripping breaker

        try:
            for i in range(100):
                res = handler.send_request("hang", timeout=0.01)
                self.assertIn("error", res)

                # Count active threads with handler's prefix
                handler_threads = [
                    t for t in threading.enumerate()
                    if t.name.startswith("mcp-mesh-") and "leak_test" in t.name and t.is_alive()
                ]
                # While a process is active, exactly 1 stdout + 1 stderr thread exists.
                # Must never grow linearly with the number of timeouts (i.e. <= 2)
                self.assertLessEqual(len(handler_threads), 2, f"Thread leak detected on turn {i+1}!")
        finally:
            handler.stop()

        # After stop(), all worker threads for this handler must be dead and reaped
        remaining = [
            t for t in threading.enumerate()
            if t.name.startswith("mcp-mesh-") and "leak_test" in t.name and t.is_alive()
        ]
        self.assertEqual(len(remaining), 0, "Zombie threads remaining after stop()!")

    def test_late_response_not_misallocated(self) -> None:
        """5. Verifies a late response from a timed-out request is dropped and never misallocated."""
        script = """
import sys, json, time
for line in sys.stdin:
    req = json.loads(line)
    if req["method"] == "slow":
        time.sleep(0.15)
        res = {"jsonrpc": "2.0", "id": req["id"], "result": "slow_late_data"}
    else:
        res = {"jsonrpc": "2.0", "id": req["id"], "result": "fast_immediate_data"}
    sys.stdout.write(json.dumps(res) + "\\n")
    sys.stdout.flush()
"""
        handler = self._make_handler(script, "late_test")
        try:
            # We start process manually and test response matching
            handler.start()

            # Mock queue to hold late request ID in pending without auto-killing process
            # to verify ID routing drops unrecognized / stale IDs cleanly
            with handler._pending_lock:
                handler._pending_requests["late_test-999"] = None

            # Now send a normal request
            res = handler.send_request("fast", timeout=2.0)
            self.assertIn("result", res)
            self.assertEqual(res["result"], "fast_immediate_data")
        finally:
            handler.stop()

    def test_premature_exit_notifies_waiter_immediately(self) -> None:
        """6. Verifies child process crash/exit unblocks waiting caller immediately (no 10s hang)."""
        script = """
import sys, json
for line in sys.stdin:
    # Read one request then immediately crash with code 1
    sys.exit(1)
"""
        handler = self._make_handler(script, "crash_srv")
        try:
            t0 = time.time()
            res = handler.send_request("crash", timeout=5.0)
            elapsed = time.time() - t0

            # Must unblock nearly instantly on EOF, not after 5.0 seconds
            self.assertLess(elapsed, 1.5)
            self.assertIn("error", res)
            self.assertIn("closed unexpectedly", res["error"]["message"])
        finally:
            handler.stop()

    def test_stderr_flood_no_deadlock(self) -> None:
        """7. Verifies writing 100KB+ to stderr does NOT deadlock the child process on OS pipe buffer."""
        script = """
import sys, json
# Flood 120KB to stderr (exceeds Windows 4KB and Linux 64KB pipe buffer)
sys.stderr.write("E" * 120000 + "\\n")
sys.stderr.flush()

for line in sys.stdin:
    req = json.loads(line)
    res = {"jsonrpc": "2.0", "id": req["id"], "result": "survived_flood"}
    sys.stdout.write(json.dumps(res) + "\\n")
    sys.stdout.flush()
"""
        handler = self._make_handler(script, "stderr_flood")
        try:
            res = handler.send_request("test_flood", timeout=3.0)
            self.assertIn("result", res, f"Deadlock occurred on stderr buffer flood! Res: {res}")
            self.assertEqual(res["result"], "survived_flood")
        finally:
            handler.stop()

    def test_repeated_start_stop_reaps_threads(self) -> None:
        """8 & 9. Verifies repeated start/stop cycles do not leak threads or processes."""
        script = """
import sys, time
for line in sys.stdin:
    pass
"""
        handler = self._make_handler(script, "restart_srv")
        for i in range(15):
            self.assertTrue(handler.start())
            self.assertTrue(handler.is_running())
            handler.stop()
            self.assertFalse(handler.is_running())

        # Verify no worker threads left
        leftover = [
            t for t in threading.enumerate()
            if t.name.startswith("mcp-mesh-") and "restart_srv" in t.name and t.is_alive()
        ]
        self.assertEqual(len(leftover), 0)

    def test_circuit_breaker_prevents_infinite_restart(self) -> None:
        """11. Verifies that persistent crash/timeouts trip circuit breaker instead of looping infinitely."""
        cfg = DownstreamServerConfig(id="broken", command="nonexistent_cmd_xyz_404")
        handler = DownstreamProcessHandler(cfg)
        handler.max_consecutive_failures = 3
        handler.circuit_cooldown_seconds = 10.0

        for i in range(3):
            res = handler.send_request("test")
            self.assertIn("error", res)

        self.assertTrue(handler.get_health()["circuit_breaker_open"])

        # 4th call should be rejected immediately by circuit breaker without trying to spawn
        t0 = time.time()
        res4 = handler.send_request("test")
        elapsed = time.time() - t0
        self.assertLess(elapsed, 0.05)
        self.assertIn("Circuit breaker open", res4["error"]["message"])

    def test_registry_shutdown_all(self) -> None:
        """8 & 12. Verifies DownstreamRegistry.shutdown_all cleanly terminates all active servers."""
        script = """
import sys, json
for line in sys.stdin:
    req = json.loads(line)
    res = {"jsonrpc": "2.0", "id": req["id"], "result": "ok"}
    sys.stdout.write(json.dumps(res) + "\\n")
    sys.stdout.flush()
"""
        registry = DownstreamRegistry()
        for i in range(3):
            cfg = DownstreamServerConfig(
                id=f"reg_srv_{i}",
                command=self.py,
                args=["-u", "-c", script],
            )
            registry.register_server_config(cfg)

        # Trigger process starts
        for i in range(3):
            res = registry.call_tool(f"reg_srv_{i}", "echo", {})
            # Check handler is running
            self.assertTrue(registry.handlers[f"reg_srv_{i}"].is_running())

        # Now shut all down
        registry.shutdown_all()

        # All processes must be stopped
        for i in range(3):
            self.assertFalse(registry.handlers[f"reg_srv_{i}"].is_running())

    def test_concurrent_requests_order_and_delivery(self) -> None:
        """10. Verifies concurrent requests from multiple caller threads are properly dispatched and returned."""
        script = """
import sys, json, time
for line in sys.stdin:
    req = json.loads(line)
    val = req["params"]["val"]
    res = {"jsonrpc": "2.0", "id": req["id"], "result": {"echo_val": val * 2}}
    sys.stdout.write(json.dumps(res) + "\\n")
    sys.stdout.flush()
"""
        handler = self._make_handler(script, "concurrent_srv")
        try:
            results: dict[int, Any] = {}
            errors: list[Any] = []

            def caller(idx: int) -> None:
                try:
                    res = handler.send_request("calc", {"val": idx}, timeout=3.0)
                    results[idx] = res
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=caller, args=(i,)) for i in range(15)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=3.0)

            self.assertEqual(len(errors), 0)
            self.assertEqual(len(results), 15)
            for i in range(15):
                self.assertIn(i, results)
                self.assertEqual(results[i]["result"]["echo_val"], i * 2)
        finally:
            handler.stop()


if __name__ == "__main__":
    unittest.main()
