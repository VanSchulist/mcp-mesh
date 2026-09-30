"""Tool indexing, keyword search scoring, and token savings metrics for mcp-mesh.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .core import ToolDefinition, estimate_tokens


# Common English stopwords to ignore during keyword scoring
STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "this", "that", "these", "those",
    "it", "its", "into", "can", "will", "would", "should", "could", "get", "set"
}


def tokenize(text: str) -> List[str]:
    """Splits identifiers and natural language into normalized search tokens.
    
    Handles compound words, camelCase, snake_case, kebab-case, and standard prose.
    """
    if not text:
        return []
    
    # 1. Whole alphanumeric words (e.g. 'github', 'pullrequest')
    raw_words = [w.lower() for w in re.findall(r"[a-zA-Z0-9]+", text)]

    # 2. Split camelCase (e.g., 'getDatabaseUser' -> 'get Database User')
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    # Replace punctuation, underscores, dashes with space
    s2 = re.sub(r"[^a-zA-Z0-9]+", " ", s1)
    split_words = [t.lower() for t in s2.split()]
    
    # Combine unique tokens and filter stopwords
    seen: Set[str] = set()
    tokens: List[str] = []
    for w in raw_words + split_words:
        if len(w) >= 2 and w not in STOPWORDS and w not in seen:
            seen.add(w)
            tokens.append(w)
    return tokens


class ToolIndexer:
    """Maintains an inverted keyword index of all available tools across connected servers.
    
    Provides sub-millisecond retrieval and calculates dynamic token economy metrics.
    """

    def __init__(self) -> None:
        self.tools: Dict[str, ToolDefinition] = {}
        # Inverted index: token -> set of tool qualified names
        self.inverted_index: Dict[str, Set[str]] = {}
        # Precomputed token weights per tool: qualified_name -> {token: weight}
        self.tool_token_weights: Dict[str, Dict[str, float]] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        """Indexes a single tool definition."""
        key = tool.qualified_name
        self.tools[key] = tool
        self._index_single_tool(tool)

    def register_tools(self, tools: List[ToolDefinition]) -> None:
        """Batch registers multiple tools."""
        for tool in tools:
            self.register_tool(tool)

    def unregister_server(self, server_id: str) -> int:
        """Removes all tools associated with a downstream server."""
        removed_keys = [k for k, t in self.tools.items() if t.server_id == server_id]
        for k in removed_keys:
            del self.tools[k]
            if k in self.tool_token_weights:
                del self.tool_token_weights[k]
        
        # Rebuild inverted index cleanly
        self._rebuild_inverted_index()
        return len(removed_keys)

    def clear(self) -> None:
        """Clears all indexed tools."""
        self.tools.clear()
        self.inverted_index.clear()
        self.tool_token_weights.clear()

    def _index_single_tool(self, tool: ToolDefinition) -> None:
        key = tool.qualified_name
        weights: Dict[str, float] = {}

        # 1. Server ID tokens (weight: 2.0)
        for t in tokenize(tool.server_id):
            weights[t] = weights.get(t, 0.0) + 2.0
            self.inverted_index.setdefault(t, set()).add(key)

        # 2. Tool Name tokens (highest priority weight: 4.0)
        for t in tokenize(tool.name):
            weights[t] = weights.get(t, 0.0) + 4.0
            self.inverted_index.setdefault(t, set()).add(key)

        # 3. Category tokens (weight: 2.5)
        for t in tokenize(tool.category):
            weights[t] = weights.get(t, 0.0) + 2.5
            self.inverted_index.setdefault(t, set()).add(key)

        # 4. Description tokens (weight: 1.5)
        for t in tokenize(tool.description):
            weights[t] = weights.get(t, 0.0) + 1.5
            self.inverted_index.setdefault(t, set()).add(key)

        # 5. Parameter names and descriptions (weight: 1.0)
        for p in tool.parameters.values():
            for t in tokenize(p.name):
                weights[t] = weights.get(t, 0.0) + 1.2
                self.inverted_index.setdefault(t, set()).add(key)
            for t in tokenize(p.description):
                weights[t] = weights.get(t, 0.0) + 0.8
                self.inverted_index.setdefault(t, set()).add(key)

        self.tool_token_weights[key] = weights

    def _rebuild_inverted_index(self) -> None:
        self.inverted_index.clear()
        self.tool_token_weights.clear()
        for tool in self.tools.values():
            self._index_single_tool(tool)

    def get_tool(self, qualified_or_name: str) -> Optional[ToolDefinition]:
        """Looks up a tool by either 'server_id::name' or simple 'name'."""
        if qualified_or_name in self.tools:
            return self.tools[qualified_or_name]
        
        # Fallback to simple name match if unambiguous
        matches = [t for t in self.tools.values() if t.name == qualified_or_name]
        if len(matches) == 1:
            return matches[0]
        return None

    def search(
        self,
        query: str,
        limit: int = 5,
        server_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
    ) -> List[Tuple[ToolDefinition, float]]:
        """Searches the index for tools matching the query string.
        
        Returns a list of tuples containing (ToolDefinition, relevance_score) sorted descending.
        """
        query_tokens = tokenize(query)
        if not query_tokens:
            # If no query tokens provided, return first N tools
            results: List[Tuple[ToolDefinition, float]] = []
            for t in list(self.tools.values())[:limit]:
                results.append((t, 1.0))
            return results

        scores: Dict[str, float] = {}

        for q_token in query_tokens:
            # Direct match in inverted index
            matched_keys = self.inverted_index.get(q_token, set())
            for key in matched_keys:
                w = self.tool_token_weights.get(key, {}).get(q_token, 1.0)
                scores[key] = scores.get(key, 0.0) + w

            # Prefix/substring match for partial inputs (e.g. 'repo' matches 'repository')
            for index_token, tool_keys in self.inverted_index.items():
                if index_token != q_token and (q_token in index_token or index_token in q_token):
                    for key in tool_keys:
                        sub_weight = 0.5 * self.tool_token_weights.get(key, {}).get(index_token, 1.0)
                        scores[key] = scores.get(key, 0.0) + sub_weight

        # Filter and rank
        ranked_results: List[Tuple[ToolDefinition, float]] = []
        for key, raw_score in scores.items():
            tool = self.tools[key]
            if server_filter and tool.server_id.lower() != server_filter.lower():
                continue
            if category_filter and tool.category.lower() != category_filter.lower():
                continue
            
            # Normalize score relative to query token count
            norm_score = round(raw_score / max(1, len(query_tokens)), 2)
            ranked_results.append((tool, norm_score))

        ranked_results.sort(key=lambda item: item[1], reverse=True)
        return ranked_results[:limit]

    def get_metrics(self) -> Dict[str, Any]:
        """Calculates token footprint metrics comparing raw MCP to mcp-mesh gateway."""
        total_tools = len(self.tools)
        servers = set(t.server_id for t in self.tools.values())
        total_servers = len(servers)

        raw_tokens = sum(t.raw_token_count for t in self.tools.values())

        # Baseline cost of exposing the 3 mcp-mesh meta-tools
        # (mesh_search_tools, mesh_describe_tool, mesh_invoke_tool)
        # Each meta-tool schema is ~120 tokens. Total ~360-400 tokens.
        mesh_meta_tokens = 380

        if raw_tokens > 0:
            saved_tokens = max(0, raw_tokens - mesh_meta_tokens)
            savings_pct = round((saved_tokens / raw_tokens) * 100.0, 1)
        else:
            saved_tokens = 0
            savings_pct = 0.0

        return {
            "total_servers": total_servers,
            "total_tools": total_tools,
            "server_ids": sorted(list(servers)),
            "raw_tool_tokens": raw_tokens,
            "gateway_meta_tokens": mesh_meta_tokens if total_tools > 0 else 0,
            "tokens_saved": saved_tokens,
            "savings_percentage": savings_pct,
        }
