"""
Federated Heterogeneous MCP Server Ingestion & Unified Tool Gateway.
Discovers upstream MCP servers from client configs (Antigravity, Claude, Cursor),
runs concurrent schema discovery over stdio, and provides predictive process pre-warming.
Zero external dependencies (uses standard library concurrent.futures, pathlib, json, os).
"""

from __future__ import annotations

import os
import sys
import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from .core import DownstreamServerConfig, ToolDefinition
from .registry import DownstreamRegistry


def discover_system_mcp_configs() -> Dict[str, Path]:
    """
    Auto-discovers standard MCP client configuration files on the local machine.
    Supports Google Antigravity, Claude Desktop, Cursor, and VSCode extensions.
    """
    found: Dict[str, Path] = {}
    home = Path.home()

    # 1. Google Antigravity
    antigravity_cfg = home / ".gemini" / "config" / "mcp_config.json"
    if antigravity_cfg.exists():
        found["antigravity"] = antigravity_cfg

    # 2. Claude Desktop
    claude_paths = [
        home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",  # Windows
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",  # macOS
        home / ".config" / "Claude" / "claude_desktop_config.json",  # Linux
    ]
    for cp in claude_paths:
        if cp.exists():
            found["claude_desktop"] = cp
            break

    # 3. Cursor
    cursor_paths = [
        home / ".cursor" / "mcp.json",
        home / "AppData" / "Roaming" / "Cursor" / "mcp.json",
    ]
    for curp in cursor_paths:
        if curp.exists():
            found["cursor"] = curp
            break

    # 4. Global mcp-mesh config
    mesh_cfg = home / ".mcp-mesh" / "servers.json"
    if mesh_cfg.exists():
        found["mesh_global"] = mesh_cfg

    return found


def is_mesh_gateway_command(command: str, args: List[str]) -> bool:
    """
    Detects if a server entry points to mcp-mesh itself to prevent circular proxy loops.
    """
    full_cmd = (command + " " + " ".join(args)).lower()
    if "mcp-mesh" in full_cmd or "mcp_mesh" in full_cmd:
        return True
    return False


