"""Enterprise demonstration suite with 50 realistic MCP tools across 6 upstream servers.

Pure Python standard library implementation used for zero-config offline benchmarking,
instant CLI demonstrations, and token context economics simulation.
"""

from __future__ import annotations

from typing import List
from .core import ToolDefinition


def get_enterprise_tools() -> List[ToolDefinition]:
    """Returns 50 production-grade MCP tool definitions across 6 server domains.
    
    Servers:
      - github (10 tools): issues, pull requests, code search, commits, files, branches
      - postgres (10 tools): queries, DML, explain plans, schema inspection, indexes
      - slack (8 tools): messaging, channels, threads, reactions, file uploads
      - aws (8 tools): EC2 orchestration, CloudWatch metrics, S3 storage, Lambda
      - filesystem (7 tools): atomic file I/O, search, tree inspection, move
      - stripe (7 tools): payments, customers, invoices, subscriptions, refunds
    """
    tools = [
        # =====================================================================
        # 1. GITHUB MCP SERVER (10 tools)
        # =====================================================================
        ToolDefinition(
            name="create_issue",
            server_id="github",
            description="Create a new issue in a GitHub repository with title, markdown body, assignees, and labels.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner or organization name."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "title": {"type": "string", "description": "Title of the issue."},
                    "body": {"type": "string", "description": "Detailed markdown issue description and reproduction steps."},
                    "labels": {"type": "array", "items": {"type": "string"}, "description": "List of label strings."},
                    "assignees": {"type": "array", "items": {"type": "string"}, "description": "GitHub usernames to assign."},
                    "milestone": {"type": "integer", "description": "Milestone number ID."},
                },
                "required": ["owner", "repo", "title"],
            },
            raw_token_count=640,
        ),
        ToolDefinition(
            name="create_pull_request",
            server_id="github",
            description="Open a new pull request comparing a head branch into a base branch with optional draft status.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner or organization."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "title": {"type": "string", "description": "Pull request title."},
                    "head": {"type": "string", "description": "Head branch containing feature commits."},
                    "base": {"type": "string", "description": "Target base branch (default: main)."},
                    "body": {"type": "string", "description": "PR description markdown body."},
                    "draft": {"type": "boolean", "description": "Whether to create PR as draft."},
                    "maintainer_can_modify": {"type": "boolean", "description": "Allow upstream maintainer commits."},
                },
                "required": ["owner", "repo", "title", "head", "base"],
            },
            raw_token_count=680,
        ),
        ToolDefinition(
            name="search_code",
            server_id="github",
            description="Search code across repositories using GitHub Search syntax, file extensions, and qualifiers.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query terms and search qualifiers."},
                    "extension": {"type": "string", "description": "Filter by file extension."},
                    "max_results": {"type": "integer", "description": "Maximum search items to return (default: 10)."},
                    "repo": {"type": "string", "description": "Constrain search to specific owner/repo."},
                },
                "required": ["query"],
            },
            raw_token_count=520,
        ),
        ToolDefinition(
            name="list_commits",
            server_id="github",
            description="Retrieve recent git commits on a branch with author, SHA hash, commit message, and timestamp.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "branch": {"type": "string", "description": "Branch or tag name."},
                    "limit": {"type": "integer", "description": "Max commits to fetch (1-100)."},
                },
                "required": ["owner", "repo"],
            },
            raw_token_count=480,
        ),
        ToolDefinition(
            name="get_file_contents",
            server_id="github",
            description="Fetch raw content, encoding, and metadata of a file at a specific branch or commit SHA.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "path": {"type": "string", "description": "Relative file path inside the repo."},
                    "ref": {"type": "string", "description": "Branch name, tag, or full 40-char SHA."},
                },
                "required": ["owner", "repo", "path"],
            },
            raw_token_count=510,
        ),
        ToolDefinition(
            name="create_branch",
            server_id="github",
            description="Create a new git reference branch pointing to a specific commit SHA or HEAD.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "branch_name": {"type": "string", "description": "Name of the new branch to create."},
                    "from_sha": {"type": "string", "description": "Source commit SHA to branch from."},
                },
                "required": ["owner", "repo", "branch_name", "from_sha"],
            },
            raw_token_count=490,
        ),
        ToolDefinition(
            name="merge_pull_request",
            server_id="github",
            description="Merge an approved pull request with squash, rebase, or standard merge commit strategy.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "pull_number": {"type": "integer", "description": "Pull request number ID."},
                    "merge_method": {"type": "string", "enum": ["merge", "squash", "rebase"], "description": "Merge strategy."},
                    "commit_title": {"type": "string", "description": "Title for the merge commit."},
                },
                "required": ["owner", "repo", "pull_number"],
            },
            raw_token_count=560,
        ),
        ToolDefinition(
            name="add_issue_comment",
            server_id="github",
            description="Post a markdown comment on an existing GitHub issue or pull request discussion.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "issue_number": {"type": "integer", "description": "Issue or PR number."},
                    "body": {"type": "string", "description": "Markdown comment text."},
                },
                "required": ["owner", "repo", "issue_number", "body"],
            },
            raw_token_count=470,
        ),
        ToolDefinition(
            name="list_workflow_runs",
            server_id="github",
            description="List GitHub Actions CI/CD workflow runs and execution statuses for a repository.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner."},
                    "repo": {"type": "string", "description": "Repository name."},
                    "status": {"type": "string", "enum": ["completed", "in_progress", "queued", "failure"], "description": "Status filter."},
                    "limit": {"type": "integer", "description": "Maximum runs to return."},
                },
                "required": ["owner", "repo"],
            },
            raw_token_count=530,
        ),
        ToolDefinition(
            name="get_repository_info",
            server_id="github",
            description="Retrieve detailed metadata, star count, license, topics, and default branch for a repository.",
            category="git",
            input_schema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner."},
                    "repo": {"type": "string", "description": "Repository name."},
                },
                "required": ["owner", "repo"],
            },
            raw_token_count=420,
        ),

        # =====================================================================
        # 2. POSTGRESQL MCP SERVER (10 tools)
        # =====================================================================
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
            raw_token_count=580,
        ),
        ToolDefinition(
            name="execute_dml",
            server_id="postgres",
            description="Execute an INSERT, UPDATE, or DELETE SQL statement in an explicit transactional block.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL DML statement."},
                    "dry_run": {"type": "boolean", "description": "Rollback transaction after planning."},
                },
                "required": ["sql"],
            },
            raw_token_count=490,
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
                    "verbose": {"type": "boolean", "description": "Include verbose output."},
                },
                "required": ["sql"],
            },
            raw_token_count=540,
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
            raw_token_count=430,
        ),
        ToolDefinition(
            name="list_tables",
            server_id="postgres",
            description="Retrieve table names, approximate row counts, and disk size footprints in the current catalog.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "include_system": {"type": "boolean", "description": "Include pg_catalog tables."},
                },
            },
            raw_token_count=410,
        ),
        ToolDefinition(
            name="describe_table_columns",
            server_id="postgres",
            description="Get detailed data types, nullability, and default value definitions for columns in a table.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Target table name."},
                    "schema_name": {"type": "string", "description": "Schema name (default: public)."},
                },
                "required": ["table_name"],
            },
            raw_token_count=480,
        ),
        ToolDefinition(
            name="vacuum_table",
            server_id="postgres",
            description="Trigger VACUUM ANALYZE to reclaim dead tuple storage and update planner statistics.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Table to vacuum."},
                    "full": {"type": "boolean", "description": "Execute aggressive full vacuum."},
                },
                "required": ["table_name"],
            },
            raw_token_count=460,
        ),
        ToolDefinition(
            name="show_active_connections",
            server_id="postgres",
            description="List running client backends, wait events, query runtime, and client IP addresses.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max connection rows to return."},
                },
            },
            raw_token_count=440,
        ),
        ToolDefinition(
            name="create_index",
            server_id="postgres",
            description="Create a B-tree or GiST index concurrently on table columns to accelerate lookups.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Target table name."},
                    "column_names": {"type": "array", "items": {"type": "string"}, "description": "Column names to index."},
                    "concurrent": {"type": "boolean", "description": "Create concurrently without table lock."},
                },
                "required": ["table_name", "column_names"],
            },
            raw_token_count=520,
        ),
        ToolDefinition(
            name="kill_query",
            server_id="postgres",
            description="Cancel or terminate a long-running backend query by PostgreSQL PID.",
            category="database",
            input_schema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "PostgreSQL backend process ID."},
                    "force": {"type": "boolean", "description": "Force terminate connection if cancel fails."},
                },
                "required": ["pid"],
            },
            raw_token_count=450,
        ),

        # =====================================================================
        # 3. SLACK MCP SERVER (8 tools)
        # =====================================================================
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
            raw_token_count=540,
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
            raw_token_count=460,
        ),
        ToolDefinition(
            name="list_channels",
            server_id="slack",
            description="List public and private Slack channels in the workspace with member counts and topics.",
            category="messaging",
            input_schema={
                "type": "object",
                "properties": {
                    "types": {"type": "string", "description": "Comma-separated types: public_channel,private_channel."},
                    "limit": {"type": "integer", "description": "Max channels to return."},
                },
            },
            raw_token_count=450,
        ),
        ToolDefinition(
            name="get_channel_history",
            server_id="slack",
            description="Fetch chronological message logs from a Slack channel within a timestamp boundary.",
            category="messaging",
            input_schema={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "Target channel ID."},
                    "limit": {"type": "integer", "description": "Number of messages to retrieve."},
                    "oldest": {"type": "string", "description": "Unix timestamp lower boundary."},
                },
                "required": ["channel_id"],
            },
            raw_token_count=480,
        ),
        ToolDefinition(
            name="create_channel",
            server_id="slack",
            description="Create a new Slack channel for project communication with optional private flag.",
            category="messaging",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Channel slug name."},
                    "is_private": {"type": "boolean", "description": "Whether channel is private."},
                },
                "required": ["name"],
            },
            raw_token_count=420,
        ),
        ToolDefinition(
            name="set_channel_topic",
            server_id="slack",
            description="Update the channel topic or headline description visible to all members.",
            category="messaging",
            input_schema={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "Channel ID."},
                    "topic": {"type": "string", "description": "Topic string."},
                },
                "required": ["channel_id", "topic"],
            },
            raw_token_count=430,
        ),
        ToolDefinition(
            name="add_reaction",
            server_id="slack",
            description="Add an emoji reaction to a specific message in a Slack conversation channel.",
            category="messaging",
            input_schema={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "Channel ID."},
                    "timestamp": {"type": "string", "description": "Message timestamp."},
                    "emoji": {"type": "string", "description": "Emoji name without colons."},
                },
                "required": ["channel_id", "timestamp", "emoji"],
            },
            raw_token_count=450,
        ),
        ToolDefinition(
            name="upload_file",
            server_id="slack",
            description="Upload a snippet, log file, or document attachment directly into a Slack channel.",
            category="messaging",
            input_schema={
                "type": "object",
                "properties": {
                    "channels": {"type": "string", "description": "Channel IDs to share into."},
                    "content": {"type": "string", "description": "Text content of the file snippet."},
                    "filename": {"type": "string", "description": "Name for the uploaded file."},
                },
                "required": ["channels", "content"],
            },
            raw_token_count=490,
        ),

        # =====================================================================
        # 4. AWS CLOUD MCP SERVER (8 tools)
        # =====================================================================
        ToolDefinition(
            name="describe_instances",
            server_id="aws",
            description="Query EC2 instances in an AWS region filtered by instance ID, tag name, or state.",
            category="cloud",
            input_schema={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "AWS region name (e.g. us-east-1)."},
                    "instance_ids": {"type": "array", "items": {"type": "string"}, "description": "List of EC2 instance IDs."},
                },
                "required": ["region"],
            },
            raw_token_count=510,
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
            raw_token_count=520,
        ),
        ToolDefinition(
            name="start_ec2_instance",
            server_id="aws",
            description="Power on a stopped EC2 virtual machine instance in a specified AWS region.",
            category="cloud",
            input_schema={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "AWS region name."},
                    "instance_id": {"type": "string", "description": "EC2 instance ID to boot."},
                },
                "required": ["region", "instance_id"],
            },
            raw_token_count=440,
        ),
        ToolDefinition(
            name="stop_ec2_instance",
            server_id="aws",
            description="Gracefully shut down a running EC2 instance to halt compute billing charges.",
            category="cloud",
            input_schema={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "AWS region name."},
                    "instance_id": {"type": "string", "description": "EC2 instance ID to shut down."},
                    "force": {"type": "boolean", "description": "Whether to force terminate."},
                },
                "required": ["region", "instance_id"],
            },
            raw_token_count=460,
        ),
        ToolDefinition(
            name="list_s3_buckets",
            server_id="aws",
            description="Enumerate all Amazon S3 object storage buckets associated with the AWS account.",
            category="cloud",
            input_schema={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "AWS region filter."},
                },
            },
            raw_token_count=410,
        ),
        ToolDefinition(
            name="get_s3_object_metadata",
            server_id="aws",
            description="Inspect object metadata headers, byte length, ETag, and last modified date in S3.",
            category="cloud",
            input_schema={
                "type": "object",
                "properties": {
                    "bucket": {"type": "string", "description": "S3 bucket name."},
                    "key": {"type": "string", "description": "Object key path."},
                },
                "required": ["bucket", "key"],
            },
            raw_token_count=460,
        ),
        ToolDefinition(
            name="query_cloudwatch_logs",
            server_id="aws",
            description="Execute CloudWatch Logs Insights query over log groups within a time duration.",
            category="cloud",
            input_schema={
                "type": "object",
                "properties": {
                    "log_group_name": {"type": "string", "description": "CloudWatch log group."},
                    "query_string": {"type": "string", "description": "Logs Insights query expression."},
                    "limit": {"type": "integer", "description": "Maximum log events to return."},
                },
                "required": ["log_group_name", "query_string"],
            },
            raw_token_count=550,
        ),
        ToolDefinition(
            name="invoke_lambda",
            server_id="aws",
            description="Synchronously or asynchronously trigger an AWS Lambda serverless function execution.",
            category="cloud",
            input_schema={
                "type": "object",
                "properties": {
                    "function_name": {"type": "string", "description": "Lambda function name or ARN."},
                    "payload": {"type": "object", "description": "JSON event payload to pass to handler."},
                },
                "required": ["function_name"],
            },
            raw_token_count=490,
        ),

        # =====================================================================
        # 5. FILESYSTEM MCP SERVER (7 tools)
        # =====================================================================
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
            raw_token_count=510,
        ),
        ToolDefinition(
            name="write_file",
            server_id="filesystem",
            description="Write or overwrite text content to a destination file on the local filesystem.",
            category="filesystem",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target destination file path."},
                    "content": {"type": "string", "description": "UTF-8 content to write."},
                    "overwrite": {"type": "boolean", "description": "Whether to overwrite if exists."},
                },
                "required": ["path", "content"],
            },
            raw_token_count=480,
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
                    "pattern": {"type": "string", "description": "Glob pattern or regex pattern."},
                },
                "required": ["root_dir"],
            },
            raw_token_count=460,
        ),
        ToolDefinition(
            name="list_directory",
            server_id="filesystem",
            description="List files, subdirectories, byte sizes, and permissions within a target directory.",
            category="filesystem",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target directory path."},
                    "recursive": {"type": "boolean", "description": "Whether to list recursively."},
                },
                "required": ["path"],
            },
            raw_token_count=440,
        ),
        ToolDefinition(
            name="delete_file",
            server_id="filesystem",
            description="Safely remove an existing file from the filesystem with workspace boundary guardrails.",
            category="filesystem",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to delete."},
                    "force": {"type": "boolean", "description": "Ignore missing files."},
                },
                "required": ["path"],
            },
            raw_token_count=420,
        ),
        ToolDefinition(
            name="get_file_metadata",
            server_id="filesystem",
            description="Inspect byte size, inode, creation time, modification timestamp, and file permissions.",
            category="filesystem",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to inspect."},
                },
                "required": ["path"],
            },
            raw_token_count=430,
        ),
        ToolDefinition(
            name="move_file",
            server_id="filesystem",
            description="Atomically move or rename a file or directory to a new target path.",
            category="filesystem",
            input_schema={
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source path."},
                    "dst": {"type": "string", "description": "Destination path."},
                },
                "required": ["src", "dst"],
            },
            raw_token_count=420,
        ),

        # =====================================================================
        # 6. STRIPE BILLING MCP SERVER (7 tools)
        # =====================================================================
        ToolDefinition(
            name="create_payment_intent",
            server_id="stripe",
            description="Create a new payment intent with currency, amount in cents, and payment method options.",
            category="billing",
            input_schema={
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "description": "Amount in smallest currency unit (e.g. cents)."},
                    "currency": {"type": "string", "description": "Three-letter ISO currency code (e.g. usd)."},
                    "customer_id": {"type": "string", "description": "Stripe customer identifier."},
                    "description": {"type": "string", "description": "Payment description."},
                },
                "required": ["amount", "currency"],
            },
            raw_token_count=610,
        ),
        ToolDefinition(
            name="retrieve_customer",
            server_id="stripe",
            description="Fetch customer record, billing details, active subscriptions, and payment methods.",
            category="billing",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Stripe customer ID (cus_...)."},
                },
                "required": ["customer_id"],
            },
            raw_token_count=480,
        ),
        ToolDefinition(
            name="list_invoices",
            server_id="stripe",
            description="Enumerate customer invoices filtered by status (paid, open, void) and date range.",
            category="billing",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID filter."},
                    "status": {"type": "string", "enum": ["paid", "open", "void", "uncollectible"], "description": "Status filter."},
                    "limit": {"type": "integer", "description": "Number of invoices to retrieve."},
                },
            },
            raw_token_count=520,
        ),
        ToolDefinition(
            name="refund_charge",
            server_id="stripe",
            description="Issue a full or partial refund for a processed charge or payment intent.",
            category="billing",
            input_schema={
                "type": "object",
                "properties": {
                    "payment_intent_id": {"type": "string", "description": "Payment intent ID to refund."},
                    "amount": {"type": "integer", "description": "Partial refund amount (omit for full refund)."},
                    "reason": {"type": "string", "enum": ["duplicate", "fraudulent", "requested_by_customer"], "description": "Refund reason code."},
                },
                "required": ["payment_intent_id"],
            },
            raw_token_count=550,
        ),
        ToolDefinition(
            name="create_subscription",
            server_id="stripe",
            description="Enroll a customer in a recurring price tier subscription with billing cycle anchors.",
            category="billing",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID."},
                    "price_id": {"type": "string", "description": "Stripe recurring price ID (price_...)."},
                    "trial_days": {"type": "integer", "description": "Optional free trial duration in days."},
                },
                "required": ["customer_id", "price_id"],
            },
            raw_token_count=540,
        ),
        ToolDefinition(
            name="cancel_subscription",
            server_id="stripe",
            description="Cancel an active subscription immediately or at the end of the current billing period.",
            category="billing",
            input_schema={
                "type": "object",
                "properties": {
                    "subscription_id": {"type": "string", "description": "Subscription ID (sub_...)."},
                    "at_period_end": {"type": "boolean", "description": "Wait until billing cycle ends."},
                },
                "required": ["subscription_id"],
            },
            raw_token_count=480,
        ),
        ToolDefinition(
            name="list_payment_methods",
            server_id="stripe",
            description="Enumerate customer stored payment methods (cards, bank accounts) with expiration dates.",
            category="billing",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Customer ID."},
                    "type": {"type": "string", "description": "Payment method type (default: card)."},
                },
                "required": ["customer_id"],
            },
            raw_token_count=470,
        ),
    ]
    return tools
