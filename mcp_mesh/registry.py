"""Downstream MCP server manager, process supervisor, and configuration loader.
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .core import (
    DOWNSTREAM_TIMEOUT,
    INTERNAL_ERROR,
    SERVER_NOT_FOUND,
    TOOL_NOT_FOUND,
    DownstreamServerConfig,
    JSONRPCRequest,
    JSONRPCResponse,
    ToolDefinition,
)
from .indexer import ToolIndexer


class DownstreamProcessHandler:
    """Manages an individual downstream MCP server process running over stdio.
    
    Features production-grade reliability:
    - Dedicated, single long-lived stdout reader thread per active child process
    - Non-blocking stderr drainer to prevent OS pipe buffer deadlocks (Windows 4KB / Linux 64KB)
    - JSON-RPC ID-based response routing to prevent response mismatch from late/stale responses
    - Reentrant locking (RLock) to prevent self-deadlock on failure handling
    - Reliable process termination, pipe closure, and thread reaping on stop/timeout
    - Circuit breaker to prevent process thrashing when a service is persistently broken
    """

    def __init__(self, config: DownstreamServerConfig) -> None:
        self.config = config
        self.process: Optional[subprocess.Popen[str]] = None
        self._lock = threading.RLock()
        self._request_counter = 0

        # Dedicated I/O worker threads per active process
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Response routing: req_id -> queue.Queue[Dict[str, Any]]
        self._pending_lock = threading.Lock()
        self._pending_requests: Dict[str, queue.Queue[Dict[str, Any]]] = {}

        # Diagnostic ring buffer for stderr output (keeps last 50 lines)
        self._stderr_lines: List[str] = []
        self._stderr_lock = threading.Lock()

        # Circuit breaker settings
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        self.circuit_open_until = 0.0
        self.circuit_cooldown_seconds = 15.0
        self.last_crash_time: Optional[float] = None

    def start(self) -> bool:
        """Spawns the downstream subprocess and initializes I/O reader threads."""
        with self._lock:
            if self.process is not None and self.process.poll() is None:
                return True  # Already running

            # Clean up any dead process artifacts before starting anew
            self._cleanup_process()

            cmd = [self.config.command] + self.config.args
            env = os.environ.copy()
            env.update(self.config.env)

            try:
                self._stop_event.clear()
                self.process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.config.cwd,
                    env=env,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )
            except Exception as e:
                sys.stderr.write(f"[mcp-mesh] Failed to start server {self.config.id}: {e}\n")
                return False

            # Start exactly ONE dedicated stdout reader thread
            self._stdout_thread = threading.Thread(
                target=self._stdout_worker,
                name=f"mcp-mesh-stdout-{self.config.id}",
                daemon=True,
            )
            self._stdout_thread.start()

            # Start exactly ONE dedicated stderr drainer thread
            self._stderr_thread = threading.Thread(
                target=self._stderr_worker,
                name=f"mcp-mesh-stderr-{self.config.id}",
                daemon=True,
            )
            self._stderr_thread.start()

            return True

    def is_running(self) -> bool:
        """Checks whether the downstream process is currently alive."""
        return self.process is not None and self.process.poll() is None

    def _stdout_worker(self) -> None:
        """Dedicated stdout reader thread routing JSON-RPC responses to pending callers."""
        proc = self.process
        if not proc or not proc.stdout:
            return

        stdout_pipe = proc.stdout
        try:
            while not self._stop_event.is_set():
                line = stdout_pipe.readline()
                if not line:
                    # EOF: child process closed stdout or terminated
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    # Ignore non-JSON log lines from downstream tool stdout
                    continue

                # Match by JSON-RPC ID
                req_id = data.get("id")
                if req_id is not None:
                    req_id_str = str(req_id)
                    with self._pending_lock:
                        q = self._pending_requests.pop(req_id_str, None)
                    if q is not None:
                        try:
                            q.put_nowait(data)
                        except Exception:
                            pass
                    else:
                        # Late response for already timed-out request or unrecognized ID:
                        # Discard safely to prevent protocol poisoning of future requests
                        pass
                else:
                    # Notification or un-ID'd payload from downstream server
                    pass
        except Exception:
            pass
        finally:
            # Process terminated or pipe broken: notify all remaining pending callers
            self._notify_pending_callers_of_eof()

    def _notify_pending_callers_of_eof(self) -> None:
        """Notifies all callers waiting for responses that the child process closed connection."""
        with self._pending_lock:
            for req_id, q in list(self._pending_requests.items()):
                try:
                    q.put_nowait({
                        "error": {
                            "code": INTERNAL_ERROR,
                            "message": f"Downstream server '{self.config.id}' connection closed unexpectedly.",
                        }
                    })
                except Exception:
                    pass
            self._pending_requests.clear()

    def _stderr_worker(self) -> None:
        """Dedicated stderr drainer thread preventing pipe buffer deadlock."""
        proc = self.process
        if not proc or not proc.stderr:
            return

        stderr_pipe = proc.stderr
        try:
            while not self._stop_event.is_set():
                line = stderr_pipe.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    with self._stderr_lock:
                        self._stderr_lines.append(line)
                        if len(self._stderr_lines) > 50:
                            self._stderr_lines.pop(0)
        except Exception:
            pass

    def _read_line_with_timeout(self, timeout: float) -> Optional[str]:
        """Legacy helper maintained for test harness compatibility."""
        if not self.process or not self.process.stdout:
            return None
        try:
            return self.process.stdout.readline()
        except Exception:
            return None

    def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> bool:
        """Sends a JSON-RPC notification (no ID) to downstream process without waiting for response."""
        with self._lock:
            if not self.is_running():
                if not self.start():
                    return False
            req = {"jsonrpc": "2.0", "method": method, "params": params or {}}
            payload = json.dumps(req) + "\n"
            try:
                assert self.process and self.process.stdin
                self.process.stdin.write(payload)
                self.process.stdin.flush()
                return True
            except Exception:
                return False

    def send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Sends a JSON-RPC request to the downstream process with watchdog and circuit breaker."""
        now = time.time()
        # 1. Circuit Breaker check
        if now < self.circuit_open_until:
            remaining = round(self.circuit_open_until - now, 1)
            return {
                "error": {
                    "code": INTERNAL_ERROR,
                    "message": f"Circuit breaker open for server '{self.config.id}'. Cooling down for {remaining}s.",
                }
            }

        # 2. Self-Healing / Auto-Restart and write under lock
        with self._lock:
            if not self.is_running():
                if not self.start():
                    self._record_failure()
                    return {
                        "error": {
                            "code": INTERNAL_ERROR,
                            "message": f"Server '{self.config.id}' is offline and could not be started.",
                        }
                    }

            self._request_counter += 1
            req_id = f"{self.config.id}-{self._request_counter}"
            req = JSONRPCRequest(method=method, params=params, id=req_id)
            payload = json.dumps(req.to_dict()) + "\n"

            # Register dedicated response queue before sending to prevent race condition
            response_queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=1)
            with self._pending_lock:
                self._pending_requests[req_id] = response_queue

            try:
                assert self.process and self.process.stdin
                self.process.stdin.write(payload)
                self.process.stdin.flush()
            except Exception as e:
                with self._pending_lock:
                    self._pending_requests.pop(req_id, None)
                self.stop()
                self._record_failure()
                return {
                    "error": {
                        "code": INTERNAL_ERROR,
                        "message": f"Write to server '{self.config.id}' failed: {e}. Process killed for restart.",
                    }
                }

        # 3. Wait for response outside _lock (allows concurrent callers and stop() to run)
        try:
            response = response_queue.get(timeout=timeout)
        except queue.Empty:
            # Clean up pending registration
            with self._pending_lock:
                self._pending_requests.pop(req_id, None)

            # Record failure
            self._record_failure()

            # Terminate the hung process so it doesn't linger or block downstream resources
            self.stop()

            # Check if stderr captured any helpful context
            with self._stderr_lock:
                last_err = self._stderr_lines[-1] if self._stderr_lines else ""
            err_suffix = f" (stderr: {last_err})" if last_err else ""

            return {
                "error": {
                    "code": DOWNSTREAM_TIMEOUT,
                    "message": f"Downstream server '{self.config.id}' timed out after {timeout}s.{err_suffix}",
                }
            }

        # 4. Check if response is an EOF/connection closed error from the reader worker
        if "error" in response and "connection closed unexpectedly" in response.get("error", {}).get("message", ""):
            self._record_failure()
            self.stop()
            return response

        # Successful response: reset circuit breaker
        self.consecutive_failures = 0
        return response

    def _record_failure(self) -> None:
        """Increments consecutive failures and trips circuit breaker if threshold reached."""
        self.consecutive_failures += 1
        self.last_crash_time = time.time()
        if self.consecutive_failures >= self.max_consecutive_failures:
            self.circuit_open_until = time.time() + self.circuit_cooldown_seconds
            sys.stderr.write(
                f"[mcp-mesh] Circuit breaker TRIPPED for '{self.config.id}' "
                f"({self.consecutive_failures} failures). Cooling down for {self.circuit_cooldown_seconds}s.\n"
            )

    def _cleanup_process(self) -> None:
        """Internal helper to safely terminate child process, close pipes, and reap threads."""
        self._stop_event.set()
        proc = self.process
        self.process = None

        if proc is not None:
            # 1. Close stdin to signal EOF to child
            if proc.stdin:
                try:
                    proc.stdin.close()
                except Exception:
                    pass

            # 2. Terminate process (SIGTERM / TerminateProcess)
            try:
                proc.terminate()
                proc.wait(timeout=0.5)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=0.5)
                except Exception:
                    pass

            # 3. Close stdout and stderr pipes
            if proc.stdout:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
            if proc.stderr:
                try:
                    proc.stderr.close()
                except Exception:
                    pass

        # 4. Join reader threads with short timeout
        if self._stdout_thread and self._stdout_thread.is_alive():
            if self._stdout_thread != threading.current_thread():
                self._stdout_thread.join(timeout=0.5)
        if self._stderr_thread and self._stderr_thread.is_alive():
            if self._stderr_thread != threading.current_thread():
                self._stderr_thread.join(timeout=0.5)

        self._stdout_thread = None
        self._stderr_thread = None

        # 5. Notify all remaining waiting callers
        self._notify_pending_callers_of_eof()

    def stop(self) -> None:
        """Terminates the child process and frees all associated threads and pipes."""
        with self._lock:
            self._cleanup_process()

    def get_health(self) -> Dict[str, Any]:
        """Returns health diagnostics for this downstream server."""
        with self._lock:
            running = self.is_running()
            pid = self.process.pid if running and self.process else None
            now = time.time()
            circuit_open = now < self.circuit_open_until
            with self._stderr_lock:
                last_stderr = self._stderr_lines[-1] if self._stderr_lines else None
            return {
                "server_id": self.config.id,
                "running": running,
                "pid": pid,
                "consecutive_failures": self.consecutive_failures,
                "circuit_breaker_open": circuit_open,
                "cooldown_remaining_s": round(max(0.0, self.circuit_open_until - now), 1) if circuit_open else 0.0,
                "last_stderr": last_stderr,
            }


