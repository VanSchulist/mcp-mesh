"""mcp-mesh: The Dynamic Model Context Protocol Gateway & Lazy Tool Router.

Author: Van Schulist (@VanSchulist / Existential Cloud)
License: MIT
"""

__version__ = "1.0.0"
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
from .indexer import ToolIndexer
from .registry import DownstreamRegistry
from .proxy import MCPMeshGateway

__all__ = [
    "__version__",
    "ToolDefinition",
    "DownstreamServerConfig",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "estimate_tokens",
    "compact_tool_signature",
    "ToolIndexer",
    "DownstreamRegistry",
    "MCPMeshGateway",
]
