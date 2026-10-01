"""Command-line interface (CLI) for mcp-mesh: gateway runner, stats, search, and demo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

from .core import ToolDefinition
from .doctor import MCPDoctor
from .indexer import ToolIndexer
from .monitor import run_monitor
from .proxy import MCPMeshGateway
from .registry import DownstreamRegistry
from .sse import run_sse_server


def load_demo_tools() -> List[ToolDefinition]:
    """Generates realistic enterprise MCP tools across 5 common server categories.
    
    Used for instant demonstrations, offline benchmarking, and zero-config experimentation.
    """
    tools = [
        # Server 1: GitHub MCP Server
        ToolDefinition(
            name="create_issue",
            server_id="github",
            description="Create a new issue in a GitHub repository with title, markdown body, assignees, and labels.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner or organization."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "title": {"type": "string", "description": "Title of the issue."},
                    "body": {"type": "string", "description": "Detailed markdown issue description."},
                    "labels": {"type": "array", "description": "List of label strings."},
                },
                "required": ["owner", "repo", "title"],
            },
        ),
        ToolDefinition(
            name="create_pull_request",
            server_id="github",
            description="Open a new pull request comparing a head branch into a base branch with optional draft status.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "title": {"type": "string", "description": "Pull request title."},
                    "head": {"type": "string", "description": "Head branch containing feature commits."},
                    "base": {"type": "string", "description": "Target base branch (default: main)."},
                    "draft": {"type": "boolean", "description": "Whether to create PR as draft."},
                },
                "required": ["owner", "repo", "title", "head", "base"],
            },
        ),
        ToolDefinition(
            name="search_code",
            server_id="github",
            description="Search code across repositories using GitHub Search syntax and file extensions.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query terms."},
                    "extension": {"type": "string", "description": "Filter by file extension."},
                    "max_results": {"type": "integer", "description": "Maximum search items."},
                },
                "required": ["query"],
            },
        ),

        # Server 2: PostgreSQL MCP Server
        ToolDefinition(
            name="query_readonly",
            server_id="postgres",
            description="Execute a safe, read-only SQL SELECT query against the PostgreSQL database with row limiting.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "Valid SQL SELECT statement."},
                    "max_rows": {"type": "integer", "description": "Maximum rows to return (default: 100)."},
                    "timeout_ms": {"type": "integer", "description": "Query timeout in milliseconds."},
                },
                "required": ["sql"],
            },
        ),
        ToolDefinition(
            name="explain_query",
            server_id="postgres",
            description="Run EXPLAIN ANALYZE on a SQL query and return cost estimation and query execution plan.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL statement to analyze."},
                    "buffers": {"type": "boolean", "description": "Include buffer usage metrics."},
                },
                "required": ["sql"],
            },
        ),
        ToolDefinition(
            name="introspect_schema",
            server_id="postgres",
            description="List all tables, views, columns, foreign keys, and indexes in a target database schema.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "schema_name": {"type": "string", "description": "Schema name (default: public)."},
                },
            },
        ),

        # Server 3: Slack MCP Server
        ToolDefinition(
            name="post_message",
            server_id="slack",
            description="Send a message to a public or private Slack channel or user thread with rich mrkdwn blocks.",
            category="messaging",
            input_schema={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "Slack channel ID or name."},
                    "text": {"type": "string", "description": "Message text in mrkdwn format."},
                    "thread_ts": {"type": "string", "description": "Optional thread timestamp for replies."},
                },
                "required": ["channel_id", "text"],
            },
        ),
        ToolDefinition(
            name="search_messages",
            server_id="slack",
            description="Search conversation history across channels by keywords, user filter, or date range.",
            category="messaging",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords to match."},
                    "count": {"type": "integer", "description": "Number of results."},
                },
                "required": ["query"],
            },
        ),

        # Server 4: AWS Cloud MCP Server
        ToolDefinition(
            name="describe_instances",
            server_id="aws",
            description="Query EC2 instances in an AWS region filtered by instance ID, tag name, or state.",
            category="cloud",
            input_schema={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "AWS region name (e.g. us-east-1)."},
                    "instance_ids": {"type": "array", "description": "List of EC2 instance IDs."},
                },
                "required": ["region"],
            },
        ),
        ToolDefinition(
            name="get_cloudwatch_metrics",
            server_id="aws",
            description="Retrieve CPU, memory, and disk CloudWatch metric datapoints for an AWS resource.",
            category="cloud",
            input_schema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Metric namespace (e.g. AWS/EC2)."},
                    "metric_name": {"type": "string", "description": "Metric name."},
                    "period_seconds": {"type": "integer", "description": "Aggregation window in seconds."},
                },
                "required": ["namespace", "metric_name"],
            },
        ),

        # Server 5: Local Filesystem MCP Server
        ToolDefinition(
            name="read_file",
            server_id="filesystem",
            description="Read the contents of a UTF-8 text file from the local workspace with line slicing.",
            category="filesystem",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path."},
                    "start_line": {"type": "integer", "description": "1-based starting line."},
                    "end_line": {"type": "integer", "description": "1-based ending line."},
                },
                "required": ["path"],
            },
        ),
        ToolDefinition(
            name="search_files",
            server_id="filesystem",
            description="Recursively search for files matching a glob pattern or containing specific regex terms.",
            category="filesystem",
            input_schema={
                "type": "object",
                "properties": {
                    "root_dir": {"type": "string", "description": "Directory root for search."},
                    "pattern": {"type": "string", "description": "Glob or regex pattern."},
                },
                "required": ["root_dir"],
            },
        ),
    ]
    return tools


def print_banner() -> None:
    banner = (
        "=================================================================\n"
        "  mcp-mesh: Dynamic MCP Gateway & Lazy Tool Router (v1.1.0)\n"
        "  Engineered by Van Schulist (@VanSchulist / Existential Cloud)\n"
        "================================================================="
    )
    print(banner)


def cmd_stats(args: argparse.Namespace) -> None:
    """Displays token metrics and server aggregation status."""
    registry = DownstreamRegistry()
    if args.config and os.path.exists(args.config):
        registry.load_config_file(args.config)
    else:
        # Load demo suite if no custom config provided
        for tool in load_demo_tools():
            registry.indexer.register_tool(tool)

    metrics = registry.indexer.get_metrics()
    print_banner()
    print("\n[+] AGGREGATION & TOKEN ECONOMY REPORT:")
    print(f"  Connected Servers  : {metrics['total_servers']}")
    print(f"  Server IDs         : {', '.join(metrics['server_ids'])}")
    print(f"  Total Tools        : {metrics['total_tools']}")
    print("-----------------------------------------------------------------")
    print(f"  Raw Schema Tokens  : {metrics['raw_tool_tokens']} tokens (Turn-0 baseline)")
    print(f"  mcp-mesh Overhead  : {metrics['gateway_meta_tokens']} tokens (Meta-tool signatures)")
    print(f"  Net Tokens Saved   : {metrics['tokens_saved']} tokens")
    print(f"  Efficiency Gain    : {metrics['savings_percentage']}% token reduction!")
    print("=================================================================\n")


def cmd_search(args: argparse.Namespace) -> None:
    """Executes a search query against indexed tools."""
    indexer = ToolIndexer()
    for tool in load_demo_tools():
        indexer.register_tool(tool)

    results = indexer.search(args.query, limit=args.limit)
    print_banner()
    print(f"\n[+] Search Query: '{args.query}' (found {len(results)} match(es))\n")

    for i, (tool, score) in enumerate(results, 1):
        print(f"  {i}. [{tool.server_id}] {tool.name} (Relevance Score: {score})")
        print(f"     Signature : {tool.to_compact_signature()}")
        print(f"     Invocation: mesh_invoke_tool(server='{tool.server_id}', tool_name='{tool.name}', arguments={{...}})")
        print()


def cmd_inspect(args: argparse.Namespace) -> None:
    """Dumps the full JSON schema of a specific tool."""
    indexer = ToolIndexer()
    for tool in load_demo_tools():
        indexer.register_tool(tool)

    tool = indexer.get_tool(args.tool_key)
    if not tool:
        print(f"[-] Error: Tool '{args.tool_key}' not found in registry.")
        sys.exit(1)

    print(json.dumps(tool.to_mcp_dict(), indent=2))


def cmd_demo(args: argparse.Namespace) -> None:
    """Interactive demonstration showcasing tool discovery, schema inspection, and token savings."""
    print_banner()
    print("\n[*] Initializing enterprise demo environment with 5 MCP servers...")
    indexer = ToolIndexer()
    tools = load_demo_tools()
    for tool in tools:
        indexer.register_tool(tool)

    metrics = indexer.get_metrics()
    print(f"[+] Loaded {len(tools)} tools across {metrics['total_servers']} servers: {', '.join(metrics['server_ids'])}")
    print(f"[+] Turn-0 Raw Tool Footprint : {metrics['raw_tool_tokens']} tokens")
    print(f"[+] mcp-mesh Gateway Footprint: {metrics['gateway_meta_tokens']} tokens")
    print(f"[+] Immediate Token Savings   : {metrics['tokens_saved']} tokens ({metrics['savings_percentage']}% reduction!)\n")

    test_queries = [
        "commit code and open a pull request",
        "query database and check execution performance",
        "post notification message to slack channel",
        "check cpu usage metrics on ec2 cloud",
    ]

    print("[*] Running simulated agent natural language tool discovery:")
    for query in test_queries:
        print(f"\n--> Agent intent: '{query}'")
        matches = indexer.search(query, limit=2)
        for tool, score in matches:
            print(f"    Match: [{tool.server_id}] {tool.name} (score: {score})")
            print(f"           {tool.to_compact_signature()}")

    print("\n[+] Demo completed successfully. Zero external dependencies required.")


def cmd_run(args: argparse.Namespace) -> None:
    """Runs the MCP gateway stdio server for client connections."""
    registry = DownstreamRegistry()
    if args.config and os.path.exists(args.config):
        count = registry.load_config_file(args.config)
        sys.stderr.write(f"[mcp-mesh] Loaded {count} server configurations from {args.config}\n")
    else:
        # Load demo tools for zero-config out-of-the-box operation
        for tool in load_demo_tools():
            registry.indexer.register_tool(tool)
        sys.stderr.write("[mcp-mesh] No config provided. Loaded default demonstration tools.\n")

    gateway = MCPMeshGateway(registry=registry, mode=args.mode)
    gateway.run_stdio()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Runs comprehensive diagnostic health checks on the MCP environment and tools."""
    print_banner()
    cfg = args.config if args.config else None
    doctor = MCPDoctor(config_path=cfg)
    doctor.run_all()
    doctor.print_report()
    if doctor.has_errors:
        sys.exit(1)


