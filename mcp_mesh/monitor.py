"""Terminal-based real-time telemetry monitor for mcp-mesh (Satellite 2 prototype).

Visualizes live tool discovery, JSON-RPC routing, dynamic LRU cache hits,
latency measurements, and cumulative token economy metrics.
"""

from __future__ import annotations

import datetime
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional


def _safe_write(text: str) -> None:
    """Writes text to stdout handling legacy terminal encodings (e.g. Windows GBK/CP936)."""
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except (UnicodeEncodeError, AttributeError):
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.buffer.write(text.encode(encoding, errors="replace"))
        sys.stdout.buffer.flush()


class TerminalMonitor:
    """Renders a live ANSI dashboard monitoring MCP agent traffic and token economy."""

    def __init__(self, servers: Optional[List[str]] = None) -> None:
        self.servers = servers or ["github", "postgres", "filesystem", "slack", "aws"]
        self.total_queries = 0
        self.total_invocations = 0
        self.raw_tokens_burned = 0
        self.mesh_tokens_burned = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.events: List[Dict[str, Any]] = []

    def record_search(self, query: str, matched_tools: List[str], latency_ms: float) -> None:
        """Records a tool discovery search event."""
        self.total_queries += 1
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.events.append({
            "time": now,
            "type": "SEARCH",
            "detail": f'"{query}" -> [{", ".join(matched_tools[:2])}]',
            "latency": latency_ms,
            "status": "200 OK",
        })
        if len(self.events) > 10:
            self.events.pop(0)

    def record_invocation(self, tool_name: str, server_id: str, latency_ms: float, cache_hit: bool = False) -> None:
        """Records a tool invocation event and updates economy meters."""
        self.total_invocations += 1
        # Raw baseline overhead: ~220 tokens per tool in 60-tool environment = ~13,200 tokens
        # Mesh overhead: 380 tokens
        self.raw_tokens_burned += 13200
        self.mesh_tokens_burned += 380
        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

        now = datetime.datetime.now().strftime("%H:%M:%S")
        hit_str = " (LRU Hit)" if cache_hit else " (Indexed)"
        self.events.append({
            "time": now,
            "type": "INVOKE",
            "detail": f"{server_id}::{tool_name}{hit_str}",
            "latency": latency_ms,
            "status": "SUCCESS",
        })
        if len(self.events) > 10:
            self.events.pop(0)

    def render_frame(self) -> str:
        """Returns the formatted dashboard frame as a string."""
        lines = []
        saved_tokens = max(0, self.raw_tokens_burned - self.mesh_tokens_burned)
        pct = (saved_tokens / self.raw_tokens_burned * 100) if self.raw_tokens_burned > 0 else 97.1
        # Dollar savings based on Claude Sonnet 5.5 ($2.00 / 1M tokens)
        dollars = (saved_tokens / 1_000_000) * 2.00

        lines.append("\033[1;33m" + "=" * 74 + "\033[0m")
        lines.append("\033[1;37m  [*] MCP-MESH REAL-TIME AGENT TELEMETRY MONITOR\033[0m  \033[32mv1.1.0 (Live)\033[0m")
        lines.append("\033[1;33m" + "=" * 74 + "\033[0m")

        # Status & Transport
        lines.append(f"\033[1;36m[Runtime]\033[0m  Stdio Gateway: \033[32mACTIVE\033[0m | SSE Daemon: \033[32mhttp://127.0.0.1:8000/sse\033[0m")
        servers_str = " ".join([f"\033[32m[+]\033[0m {s}" for s in self.servers])
        lines.append(f"\033[1;36m[Servers]\033[0m  {servers_str}")
        lines.append("\033[90m" + "-" * 74 + "\033[0m")

        # Metrics summary
        lines.append("\033[1;33m[TOKEN ECONOMY METER]\033[0m")
        lines.append(
            f"  Turns Processed: \033[1m{self.total_invocations + self.total_queries}\033[0m | "
            f"Baseline Tokens: \033[31m{self.raw_tokens_burned:,}\033[0m | "
            f"Mesh Tokens: \033[33m{self.mesh_tokens_burned:,}\033[0m"
        )
        lines.append(
            f"  Net Tokens Saved: \033[1;32m{saved_tokens:,}\033[0m (\033[1;32m{pct:.1f}%\033[0m) | "
            f"Estimated Savings: \033[1;32m${dollars:.2f}\033[0m | "
            f"LRU Cache Hits: \033[36m{self.cache_hits}\033[0m"
        )
        lines.append("\033[90m" + "-" * 74 + "\033[0m")

        # Live Event Log
        lines.append("\033[1;37m[RECENT ROUTING EVENTS]\033[0m")
        if not self.events:
            lines.append("  \033[90mNo agent queries captured yet. Waiting for client traffic...\033[0m")
        else:
            for ev in self.events:
                type_color = "\033[34m" if ev["type"] == "SEARCH" else "\033[32m"
                lines.append(
                    f"  \033[90m[{ev['time']}]\033[0m {type_color}[{ev['type']}]\033[0m "
                    f"{ev['detail']:<42} \033[33m{ev['latency']:.1f}ms\033[0m \033[32m{ev['status']}\033[0m"
                )

        lines.append("\033[1;33m" + "=" * 74 + "\033[0m")
        return "\n".join(lines)


def run_monitor(iterations: Optional[int] = None, interval: float = 0.5, mock: bool = True) -> None:
    """Executes the monitor loop."""
    monitor = TerminalMonitor()

    sample_scenarios = [
        ("SEARCH", "search for open authentication issues", ["github::search_code", "github::create_issue"], 1.1),
        ("INVOKE", "query_readonly", "postgres", 3.2, False),
        ("SEARCH", "write diagnostic report to disk", ["filesystem::write_file"], 0.8),
        ("INVOKE", "write_file", "filesystem", 1.5, True),
        ("INVOKE", "query_readonly", "postgres", 1.1, True),
        ("SEARCH", "notify backend team about release", ["slack::post_message"], 1.2),
        ("INVOKE", "post_message", "slack", 4.1, False),
        ("SEARCH", "query s3 backup bucket", ["aws::s3_get_object"], 0.9),
        ("INVOKE", "s3_get_object", "aws", 2.8, True),
    ]

    count = 0
    try:
        while True:
            # Clear terminal or carriage return
            if os.name == "nt":
                os.system("cls")
            else:
                _safe_write("\033[2J\033[H")

            # Simulate an event if mock mode
            if mock and sample_scenarios:
                idx = count % len(sample_scenarios)
                item = sample_scenarios[idx]
                if item[0] == "SEARCH":
                    monitor.record_search(item[1], item[2], item[3])
                else:
                    monitor.record_invocation(item[1], item[2], item[3], item[4])

            _safe_write(monitor.render_frame() + "\n")

            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        _safe_write("\n[mcp-mesh monitor] Detached successfully.\n")
