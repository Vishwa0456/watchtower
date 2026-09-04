"""SQLite-backed storage for check results and remediation actions.

Uses stdlib sqlite3 directly (no ORM) - deliberate choice for a project
this size. An ORM would be overkill for two tables and adds a dependency
without adding clarity.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from watchtower.checks import CheckResult
from watchtower.remediation import RemediationResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS check_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    threshold REAL NOT NULL,
    breached INTEGER NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS remediation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    check_name TEXT NOT NULL,
    remediation_name TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    applied INTEGER NOT NULL,
    detail TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_check_results_timestamp ON check_results(timestamp);
"""


class Storage:
    """SQLite connection, opened per-call rather than held open for the
    life of the object. This costs a little connection-setup overhead but
    makes Storage safe to share across threads - which matters once the
    web dashboard (Flask, multi-threaded by default) reads from the same
    database a background monitor loop is writing to. A single long-lived
    connection is NOT thread-safe in sqlite3 without extra locking; this
    sidesteps that entirely.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_check(self, result: CheckResult) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO check_results (timestamp, name, value, threshold, breached, message) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (result.timestamp, result.name, result.value, result.threshold,
                 int(result.breached), result.message),
            )

    def record_remediation(self, check_name: str, result: RemediationResult, timestamp: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO remediation_results "
                "(timestamp, check_name, remediation_name, dry_run, applied, detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (timestamp, check_name, result.name, int(result.dry_run), int(result.applied), result.detail),
            )

    def recent_incidents(self, limit: int = 20) -> list[sqlite3.Row]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM check_results WHERE breached = 1 "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def history(self, check_name: str, limit: int = 60) -> list[sqlite3.Row]:
        """Returns the most recent `limit` results for one check, oldest
        first (chart-ready order). Used to render trend charts - unlike
        recent_incidents, this includes non-breached values too, since a
        chart needs the full trend, not just the breach moments.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT timestamp, value FROM check_results WHERE name = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (check_name, limit),
            )
            rows = cur.fetchall()
            return list(reversed(rows))

    def close(self) -> None:
        pass  # no persistent connection to close; kept for API compatibility

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