def cmd_sse(args: argparse.Namespace) -> None:
    """Runs the HTTP/SSE streaming gateway daemon."""
    print_banner()
    registry = DownstreamRegistry()
    if args.config and os.path.exists(args.config):
        count = registry.load_config_file(args.config)
        sys.stderr.write(f"[mcp-mesh] Loaded {count} server configurations from {args.config}\n")
    else:
        for tool in load_demo_tools():
            registry.indexer.register_tool(tool)
        sys.stderr.write("[mcp-mesh] No config provided. Loaded default demonstration tools.\n")

    run_sse_server(registry=registry, host=args.host, port=args.port, mode=args.mode)


def cmd_monitor(args: argparse.Namespace) -> None:
    """Runs the real-time terminal telemetry monitor."""
    run_monitor(iterations=args.iterations, interval=args.interval, mock=args.demo)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-mesh",
        description="The Dynamic Model Context Protocol Gateway & Lazy Tool Router.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Command: run
    p_run = subparsers.add_parser("run", help="Start MCP stdio proxy gateway for Claude/Cursor/Antigravity")
    p_run.add_argument("--config", "-c", type=str, default="mcp_mesh.json", help="Path to MCP configuration file")
    p_run.add_argument("--mode", "-m", choices=["lazy", "passthrough"], default="lazy", help="Proxy mode (default: lazy)")

    # Command: stats
    p_stats = subparsers.add_parser("stats", help="Display token savings metrics and server summary")
    p_stats.add_argument("--config", "-c", type=str, default="", help="Path to MCP configuration file")

    # Command: search
    p_search = subparsers.add_parser("search", help="Test natural language tool discovery in terminal")
    p_search.add_argument("query", type=str, help="Search query or functional goal")
    p_search.add_argument("--limit", "-l", type=int, default=3, help="Max candidates to return")

    # Command: inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect full JSON schema for an indexed tool")
    p_inspect.add_argument("tool_key", type=str, help="Tool name or server_id::tool_name")

    # Command: doctor
    p_doctor = subparsers.add_parser("doctor", help="Run comprehensive diagnostic health check on MCP environment and tools")
    p_doctor.add_argument("--config", "-c", type=str, default="", help="Path to MCP configuration file")

    # Command: sse
    p_sse = subparsers.add_parser("sse", help="Start HTTP/SSE streaming gateway daemon for remote/containerized agents")
    p_sse.add_argument("--config", "-c", type=str, default="", help="Path to MCP configuration file")
    p_sse.add_argument("--host", "-H", type=str, default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    p_sse.add_argument("--port", "-p", type=int, default=8000, help="Port to listen on (default: 8000)")
    p_sse.add_argument("--mode", "-m", choices=["lazy", "passthrough"], default="lazy", help="Proxy mode (default: lazy)")

    # Command: monitor
    p_monitor = subparsers.add_parser("monitor", help="Start real-time ANSI terminal telemetry dashboard")
    p_monitor.add_argument("--demo", "-d", action="store_true", default=True, help="Run live simulated multi-turn agent telemetry (default: True)")
    p_monitor.add_argument("--iterations", "-n", type=int, default=None, help="Number of ticks before exiting (default: continuous)")
    p_monitor.add_argument("--interval", "-i", type=float, default=0.8, help="Refresh interval in seconds (default: 0.8)")

    # Command: demo
    subparsers.add_parser("demo", help="Run interactive zero-config demonstration and benchmark")

    args = parser.parse_args()

    if args.subcommand == "run":
        cmd_run(args)
    elif args.subcommand == "stats":
        cmd_stats(args)
    elif args.subcommand == "search":
        cmd_search(args)
    elif args.subcommand == "inspect":
        cmd_inspect(args)
    elif args.subcommand == "doctor":
        cmd_doctor(args)
    elif args.subcommand == "sse":
        cmd_sse(args)
    elif args.subcommand == "monitor":
        cmd_monitor(args)
    elif args.subcommand == "demo":
        cmd_demo(args)
    else:
        cmd_demo(args)


if __name__ == "__main__":
    main()
