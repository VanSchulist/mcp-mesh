"""Persistent SQLite Telemetry Ledger for mcp-mesh.

Inspired by Simon Willison's llm architecture:
Zero-dependency, thread-safe, structured local SQLite logging of all tool invocations,
token savings, latency, and tool co-occurrence graphs.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class TelemetryLedger:
    """Thread-safe SQLite database for mcp-mesh session and call telemetry."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        if db_path is None:
            home = Path.home()
            mesh_dir = home / ".mcp-mesh"
            try:
                mesh_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = mesh_dir / "telemetry.db"
            except Exception:
                self.db_path = Path("mcp_mesh_telemetry.db")
        else:
            self.db_path = Path(db_path)
            if self.db_path.parent:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection with WAL mode enabled."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for high concurrent throughput
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
            except Exception:
                pass
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        """Initializes database tables and indexes."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                with conn:
                    conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS sessions (
                            session_id TEXT PRIMARY KEY,
                            started_at TEXT NOT NULL,
                            mode TEXT NOT NULL,
                            server_count INTEGER DEFAULT 0,
                            tool_count INTEGER DEFAULT 0
                        );

                        CREATE TABLE IF NOT EXISTS calls (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT NOT NULL,
                            session_id TEXT,
                            caller TEXT DEFAULT 'agent',
                            server_id TEXT NOT NULL,
                            tool_name TEXT NOT NULL,
                            latency_ms REAL NOT NULL,
                            success INTEGER NOT NULL,
                            cache_hit INTEGER DEFAULT 0,
                            tokens_baseline INTEGER DEFAULT 0,
                            tokens_mesh INTEGER DEFAULT 0,
                            tokens_saved INTEGER DEFAULT 0,
                            error_message TEXT
                        );

                        CREATE TABLE IF NOT EXISTS tool_cooccurrence (
                            tool_a TEXT NOT NULL,
                            tool_b TEXT NOT NULL,
                            count INTEGER DEFAULT 1,
                            last_seen TEXT NOT NULL,
                            PRIMARY KEY (tool_a, tool_b)
                        );

                        CREATE INDEX IF NOT EXISTS idx_calls_timestamp ON calls(timestamp);
                        CREATE INDEX IF NOT EXISTS idx_calls_tool ON calls(server_id, tool_name);
                        CREATE INDEX IF NOT EXISTS idx_calls_session ON calls(session_id);
                        """
                    )
            finally:
                conn.close()

    def start_session(self, session_id: str, mode: str, server_count: int, tool_count: int) -> None:
        """Records a new gateway runtime session."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO sessions (session_id, started_at, mode, server_count, tool_count)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, now, mode, server_count, tool_count),
                )
        except Exception:
            pass

    def log_call(
        self,
        server_id: str,
        tool_name: str,
        latency_ms: float,
        success: bool = True,
        cache_hit: bool = False,
        tokens_baseline: int = 0,
        tokens_mesh: int = 0,
        tokens_saved: int = 0,
        session_id: Optional[str] = None,
        caller: str = "agent",
        error_message: Optional[str] = None,
    ) -> None:
        """Logs an individual tool execution event and updates co-occurrence metrics."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        full_tool = f"{server_id}::{tool_name}"
        try:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO calls (
                        timestamp, session_id, caller, server_id, tool_name,
                        latency_ms, success, cache_hit, tokens_baseline,
                        tokens_mesh, tokens_saved, error_message
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now,
                        session_id,
                        caller,
                        server_id,
                        tool_name,
                        round(latency_ms, 2),
                        1 if success else 0,
                        1 if cache_hit else 0,
                        tokens_baseline,
                        tokens_mesh,
                        tokens_saved,
                        error_message,
                    ),
                )
        except Exception:
            pass

    def record_cooccurrence(self, tool_a: str, tool_b: str) -> None:
        """Records that tool_a and tool_b were invoked sequentially or together."""
        if tool_a == tool_b:
            return
        # Ensure canonical ordering
        if tool_a > tool_b:
            tool_a, tool_b = tool_b, tool_a
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            conn = self._get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO tool_cooccurrence (tool_a, tool_b, count, last_seen)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(tool_a, tool_b) DO UPDATE SET
                        count = count + 1,
                        last_seen = excluded.last_seen
                    """,
                    (tool_a, tool_b, now),
                )
        except Exception:
            pass

    def get_related_tools(self, tool_name: str, limit: int = 3) -> List[Tuple[str, int]]:
        """Returns tools frequently co-called with the given tool."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT 
                    CASE WHEN tool_a = ? THEN tool_b ELSE tool_a END AS related,
                    count
                FROM tool_cooccurrence
                WHERE tool_a = ? OR tool_b = ?
                ORDER BY count DESC
                LIMIT ?
                """,
                (tool_name, tool_name, tool_name, limit),
            )
            return [(row["related"], row["count"]) for row in cursor.fetchall()]
        except Exception:
            return []

    def get_summary(self) -> Dict[str, Any]:
        """Calculates global aggregate metrics across all recorded calls."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_calls,
                    COALESCE(SUM(tokens_saved), 0) as total_tokens_saved,
                    COALESCE(SUM(tokens_baseline), 0) as total_tokens_baseline,
                    COALESCE(SUM(tokens_mesh), 0) as total_tokens_mesh,
                    COALESCE(AVG(latency_ms), 0.0) as avg_latency_ms,
                    COALESCE(SUM(cache_hit), 0) as cache_hits,
                    COALESCE(SUM(success), 0) as successful_calls
                FROM calls
                """
            )
            row = cursor.fetchone()
            total_calls = row["total_calls"]
            cache_hits = row["cache_hits"]
            successful = row["successful_calls"]
            tokens_saved = row["total_tokens_saved"]

            # Estimate cost savings assuming blended $2.00 / 1M tokens (Claude Sonnet / GPT-6 tier)
            est_dollars_saved = round((tokens_saved / 1_000_000.0) * 2.00, 4)
            hit_ratio = round((cache_hits / total_calls * 100.0), 1) if total_calls > 0 else 0.0
            success_rate = round((successful / total_calls * 100.0), 1) if total_calls > 0 else 100.0

            return {
                "db_path": str(self.db_path),
                "total_calls": total_calls,
                "successful_calls": successful,
                "success_rate_percent": success_rate,
                "total_tokens_saved": tokens_saved,
                "total_tokens_baseline": row["total_tokens_baseline"],
                "total_tokens_mesh": row["total_tokens_mesh"],
                "avg_latency_ms": round(row["avg_latency_ms"], 2),
                "cache_hits": cache_hits,
                "cache_hit_ratio_percent": hit_ratio,
                "estimated_dollars_saved": est_dollars_saved,
            }
        except Exception as e:
            return {
                "db_path": str(self.db_path),
                "total_calls": 0,
                "total_tokens_saved": 0,
                "avg_latency_ms": 0.0,
                "error": str(e),
            }

    def query(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
        """Executes a read-only custom SQL query and returns rows as dictionaries."""
        sql_lower = sql.strip().lower()
        if not (sql_lower.startswith("select") or sql_lower.startswith("pragma") or sql_lower.startswith("explain")):
            raise ValueError("Only read-only SELECT queries are permitted.")

        conn = self._get_connection()
        cursor = conn.execute(sql, params or ())
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """Closes thread-local connections to release file locks on Windows."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None