class DownstreamRegistry:
    """Manages the catalog of downstream MCP servers, their active processes, and tool discovery."""

    def __init__(self, indexer: Optional[ToolIndexer] = None) -> None:
        self.indexer = indexer or ToolIndexer()
        self.configs: Dict[str, DownstreamServerConfig] = {}
        self.handlers: Dict[str, DownstreamProcessHandler] = {}
        # In-memory mock dispatch handlers for testing / embedded execution
        self.mock_dispatchers: Dict[str, Callable[[str, Dict[str, Any]], Any]] = {}

        atexit.register(self.shutdown_all)

    def register_server_config(self, config: DownstreamServerConfig) -> None:
        """Registers a server configuration."""
        self.configs[config.id] = config
        self.handlers[config.id] = DownstreamProcessHandler(config)

    def register_mock_server(
        self,
        server_id: str,
        tools: List[ToolDefinition],
        dispatcher: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ) -> None:
        """Registers an in-memory or simulated downstream server with pre-defined tools."""
        self.configs[server_id] = DownstreamServerConfig(
            id=server_id,
            command="mock",
            description=f"In-memory simulated server {server_id}",
        )
        if dispatcher:
            self.mock_dispatchers[server_id] = dispatcher
        
        for tool in tools:
            tool.server_id = server_id
            self.indexer.register_tool(tool)

    def load_config_file(self, config_path: str) -> int:
        """Loads server definitions from a configuration file.
        
        Supports both mcp-mesh native config and Claude/Cursor mcpServers standard JSON.
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        servers_data: Dict[str, Any] = {}
        if "mcpServers" in data:
            servers_data = data["mcpServers"]
        elif "servers" in data:
            servers_data = data["servers"]
        elif isinstance(data, dict):
            servers_data = data

        count = 0
        for server_id, cfg in servers_data.items():
            if not isinstance(cfg, dict):
                continue
            cmd = cfg.get("command", "")
            if not cmd:
                continue
            args = cfg.get("args", [])
            env = cfg.get("env", {})
            cwd = cfg.get("cwd", None)
            desc = cfg.get("description", f"Downstream MCP Server: {server_id}")

            server_cfg = DownstreamServerConfig(
                id=server_id,
                command=cmd,
                args=args,
                env=env,
                cwd=cwd,
                description=desc,
            )
            self.register_server_config(server_cfg)
            count += 1

        return count

    def discover_tools_from_server(self, server_id: str) -> List[ToolDefinition]:
        """Queries a downstream server via MCP tools/list and registers discovered tools."""
        handler = self.handlers.get(server_id)
        if not handler:
            return []

        # Send initialize handshake if needed
        init_res = handler.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-mesh-gateway", "version": "1.0.0"}
        })
        if "error" in init_res:
            sys.stderr.write(f"[mcp-mesh] Init error for {server_id}: {init_res['error']}\n")
            return []

        handler.send_notification("notifications/initialized", {})

        # Request tools list
        res = handler.send_request("tools/list", {})
        if "error" in res or "result" not in res:
            sys.stderr.write(f"[mcp-mesh] tools/list error for {server_id}: {res.get('error')}\n")
            return []

        raw_tools = res["result"].get("tools", [])
        discovered: List[ToolDefinition] = []

        for rt in raw_tools:
            name = rt.get("name", "")
            desc = rt.get("description", "")
            schema = rt.get("inputSchema", {})
            category = rt.get("category", "general")

            tool_def = ToolDefinition(
                name=name,
                server_id=server_id,
                description=desc,
                input_schema=schema,
                category=category,
            )
            self.indexer.register_tool(tool_def)
            discovered.append(tool_def)

        return discovered

    def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Routes a tool execution request to the appropriate downstream server."""
        # 1. Check in-memory / mock dispatchers
        if server_id in self.mock_dispatchers:
            try:
                res = self.mock_dispatchers[server_id](tool_name, arguments)
                return {"result": {"content": [{"type": "text", "text": str(res)}]}}
            except Exception as e:
                return {"error": {"code": INTERNAL_ERROR, "message": f"Execution failed: {str(e)}"}}

        # 2. Check live stdio handler
        handler = self.handlers.get(server_id)
        if not handler:
            return {
                "error": {
                    "code": SERVER_NOT_FOUND,
                    "message": f"Server '{server_id}' not registered in mcp-mesh.",
                }
            }

        # Send tools/call to downstream server
        response = handler.send_request(
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
        )
        return response

    def shutdown_all(self) -> None:
        """Stops all running downstream processes."""
        for handler in self.handlers.values():
            handler.stop()
