"""The Model Context Protocol (MCP) Stdio Gateway implementation.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict, List, Optional, Union

from .core import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    SERVER_NOT_FOUND,
    TOOL_NOT_FOUND,
    JSONRPCRequest,
    JSONRPCResponse,
)
from .cache import LRUSchemaCache
from .federation import FederationManager
from .indexer import ToolIndexer
from .registry import DownstreamRegistry
from .telemetry import TelemetryLedger


class MCPMeshGateway:
    """The central MCP proxy server.
    
    Accepts standard JSON-RPC 2.0 requests over stdio from clients (Claude Desktop,
    Cursor, Antigravity) and lazily routes calls to downstream servers.
    """

    def __init__(
        self,
        registry: Optional[DownstreamRegistry] = None,
        mode: str = "lazy",
        server_name: str = "mcp-mesh",
        server_version: str = "1.3.0",
        cache_capacity: int = 8,
        db_path: Optional[str] = None,
        federate: bool = False,
        custom_configs: Optional[List[str]] = None,
        parallel_discovery: bool = True,
    ) -> None:
        self.registry = registry or DownstreamRegistry()
        self.indexer: ToolIndexer = self.registry.indexer
        self.cache = LRUSchemaCache(capacity=cache_capacity)
        self.ledger = TelemetryLedger(db_path=db_path)
        self.federation = FederationManager(registry=self.registry)
        self.mode = mode  # "lazy" or "passthrough"
        self.server_name = server_name
        self.server_version = server_version
        self.protocol_version = "2024-11-05"
        self.session_id = f"mesh-{int(time.time())}"
        self.last_invoked_tool: Optional[str] = None

        # Execute upstream server federation if enabled
        if federate or custom_configs:
            self.federation.load_federated_servers(auto_discover=federate, custom_configs=custom_configs)
            self.federation.discover_all_tools(parallel=parallel_discovery)

        # Log session startup
        metrics = self.indexer.get_metrics()
        self.ledger.start_session(
            session_id=self.session_id,
            mode=self.mode,
            server_count=metrics["total_servers"],
            tool_count=metrics["total_tools"],
        )

    def handle_message(self, line: str) -> Optional[str]:
        """Parses and executes a single incoming JSON-RPC line.
        
        Returns the JSON-RPC response string, or None for notifications.
        """
        line = line.strip()
        if not line:
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            err = JSONRPCResponse.make_error(None, PARSE_ERROR, f"Invalid JSON payload: {str(e)}")
            return err.to_json_line()

        if not isinstance(data, dict):
            err = JSONRPCResponse.make_error(None, INVALID_REQUEST, "JSON-RPC payload must be a JSON object.")
            return err.to_json_line()

        req = JSONRPCRequest.from_dict(data)

        # Handle notification (no 'id')
        is_notification = req.id is None
        response = self.dispatch_request(req)

        if is_notification or response is None:
            return None

        return response.to_json_line()

    def dispatch_request(self, req: JSONRPCRequest) -> Optional[JSONRPCResponse]:
        """Dispatches an incoming JSON-RPC request to the appropriate protocol handler."""
        method = req.method
        params = req.params if isinstance(req.params, dict) else {}

        if method == "initialize":
            return self._handle_initialize(req.id, params)
        elif method == "notifications/initialized":
            return None  # Acknowledge notification
        elif method == "ping":
            return JSONRPCResponse.make_result(req.id, {})
        elif method == "tools/list":
            return self._handle_tools_list(req.id, params)
        elif method == "tools/call":
            return self._handle_tools_call(req.id, params)
        elif method == "resources/list":
            return JSONRPCResponse.make_result(req.id, {"resources": []})
        elif method == "prompts/list":
            return JSONRPCResponse.make_result(req.id, {"prompts": []})
        else:
            return JSONRPCResponse.make_error(
                req.id,
                METHOD_NOT_FOUND,
                f"Method '{method}' not supported by mcp-mesh gateway.",
            )

    def _handle_initialize(self, req_id: Optional[Union[str, int]], params: Dict[str, Any]) -> JSONRPCResponse:
        return JSONRPCResponse.make_result(
            req_id,
            {
                "protocolVersion": self.protocol_version,
                "serverInfo": {
                    "name": self.server_name,
                    "version": self.server_version,
                },
                "capabilities": {
                    "tools": {"listChanged": True},
                    "logging": {},
                },
            },
        )

    def _handle_tools_list(self, req_id: Optional[Union[str, int]], params: Dict[str, Any]) -> JSONRPCResponse:
        if self.mode == "passthrough":
            # Direct passthrough mode: expose all downstream tool schemas (for benchmark comparisons)
            tools_list = [tool.to_mcp_dict() for tool in self.indexer.tools.values()]
            return JSONRPCResponse.make_result(req_id, {"tools": tools_list})

        # Lazy Meta-Tool Mode: Return the 4 lightweight discovery and invocation tools
        meta_tools = [
            {
                "name": "mesh_search_tools",
                "description": (
                    "Search for relevant tools across all aggregated MCP servers using natural "
                    "language keywords (e.g. 'git commit', 'read file', 'query postgres'). "
                    "Returns ultra-compact signatures and relevance scores."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Keywords or functional goal describing the desired tool.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum candidate tools to return (default: 5).",
                            "default": 5,
                        },
                        "server": {
                            "type": "string",
                            "description": "Optional downstream server ID to restrict search.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "mesh_describe_tool",
                "description": (
                    "Inspect the full JSON schema and detailed parameter specifications of a specific "
                    "tool before invoking it."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "server": {
                            "type": "string",
                            "description": "The downstream server ID hosting the tool.",
                        },
                        "tool_name": {
                            "type": "string",
                            "description": "The target tool name to inspect.",
                        },
                    },
                    "required": ["server", "tool_name"],
                },
            },
            {
                "name": "mesh_invoke_tool",
                "description": (
                    "Directly execute any tool on a downstream MCP server. Pass server ID, "
                    "target tool name, and input arguments dictionary."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "server": {
                            "type": "string",
                            "description": "The downstream server ID (e.g. 'github', 'postgres'). Optional if tool_name is namespaced as 'server::tool'.",
                        },
                        "tool_name": {
                            "type": "string",
                            "description": "The exact tool name to execute.",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "JSON arguments matching the tool's parameter schema.",
                            "default": {},
                        },
                    },
                    "required": ["tool_name"],
                },
            },
            {
                "name": "mesh_status",
                "description": (
                    "Inspect real-time gateway statistics: connected downstream servers, "
                    "total tools indexed, and estimated context token savings."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

        return JSONRPCResponse.make_result(req_id, {"tools": meta_tools})

    def _handle_tools_call(self, req_id: Optional[Union[str, int]], params: Dict[str, Any]) -> JSONRPCResponse:
        name = params.get("name", "")
        args = params.get("arguments", {})
        if not isinstance(args, dict):
            args = {}

        if name == "mesh_search_tools":
            return self._exec_mesh_search(req_id, args)
        elif name == "mesh_describe_tool":
            return self._exec_mesh_describe(req_id, args)
        elif name == "mesh_invoke_tool":
            return self._exec_mesh_invoke(req_id, args)
        elif name == "mesh_status":
            return self._exec_mesh_status(req_id)
        else:
            # Fallback: Check if tool name matches directly (e.g. client called 'my_tool' or 'server::my_tool')
            tool = self.indexer.get_tool(name)
            if tool:
                result = self.registry.call_tool(tool.server_id, tool.name, args)
                if "error" in result:
                    err = result["error"]
                    return JSONRPCResponse.make_error(req_id, err.get("code", INTERNAL_ERROR), err.get("message", "Tool execution error"))
                return JSONRPCResponse.make_result(req_id, result.get("result", {}))
            
            return JSONRPCResponse.make_error(
                req_id,
                TOOL_NOT_FOUND,
                f"Tool '{name}' not found. Use 'mesh_search_tools' to discover available tools.",
            )

    def _exec_mesh_search(self, req_id: Optional[Union[str, int]], args: Dict[str, Any]) -> JSONRPCResponse:
        query = args.get("query", "")
        limit = int(args.get("limit", 5))
        server_filter = args.get("server")

        if not query:
            return JSONRPCResponse.make_error(req_id, INVALID_PARAMS, "'query' parameter is required.")

        matches = self.indexer.search(query=query, limit=limit, server_filter=server_filter)

        if not matches:
            text_out = f"No matching tools found for query: '{query}'. Use 'mesh_status' to check registered servers."
        else:
            # Predictive pre-warm: background spawn for top match servers
            try:
                self.federation.predictive_prewarm_candidates(matches)
            except Exception:
                pass

            lines = [f"Found {len(matches)} matching tool(s):"]
            for tool, score in matches:
                self.cache.put(tool)  # Warm up LRU hot-tier cache
                lines.append(f"- [{tool.server_id}] {tool.name} (relevance: {score})")
                lines.append(f"  Signature: {tool.to_compact_signature()}")
                lines.append(f"  Invoke via: mesh_invoke_tool(server='{tool.server_id}', tool_name='{tool.name}', arguments={{...}})")
            text_out = "\n".join(lines)

        return JSONRPCResponse.make_result(
            req_id,
            {"content": [{"type": "text", "text": text_out}]},
        )

    def _exec_mesh_describe(self, req_id: Optional[Union[str, int]], args: Dict[str, Any]) -> JSONRPCResponse:
        server = args.get("server", "")
        tool_name = args.get("tool_name", "")

        if not tool_name:
            return JSONRPCResponse.make_error(req_id, INVALID_PARAMS, "'tool_name' is required.")

        # Auto-resolve server if missing
        if not server:
            if "::" in tool_name:
                server, tool_name = tool_name.split("::", 1)
            else:
                tool_match = self.indexer.get_tool(tool_name)
                if tool_match:
                    server = tool_match.server_id

        if not server:
            return JSONRPCResponse.make_error(req_id, INVALID_PARAMS, f"Could not resolve server for tool '{tool_name}'.")

        tool_key = f"{server}::{tool_name}"
        # 1. Check LRU Hot-Tier Cache first
        tool = self.cache.get(tool_key)
        if not tool:
            # 2. Fall back to indexer
            tool = self.indexer.get_tool(tool_key)
            if tool:
                self.cache.put(tool)

        if not tool:
            return JSONRPCResponse.make_error(req_id, TOOL_NOT_FOUND, f"Tool '{tool_name}' on server '{server}' not found.")

        schema_text = json.dumps(tool.to_mcp_dict(), indent=2)
        return JSONRPCResponse.make_result(
            req_id,
            {"content": [{"type": "text", "text": schema_text}]},
        )

    def _exec_mesh_invoke(self, req_id: Optional[Union[str, int]], args: Dict[str, Any]) -> JSONRPCResponse:
        server = args.get("server", "")
        tool_name = args.get("tool_name", "")
        tool_args = args.get("arguments", {})

        if not tool_name:
            return JSONRPCResponse.make_error(req_id, INVALID_PARAMS, "'tool_name' is required.")

        # Auto-resolve server if missing or formatted as 'server::tool'
        if not server:
            if "::" in tool_name:
                server, tool_name = tool_name.split("::", 1)
            else:
                tool_match = self.indexer.get_tool(tool_name)
                if tool_match:
                    server = tool_match.server_id

        if not server:
            return JSONRPCResponse.make_error(req_id, INVALID_PARAMS, f"Could not determine downstream server for tool '{tool_name}'.")

        start_t = time.perf_counter()
        tool_key = f"{server}::{tool_name}"
        cached_tool = self.cache.get(tool_key)
        cache_hit = cached_tool is not None
        if not cached_tool:
            tool = self.indexer.get_tool(tool_key)
            if tool:
                self.cache.put(tool)

        res = self.registry.call_tool(server, tool_name, tool_args)
        latency_ms = (time.perf_counter() - start_t) * 1000.0

        metrics = self.indexer.get_metrics()
        success = "error" not in res
        err_msg = res.get("error", {}).get("message") if not success else None

        # Record call in persistent SQLite telemetry ledger
        self.ledger.log_call(
            server_id=server,
            tool_name=tool_name,
            latency_ms=latency_ms,
            success=success,
            cache_hit=cache_hit,
            tokens_baseline=metrics["raw_tool_tokens"],
            tokens_mesh=metrics["gateway_meta_tokens"],
            tokens_saved=metrics["tokens_saved"],
            session_id=self.session_id,
            error_message=err_msg,
        )

        # Record tool co-occurrence in telemetry ledger
        if self.last_invoked_tool and self.last_invoked_tool != tool_key:
            self.ledger.log_tool_transition(self.last_invoked_tool, tool_key)
        self.last_invoked_tool = tool_key

        if not success:
            err = res["error"]
            return JSONRPCResponse.make_error(
                req_id,
                err.get("code", INTERNAL_ERROR),
                err.get("message", "Tool execution failed on downstream server"),
            )

        return JSONRPCResponse.make_result(req_id, res.get("result", {}))

    def _exec_mesh_status(self, req_id: Optional[Union[str, int]]) -> JSONRPCResponse:
        metrics = self.indexer.get_metrics()
        cache_stats = self.cache.get_stats()
        telemetry_summary = self.ledger.get_summary()
        sources_desc = f"{len(self.federation.federated_sources)} sources" if self.federation.federated_sources else "local"
        report = (
            f"=== mcp-mesh Federated Gateway v{self.server_version} ===\n"
            f"- Connected Servers : {metrics['total_servers']} ({', '.join(metrics['server_ids']) or 'none'})\n"
            f"- Federated Sources : {sources_desc}\n"
            f"- Indexed Tools     : {metrics['total_tools']}\n"
            f"- Raw Tools Tokens  : {metrics['raw_tool_tokens']} tokens\n"
            f"- Gateway Overhead  : {metrics['gateway_meta_tokens']} tokens\n"
            f"- Turn-0 Reduction  : {metrics['tokens_saved']} tokens ({metrics['savings_percentage']}% saved)\n"
            f"- LRU Hot Cache     : {cache_stats['cached_count']}/{cache_stats['capacity']} tools "
            f"(Hit Ratio: {cache_stats['hit_ratio_percent']}%)\n"
            f"- Lifetime Calls    : {telemetry_summary['total_calls']} calls ({telemetry_summary['success_rate_percent']}% success)\n"
            f"- Lifetime Saved    : {telemetry_summary['total_tokens_saved']:,} tokens (${telemetry_summary['estimated_dollars_saved']:.2f})\n"
            f"- Avg Call Latency  : {telemetry_summary['avg_latency_ms']:.1f}ms\n"
            f"- Telemetry Database: {telemetry_summary['db_path']}\n"
        )
        return JSONRPCResponse.make_result(
            req_id,
            {"content": [{"type": "text", "text": report}]},
        )

    def run_stdio(self) -> None:
        """Starts the gateway listening on standard input and writing to standard output."""
        sys.stderr.write(f"[mcp-mesh] Gateway active in '{self.mode}' mode. Listening on stdio...\n")
        sys.stderr.flush()

        for line in sys.stdin:
            response_line = self.handle_message(line)
            if response_line:
                sys.stdout.write(response_line)
                sys.stdout.flush()
