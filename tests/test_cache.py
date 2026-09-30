"""Unit tests for mcp-mesh LRU schema cache."""

from __future__ import annotations

import unittest
from mcp_mesh.cache import LRUSchemaCache
from mcp_mesh.core import ToolDefinition


class TestLRUSchemaCache(unittest.TestCase):
    """Test suite for LRUSchemaCache operations, eviction, and metrics."""

    def setUp(self) -> None:
        self.cache = LRUSchemaCache(capacity=3)
        self.t1 = ToolDefinition(name="tool1", server_id="s1", description="Tool 1", input_schema={"type": "object"})
        self.t2 = ToolDefinition(name="tool2", server_id="s1", description="Tool 2", input_schema={"type": "object"})
        self.t3 = ToolDefinition(name="tool3", server_id="s2", description="Tool 3", input_schema={"type": "object"})
        self.t4 = ToolDefinition(name="tool4", server_id="s2", description="Tool 4", input_schema={"type": "object"})

    def test_put_and_get(self) -> None:
        self.cache.put("s1::tool1", self.t1)
        found = self.cache.get("s1::tool1")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "tool1")

    def test_cache_miss(self) -> None:
        missing = self.cache.get("non_existent")
        self.assertIsNone(missing)

    def test_lru_eviction(self) -> None:
        # Cache capacity is 3
        self.cache.put("s1::tool1", self.t1)
        self.cache.put("s1::tool2", self.t2)
        self.cache.put("s2::tool3", self.t3)
        self.assertEqual(len(self.cache), 3)

        # Access tool1 to make tool2 the least recently used
        _ = self.cache.get("s1::tool1")

        # Insert tool4, should evict tool2
        self.cache.put("s2::tool4", self.t4)
        self.assertEqual(len(self.cache), 3)

        self.assertIsNotNone(self.cache.get("s1::tool1"))
        self.assertIsNone(self.cache.get("s1::tool2"))  # Evicted!
        self.assertIsNotNone(self.cache.get("s2::tool3"))
        self.assertIsNotNone(self.cache.get("s2::tool4"))

    def test_stats_and_hit_ratio(self) -> None:
        self.cache.put("s1::tool1", self.t1)
        
        # 1 hit
        _ = self.cache.get("s1::tool1")
        # 2 misses
        _ = self.cache.get("unknown_1")
        _ = self.cache.get("unknown_2")

        stats = self.cache.get_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 2)
        self.assertAlmostEqual(stats["hit_ratio"], 1.0 / 3.0, places=3)
        self.assertEqual(stats["size"], 1)
        self.assertEqual(stats["capacity"], 3)

    def test_get_hot_tools(self) -> None:
        self.cache.put("s1::tool1", self.t1)
        self.cache.put("s1::tool2", self.t2)

        # Access tool1 three times, tool2 once
        self.cache.get("s1::tool1")
        self.cache.get("s1::tool1")
        self.cache.get("s1::tool2")

        hot = self.cache.get_hot_tools(limit=2)
        self.assertEqual(len(hot), 2)
        self.assertEqual(hot[0]["key"], "s1::tool1")
        self.assertEqual(hot[0]["hit_count"], 2)

    def test_clear(self) -> None:
        self.cache.put("s1::tool1", self.t1)
        self.cache.clear()
        self.assertEqual(len(self.cache), 0)
        self.assertIsNone(self.cache.get("s1::tool1"))


if __name__ == "__main__":
    unittest.main()