class FederationManager:
    """
    Federates multiple upstream MCP servers into a single mcp-mesh gateway.
    Features:
      - Automatic system configuration aggregation
      - Circular loop prevention
      - Concurrent upstream tool schema discovery
      - Predictive background process pre-warming
    """

    def __init__(self, registry: Optional[DownstreamRegistry] = None):
        self.registry = registry or DownstreamRegistry()
        self.federated_sources: Dict[str, Path] = {}
        self.prewarmed_servers: Set[str] = set()
        self._prewarm_lock = threading.Lock()

    def load_federated_servers(
        self,
        auto_discover: bool = True,
        custom_configs: Optional[List[str | Path]] = None,
    ) -> Dict[str, int]:
        """
        Discovers and registers server configurations from client settings.
        Returns a dict of {source_name: registered_server_count}.
        """
        sources_to_read: Dict[str, Path] = {}
        if auto_discover:
            sources_to_read.update(discover_system_mcp_configs())

        if custom_configs:
            for i, p in enumerate(custom_configs):
                path_obj = Path(p)
                if path_obj.exists():
                    sources_to_read[f"custom_{i+1}"] = path_obj

        results: Dict[str, int] = {}

        for src_name, cfg_path in sources_to_read.items():
            self.federated_sources[src_name] = cfg_path
            count = 0
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                servers_data = {}
                if "mcpServers" in data:
                    servers_data = data["mcpServers"]
                elif "servers" in data:
                    servers_data = data["servers"]
                elif isinstance(data, dict):
                    servers_data = data

                for server_id, cfg in servers_data.items():
                    if not isinstance(cfg, dict):
                        continue

                    cmd = cfg.get("command", "").strip()
                    if not cmd:
                        continue
                    args = cfg.get("args", [])
                    env = cfg.get("env", {})
                    cwd = cfg.get("cwd", None)
                    desc = cfg.get("description", f"Federated upstream: {server_id}")

                    # Prevent circular loops (never proxy mcp-mesh into mcp-mesh)
                    if is_mesh_gateway_command(cmd, args):
                        continue

                    # Namespace server_id if conflict arises
                    canonical_id = server_id
                    if canonical_id in self.registry.configs:
                        canonical_id = f"{server_id}_{src_name}"

                    server_cfg = DownstreamServerConfig(
                        id=canonical_id,
                        command=cmd,
                        args=args,
                        env=env,
                        cwd=cwd,
                        description=desc,
                    )
                    self.registry.register_server_config(server_cfg)
                    count += 1
            except Exception as e:
                sys.stderr.write(f"[mcp-mesh-federation] Failed to read {src_name} ({cfg_path}): {e}\n")

            results[src_name] = count

        return results

    def discover_all_tools(
        self,
        parallel: bool = True,
        max_workers: int = 4,
        timeout: float = 8.0,
    ) -> Dict[str, List[ToolDefinition]]:
        """
        Queries tools/list across all federated upstream servers concurrently.
        Registers discovered tools in the unified BM25 indexer.
        """
        servers_to_query = list(self.registry.configs.keys())
        if not servers_to_query:
            return {}

        results: Dict[str, List[ToolDefinition]] = {}

        if not parallel or len(servers_to_query) == 1:
            for s_id in servers_to_query:
                try:
                    tools = self.registry.discover_tools_from_server(s_id)
                    results[s_id] = tools
                except Exception as e:
                    sys.stderr.write(f"[mcp-mesh-federation] Discovery failed for {s_id}: {e}\n")
                    results[s_id] = []
            return results

        def _worker(server_id: str) -> Tuple[str, List[ToolDefinition]]:
            try:
                tools = self.registry.discover_tools_from_server(server_id)
                return server_id, tools
            except Exception as e:
                sys.stderr.write(f"[mcp-mesh-federation] Async discovery error for {server_id}: {e}\n")
                return server_id, []

        with ThreadPoolExecutor(max_workers=min(max_workers, len(servers_to_query))) as executor:
            futures = {executor.submit(_worker, s_id): s_id for s_id in servers_to_query}
            for fut in as_completed(futures):
                s_id = futures[fut]
                try:
                    server_id, tools = fut.result(timeout=timeout)
                    results[server_id] = tools
                except Exception as e:
                    sys.stderr.write(f"[mcp-mesh-federation] Timeout/error discovering {s_id}: {e}\n")
                    results[s_id] = []

        return results

    def prewarm_server(self, server_id: str) -> bool:
        """
        Initiates a non-blocking background spawn and handshake for an upstream server.
        """
        with self._prewarm_lock:
            if server_id in self.prewarmed_servers:
                return True
            if server_id in self.registry.mock_dispatchers or (
                server_id in self.registry.configs and self.registry.configs[server_id].command == "mock"
            ):
                self.prewarmed_servers.add(server_id)
                return True
            handler = self.registry.handlers.get(server_id)
            if not handler:
                if server_id in self.registry.configs:
                    handler = self.registry.handlers.setdefault(server_id, self.registry.handlers.get(server_id))
                if not handler:
                    return False

            if handler.is_running():
                self.prewarmed_servers.add(server_id)
                return True

            def _spawn():
                try:
                    handler.start()
                    # Perform lightweight ping or initialize
                    handler.send_request("ping", {}, timeout=3.0)
                except Exception:
                    pass

            t = threading.Thread(target=_spawn, daemon=True)
            t.start()
            self.prewarmed_servers.add(server_id)
            return True

    def predictive_prewarm_candidates(self, candidate_tools: List[Tuple[ToolDefinition, float]]) -> None:
        """
        Given the top candidate tools returned from a BM25 natural language search,
        pre-warms the upstream servers in the background.
        """
        servers = {tool.server_id for tool, _ in candidate_tools[:2]}
        for s_id in servers:
            self.prewarm_server(s_id)
