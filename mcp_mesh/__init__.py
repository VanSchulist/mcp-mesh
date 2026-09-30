"""mcp-mesh: The Dynamic Model Context Protocol Gateway & Lazy Tool Router.

Author: Van Schulist (@VanSchulist / Existential Cloud)
License: MIT
"""

__version__ = "1.1.0"
__author__ = "Van Schulist"
__brand__ = "Existential Cloud"

from .core import (
    ToolDefinition,
    DownstreamServerConfig,
    JSONRPCRequest,
    JSONRPCResponse,
    estimate_tokens,
    compact_tool_signature,
)
from .cache import LRUSchemaCache
from .doctor import MCPDoctor
from .indexer import ToolIndexer
from .registry import DownstreamRegistry
from .proxy import MCPMeshGateway
from .sse import run_sse_server

__all__ = [
    "__version__",
    "ToolDefinition",
    "DownstreamServerConfig",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "estimate_tokens",
    "compact_tool_signature",
    "LRUSchemaCache",
    "MCPDoctor",
    "ToolIndexer",
    "DownstreamRegistry",
    "MCPMeshGateway",
    "run_sse_server",
]
