#!/usr/bin/env python3
"""A standalone, lightweight mock downstream MCP server for integration testing.

Responds to initialize, tools/list, and tools/call over standard input/output.
"""

import argparse
import json
import sys


SERVER_TOOLS = {
    "github": [
        {
            "name": "create_issue",
            "description": "Create a new issue in a GitHub repository.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["owner", "repo", "title"],
            },
        },
        {
            "name": "search_code",
            "description": "Search code across repositories.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    ],
    "postgres": [
        {
            "name": "query_readonly",
            "description": "Execute a SELECT SQL query against PostgreSQL.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                },
                "required": ["sql"],
            },
        }
    ],
    "filesystem": [
        {
            "name": "read_file",
            "description": "Read file contents from local filesystem.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        }
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="github", choices=["github", "postgres", "filesystem"])
    args = parser.parse_args()

    tools = SERVER_TOOLS.get(args.server, [])

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": f"mock-{args.server}", "version": "1.0.0"},
                    "capabilities": {"tools": {}},
                },
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools},
            }
        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Mock execution succeeded for {args.server}::{tool_name} with {json.dumps(tool_args)}",
                        }
                    ]
                },
            }
        else:
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method {method} not found"},
            }

        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
