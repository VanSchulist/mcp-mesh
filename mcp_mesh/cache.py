"""Dynamic LRU Hot-Tier Schema Cache for mcp-mesh.

Maintains an in-memory cache of frequently accessed tool schemas to minimize
repeated inverted-index searches and reduce latency in multi-turn agent sessions.
"""

from __future__ import annotations

import collections
import time
from typing import Any, Dict, List, Optional

from .core import ToolDefinition


class LRUSchemaCache:
    """Least Recently Used (LRU) cache for active tool schemas."""

    def __init__(self, capacity: int = 8) -> None:
        self.capacity = max(1, capacity)
        # Key: tool qualified name (server_id::tool_name) -> ToolDefinition
        self._cache: collections.OrderedDict[str, ToolDefinition] = collections.OrderedDict()
        self._access_timestamps: Dict[str, float] = {}
        self._hit_counts: Dict[str, int] = collections.defaultdict(int)
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def __len__(self) -> int:
        return len(self._cache)

    def get(self, key: str) -> Optional[ToolDefinition]:
        """Retrieves a tool from cache and moves it to the most recently used position."""
        if key in self._cache:
            self.hits += 1
            self._hit_counts[key] += 1
            self._cache.move_to_end(key)
            self._access_timestamps[key] = time.time()
            return self._cache[key]
        self.misses += 1
        return None

    def put(self, key_or_tool: Any, tool: Optional[ToolDefinition] = None) -> None:
        """Inserts or updates a tool in the cache. Supports put(tool) or put(key, tool)."""
        if tool is not None:
            key = str(key_or_tool)
            val = tool
        elif isinstance(key_or_tool, ToolDefinition):
            key = key_or_tool.qualified_name
            val = key_or_tool
        else:
            raise TypeError("Expected ToolDefinition or (key, ToolDefinition)")

        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.capacity:
                oldest_key, _ = self._cache.popitem(last=False)
                if oldest_key in self._access_timestamps:
                    del self._access_timestamps[oldest_key]
                if oldest_key in self._hit_counts:
                    del self._hit_counts[oldest_key]
                self.evictions += 1
        
        self._cache[key] = val
        self._access_timestamps[key] = time.time()

    def get_hot_tools(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns the list of currently cached tools in order of frequency and recency."""
        items: List[Dict[str, Any]] = []
        for k in self._cache:
            items.append({
                "key": k,
                "tool": self._cache[k],
                "hit_count": self._hit_counts.get(k, 0),
                "last_access": self._access_timestamps.get(k, 0.0),
            })
        # Rank primarily by frequency (hit_count), then by recency (last_access)
        items.sort(key=lambda x: (x["hit_count"], x["last_access"]), reverse=True)
        if limit is not None:
            return items[:limit]
        return items

    def clear(self) -> None:
        """Clears all cached entries and resets statistics."""
        self._cache.clear()
        self._access_timestamps.clear()
        self._hit_counts.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get_stats(self) -> Dict[str, Any]:
        """Returns operational metrics and hit/miss ratios."""
        total_requests = self.hits + self.misses
        hit_ratio = (self.hits / total_requests) if total_requests > 0 else 0.0
        return {
            "capacity": self.capacity,
            "size": len(self._cache),
            "cached_count": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_ratio": hit_ratio,
            "hit_ratio_percent": round(hit_ratio * 100, 1),
            "hot_tool_keys": list(self._cache.keys()),
        }
