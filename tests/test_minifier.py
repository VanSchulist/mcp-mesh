"""Unit tests for AST-based JSON-Schema minification and deduplication engine."""

import copy
import json
import unittest

from mcp_mesh.core import ToolDefinition, ToolParameter
from mcp_mesh.minifier import (
    MinificationConfig,
    MinificationStats,
    SchemaMinifier,
    minify_tool_schema,
)
from mcp_mesh.proxy import MCPMeshGateway
from mcp_mesh.registry import DownstreamRegistry


class TestSchemaMinifier(unittest.TestCase):

    def setUp(self):
        self.bloated_tool = {
            "name": "kubernetes_deploy_manifest",
            "description": (
                "Deploy a comprehensive Kubernetes manifest containing Deployments, StatefulSets, "
                "Services, Ingresses, and ConfigMaps to an existing cluster namespace.\n\n"
                "### Detailed Usage Instructions\n"
                "Make sure your kubeconfig is active and cluster RBAC permissions allow creating resources. "
                "Any invalid YAML syntax will trigger a validation error on the control plane. Refer to "
                "official Kubernetes docs for API schema versions."
            ),
            "inputSchema": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "$id": "https://example.com/schemas/k8s_deploy.json",
                "title": "DeployManifestParameters",
                "type": "object",
                "properties": {
                    "namespace": {
                        "title": "Namespace",
                        "type": "string",
                        "description": "Target Kubernetes namespace. Defaults to 'default' if omitted. Must conform to DNS-1123 label format.",
                        "default": "default",
                        "maxLength": 63,
                    },
                    "manifest_yaml": {
                        "title": "ManifestYAML",
                        "type": "string",
                        "description": (
                            "Raw YAML text representation of the Kubernetes resource manifests.\n\n"
                            "### Security Notice\n"
                            "Do not include plaintext secrets; use Secret resources or sealed secrets."
                        ),
                        "minLength": 10,
                    },
                    "dry_run": {
                        "title": "DryRun",
                        "type": "boolean",
                        "description": "If true, simulates the application via server-side dry run without persisting changes.",
                        "default": False,
                    },
                    "strategy": {
                        "title": "Strategy",
                        "type": "string",
                        "description": "Rollout deployment strategy type.",
                        "enum": ["RollingUpdate", "Recreate"],
                        "default": "RollingUpdate",
                    },
                    "metadata": {
                        "title": "Metadata",
                        "type": "object",
                        "properties": {
                            "labels": {
                                "title": "Labels",
                                "type": "object",
                                "description": "Arbitrary key-value label pairs to attach to all spawned pods.",
                                "examples": [{"app": "web", "env": "prod"}],
                            },
                            "annotations": {
                                "title": "Annotations",
                                "type": "object",
                                "description": "Non-identifying metadata annotations.",
                                "x-internal-flag": True,
                            },
                        },
                    },
                },
                "required": ["manifest_yaml"],
                "examples": [{"namespace": "prod", "dry_run": True}],
                "x-vendor-version": "1.28.0",
            },
        }

    def test_strip_non_semantic_keys(self):
        """Verifies that non-semantic keys ($schema, $id, title, examples, x-*) are stripped."""
        minifier = SchemaMinifier()
        minified = minifier.minify_tool(self.bloated_tool)

        schema = minified["inputSchema"]
        self.assertNotIn("$schema", schema)
        self.assertNotIn("$id", schema)
        self.assertNotIn("title", schema)
        self.assertNotIn("examples", schema)
        self.assertNotIn("x-vendor-version", schema)

        meta_props = schema["properties"]["metadata"]["properties"]
        self.assertNotIn("examples", meta_props["labels"])
        self.assertNotIn("x-internal-flag", meta_props["annotations"])

    def test_description_pruning_and_markdown_stripping(self):
        """Verifies that long multi-paragraph descriptions are pruned cleanly."""
        minifier = SchemaMinifier()
        minified = minifier.minify_tool(self.bloated_tool)

        # Tool description should have the main summary but strip the ### Usage Instructions section
        self.assertNotIn("### Detailed Usage Instructions", minified["description"])
        self.assertTrue(len(minified["description"]) <= 180)
        self.assertTrue(minified["description"].startswith("Deploy a comprehensive"))

        # Parameter description should strip ### Security Notice
        yaml_desc = minified["inputSchema"]["properties"]["manifest_yaml"]["description"]
        self.assertNotIn("### Security Notice", yaml_desc)
        self.assertTrue(len(yaml_desc) <= 110)

    def test_constraint_preservation(self):
        """Ensures semantic constraints (type, required, enum, default, min/max) are 100% preserved."""
        minifier = SchemaMinifier()
        minified = minifier.minify_tool(self.bloated_tool)
        schema = minified["inputSchema"]

        self.assertEqual(schema["required"], ["manifest_yaml"])
        self.assertEqual(schema["properties"]["strategy"]["enum"], ["RollingUpdate", "Recreate"])
        self.assertEqual(schema["properties"]["strategy"]["default"], "RollingUpdate")
        self.assertEqual(schema["properties"]["dry_run"]["default"], False)
        self.assertEqual(schema["properties"]["namespace"]["maxLength"], 63)
        self.assertEqual(schema["properties"]["manifest_yaml"]["minLength"], 10)

    def test_calculate_savings(self):
        """Verifies token reduction calculation returns positive savings."""
        minifier = SchemaMinifier()
        minified = minifier.minify_tool(self.bloated_tool)
        stats = minifier.calculate_savings(self.bloated_tool, minified)

        self.assertGreater(stats.raw_tokens, stats.minified_tokens)
        self.assertGreater(stats.tokens_saved, 0)
        self.assertGreater(stats.savings_ratio, 0.25)  # At least 25% savings on bloated schema

    def test_hoist_shared_definitions(self):
        """Tests hoisting duplicate nested structures across multiple tools into shared $defs."""
        shared_filter = {
            "type": "object",
            "properties": {
                "field": {"type": "string", "description": "Filter field name"},
                "operator": {"type": "string", "enum": ["eq", "gt", "lt"]},
                "value": {"type": "string"},
            },
            "required": ["field", "operator"],
        }

        tool_a = {
            "name": "query_users",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filter": copy.deepcopy(shared_filter),
                    "limit": {"type": "integer"},
                },
            },
        }

        tool_b = {
            "name": "query_orders",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filter": copy.deepcopy(shared_filter),
                    "offset": {"type": "integer"},
                },
            },
        }

        minifier = SchemaMinifier()
        hoisted_tools, shared_defs = minifier.hoist_shared_definitions([tool_a, tool_b], min_occurrences=2)

        self.assertEqual(len(shared_defs), 1)
        self.assertIn("SharedType1", shared_defs)
        self.assertIn("$ref", hoisted_tools[0]["inputSchema"]["properties"]["filter"])
        self.assertEqual(hoisted_tools[0]["inputSchema"]["properties"]["filter"]["$ref"], "#/$defs/SharedType1")
        self.assertEqual(hoisted_tools[1]["inputSchema"]["properties"]["filter"]["$ref"], "#/$defs/SharedType1")

    def test_convenience_helper(self):
        """Tests the module-level minify_tool_schema convenience function."""
        minified = minify_tool_schema(self.bloated_tool, max_desc_tokens=40)
        self.assertIn("name", minified)
        self.assertIn("inputSchema", minified)
        self.assertTrue(len(minified["description"]) <= 160)

    def test_tool_definition_to_minified_dict(self):
        """Verifies ToolDefinition.to_minified_dict() integration."""
        tool = ToolDefinition(
            name="test_tool",
            server_id="test_server",
            description="A test tool with verbose explanation.\n\n### Caveats\nDo not call frequently.",
            input_schema={
                "type": "object",
                "title": "UnwantedTitle",
                "properties": {
                    "param1": {
                        "type": "string",
                        "title": "param1",
                        "description": "First param with very long redundant paragraph explanation that goes on and on and on.",
                    }
                },
                "required": ["param1"],
            },
        )
        min_dict = tool.to_minified_dict(max_desc_tokens=30)
        self.assertEqual(min_dict["name"], "test_tool")
        self.assertNotIn("title", min_dict["inputSchema"])
        self.assertNotIn("### Caveats", min_dict["description"])

    def test_proxy_mesh_describe_minify_flag(self):
        """Tests that mesh_describe_tool respects the 'minify' flag."""
        registry = DownstreamRegistry()
        tool = ToolDefinition(
            name="bloated_query",
            server_id="db_server",
            description="Database query tool.\n\n### SQL Guidelines\nAlways use parameterized queries.",
            input_schema={
                "type": "object",
                "title": "QueryArgs",
                "properties": {
                    "sql": {
                        "type": "string",
                        "title": "SQL",
                        "description": "SQL statement.\n\nMust be SELECT only.",
                    }
                },
                "required": ["sql"],
            },
        )
        registry.indexer.register_tool(tool)
        gateway = MCPMeshGateway(registry=registry)

        # 1. Default (minify=True)
        res_min = gateway._exec_mesh_describe(1, {"server": "db_server", "tool_name": "bloated_query", "minify": True})
        content_min = json.loads(res_min.result["content"][0]["text"])
        self.assertNotIn("title", content_min["inputSchema"])
        self.assertNotIn("### SQL Guidelines", content_min["description"])

        # 2. Raw un-minified (minify=False)
        res_raw = gateway._exec_mesh_describe(2, {"server": "db_server", "tool_name": "bloated_query", "minify": False})
        content_raw = json.loads(res_raw.result["content"][0]["text"])
        self.assertIn("title", content_raw["inputSchema"])
        self.assertIn("### SQL Guidelines", content_raw["description"])

        # 3. Via full JSON-RPC string message (default without explicit minify param)
        rpc_str = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "mesh_describe_tool",
                "arguments": {"server": "db_server", "tool_name": "bloated_query"},
            },
        })
        resp_json = json.loads(gateway.handle_message(rpc_str))
        resp_content = json.loads(resp_json["result"]["content"][0]["text"])
        self.assertNotIn("title", resp_content["inputSchema"])
        self.assertIn("title", content_raw["inputSchema"])
        self.assertIn("### SQL Guidelines", content_raw["description"])


if __name__ == "__main__":
    unittest.main()
