"""The Model Context Protocol (MCP) Stdio Gateway implementation.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

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
from .indexer import ToolIndexer
from .registry import DownstreamRegistry


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
        server_version: str = "1.0.0",
    ) -> None:
        self.registry = registry or DownstreamRegistry()
        self.indexer: ToolIndexer = self.registry.indexer
        self.mode = mode  # "lazy" or "passthrough"
        self.server_name = server_name
        self.server_version = server_version
        self.protocol_version = "2024-11-05"

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
                            "description": "The downstream server ID (e.g. 'github', 'postgres').",
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
                    "required": ["server", "tool_name"],
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
            lines = [f"Found {len(matches)} matching tool(s):"]
            for tool, score in matches:
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

        if not server or not tool_name:
            return JSONRPCResponse.make_error(req_id, INVALID_PARAMS, "'server' and 'tool_name' are required.")

        tool = self.indexer.get_tool(f"{server}::{tool_name}")
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

        if not server or not tool_name:
            return JSONRPCResponse.make_error(req_id, INVALID_PARAMS, "'server' and 'tool_name' are required.")

        res = self.registry.call_tool(server, tool_name, tool_args)
        if "error" in res:
            err = res["error"]
            return JSONRPCResponse.make_error(
                req_id,
                err.get("code", INTERNAL_ERROR),
                err.get("message", "Execution error"),
                err.get("data"),
            )

        return JSONRPCResponse.make_result(req_id, res.get("result", {}))

    def _exec_mesh_status(self, req_id: Optional[Union[str, int]]) -> JSONRPCResponse:
        metrics = self.indexer.get_metrics()
        report = (
            f"=== mcp-mesh Gateway Status ===\n"
            f"• Connected Servers : {metrics['total_servers']} ({', '.join(metrics['server_ids']) or 'none'})\n"
            f"• Indexed Tools     : {metrics['total_tools']}\n"
            f"• Raw Tools Tokens  : {metrics['raw_tool_tokens']} tokens\n"
            f"• Gateway Overhead  : {metrics['gateway_meta_tokens']} tokens\n"
            f"• Turn-0 Reduction  : {metrics['tokens_saved']} tokens ({metrics['savings_percentage']}% saved)\n"
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
