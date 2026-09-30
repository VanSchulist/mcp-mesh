"""Core data models, protocol envelopes, and helper functions for mcp-mesh.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


# Standard JSON-RPC 2.0 Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Extended MCP Mesh Error Codes
SERVER_NOT_FOUND = -32001
TOOL_NOT_FOUND = -32002
DOWNSTREAM_TIMEOUT = -32003


@dataclass
class ToolParameter:
    """Represents a single input parameter of an MCP tool."""
    name: str
    param_type: str
    description: str = ""
    required: bool = False
    default: Any = None
    enum_values: List[str] = field(default_factory=list)


@dataclass
class ToolDefinition:
    """Represents an introspected or registered tool from an upstream/downstream server."""
    name: str
    server_id: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, ToolParameter] = field(default_factory=dict)
    raw_token_count: int = 0
    category: str = "general"

    def __post_init__(self) -> None:
        if not self.parameters and self.input_schema:
            self._parse_parameters_from_schema()
        if self.raw_token_count == 0:
            self.raw_token_count = estimate_tokens(self.to_mcp_dict())

    def _parse_parameters_from_schema(self) -> None:
        properties = self.input_schema.get("properties", {})
        required_list = self.input_schema.get("required", [])

        for param_name, meta in properties.items():
            if isinstance(meta, dict):
                p_type = meta.get("type", "any")
                p_desc = meta.get("description", "")
                p_req = param_name in required_list
                p_enum = meta.get("enum", [])
                p_default = meta.get("default", None)
                self.parameters[param_name] = ToolParameter(
                    name=param_name,
                    param_type=str(p_type),
                    description=p_desc,
                    required=p_req,
                    default=p_default,
                    enum_values=[str(x) for x in p_enum],
                )

    @property
    def qualified_name(self) -> str:
        """Returns the fully-qualified unique identifier: server_id::tool_name."""
        return f"{self.server_id}::{self.name}"

    def to_compact_signature(self) -> str:
        """Generates an ultra-compact signature (15-30 tokens) for lazy exploration."""
        args_summary: List[str] = []
        for p in self.parameters.values():
            opt = "" if p.required else "?"
            args_summary.append(f"{p.name}{opt}: {p.param_type}")
        args_str = ", ".join(args_summary)
        # First sentence or 100 characters of description
        clean_desc = self.description.strip().split("\n")[0]
        if len(clean_desc) > 90:
            clean_desc = clean_desc[:87] + "..."
        return f"{self.qualified_name}({args_str}) -> {clean_desc}"

    def to_mcp_dict(self) -> Dict[str, Any]:
        """Converts into standard Model Context Protocol tool schema format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema or {
                "type": "object",
                "properties": {
                    p.name: {"type": p.param_type, "description": p.description}
                    for p in self.parameters.values()
                },
                "required": [p.name for p in self.parameters.values() if p.required],
            },
        }


@dataclass
class DownstreamServerConfig:
    """Configuration for connecting to an upstream or downstream MCP server."""
    id: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    enabled: bool = True
    description: str = ""


@dataclass
class JSONRPCRequest:
    """Represents a JSON-RPC 2.0 incoming request."""
    method: str
    params: Union[Dict[str, Any], List[Any], None] = None
    id: Optional[Union[str, int]] = None
    jsonrpc: str = "2.0"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> JSONRPCRequest:
        return cls(
            method=data.get("method", ""),
            params=data.get("params"),
            id=data.get("id"),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            res["params"] = self.params
        if self.id is not None:
            res["id"] = self.id
        return res


@dataclass
class JSONRPCResponse:
    """Represents a JSON-RPC 2.0 outgoing response."""
    id: Optional[Union[str, int]]
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    jsonrpc: str = "2.0"

    @classmethod
    def make_result(cls, req_id: Optional[Union[str, int]], result: Any) -> JSONRPCResponse:
        return cls(id=req_id, result=result, error=None)

    @classmethod
    def make_error(
        cls,
        req_id: Optional[Union[str, int]],
        code: int,
        message: str,
        data: Optional[Any] = None,
    ) -> JSONRPCResponse:
        err: Dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return cls(id=req_id, result=None, error=err)

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            res["error"] = self.error
        else:
            res["result"] = self.result
        return res

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True) + "\n"


def estimate_tokens(content: Union[str, Dict[str, Any], List[Any]]) -> int:
    """Estimates the LLM token footprint of arbitrary content.
    
    Uses standard ~3.8-4.0 characters per token rule for JSON/code structures.
    """
    if isinstance(content, (dict, list)):
        raw_text = json.dumps(content, separators=(",", ":"))
    else:
        raw_text = str(content)
    
    if not raw_text:
        return 0
    
    # Accurate heuristic: ~3.75 characters per token in structured JSON/English text
    tokens = max(1, int(len(raw_text) / 3.75))
    return tokens


def compact_tool_signature(tool: ToolDefinition) -> str:
    """Wrapper function returning the compact string signature of a tool."""
    return tool.to_compact_signature()
