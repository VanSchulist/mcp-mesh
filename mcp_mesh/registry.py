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
    
    Features LiteLLM-style resilience:
    - Threaded timeout watchdog to prevent hanging child processes
    - Automatic crash recovery and process self-healing
    - Circuit breaker to prevent process thrashing when a service is persistently broken
    """

    def __init__(self, config: DownstreamServerConfig) -> None:
        self.config = config
        self.process: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()
        self._request_counter = 0
        # Circuit breaker settings
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        self.circuit_open_until = 0.0
        self.circuit_cooldown_seconds = 15.0
        self.last_crash_time: Optional[float] = None

    def start(self) -> bool:
        """Spawns the downstream subprocess."""
        with self._lock:
            if self.process is not None and self.process.poll() is None:
                return True  # Already running
            
            cmd = [self.config.command] + self.config.args
            env = os.environ.copy()
            env.update(self.config.env)

            try:
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
                return True
            except Exception as e:
                sys.stderr.write(f"[mcp-mesh] Failed to start server {self.config.id}: {e}\n")
                return False

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _read_line_with_timeout(self, timeout: float) -> Optional[str]:
        """Reads a line from stdout with a timeout watchdog to prevent gateway freezes."""
        if not self.process or not self.process.stdout:
            return None

        result_queue: queue.Queue[Optional[str]] = queue.Queue(maxsize=1)

        def _reader():
            try:
                if self.process and self.process.stdout:
                    line = self.process.stdout.readline()
                    result_queue.put(line)
            except Exception:
                result_queue.put(None)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        try:
            return result_queue.get(timeout=timeout)
        except queue.Empty:
            return None  # Timed out

    def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
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

        # 2. Self-Healing / Auto-Restart
        if not self.is_running():
            if not self.start():
                self._record_failure()
                return {"error": {"code": INTERNAL_ERROR, "message": f"Server '{self.config.id}' is offline and could not be started."}}

        with self._lock:
            self._request_counter += 1
            req_id = f"{self.config.id}-{self._request_counter}"
            req = JSONRPCRequest(method=method, params=params, id=req_id)
            payload = json.dumps(req.to_dict()) + "\n"

            try:
                assert self.process and self.process.stdin
                self.process.stdin.write(payload)
                self.process.stdin.flush()
            except Exception as e:
                self.stop()
                self._record_failure()
                return {"error": {"code": INTERNAL_ERROR, "message": f"Write to server '{self.config.id}' failed: {e}. Process killed for restart."}}

            # 3. Read with Watchdog Timeout
            line = self._read_line_with_timeout(timeout=timeout)
            if line is None:
                # Timeout triggered or pipe broken
                if self.is_running():
                    # Process is still alive but hung: kill to protect gateway
                    self.stop()
                    self._record_failure()
                    return {
                        "error": {
                            "code": DOWNSTREAM_TIMEOUT,
                            "message": f"Downstream server '{self.config.id}' timed out after {timeout}s. Process terminated to prevent hanging.",
                        }
                    }
                else:
                    # Process died unexpectedly
                    self.stop()
                    self._record_failure()
                    return {
                        "error": {
                            "code": INTERNAL_ERROR,
                            "message": f"Downstream server '{self.config.id}' terminated unexpectedly. Auto-healing will respawn on next request.",
                        }
                    }

            line = line.strip()
            if not line:
                self.stop()
                self._record_failure()
                return {"error": {"code": INTERNAL_ERROR, "message": "Downstream process returned empty response and closed connection."}}

            try:
                data = json.loads(line)
                # Success: reset circuit breaker
                self.consecutive_failures = 0
                return data
            except json.JSONDecodeError as e:
                self._record_failure()
                return {"error": {"code": INTERNAL_ERROR, "message": f"Invalid JSON response from server '{self.config.id}': {e}"}}

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

    def stop(self) -> None:
        """Terminates the child process."""
        with self._lock:
            if self.process is not None:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=1.0)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                finally:
                    self.process = None

    def get_health(self) -> Dict[str, Any]:
        """Returns health diagnostics for this downstream server."""
        running = self.is_running()
        pid = self.process.pid if running and self.process else None
        now = time.time()
        circuit_open = now < self.circuit_open_until
        return {
            "server_id": self.config.id,
            "running": running,
            "pid": pid,
            "consecutive_failures": self.consecutive_failures,
            "circuit_breaker_open": circuit_open,
            "cooldown_remaining_s": round(max(0.0, self.circuit_open_until - now), 1) if circuit_open else 0.0,
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

        handler.send_request("notifications/initialized", {})

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
