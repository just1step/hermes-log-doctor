"""Log Doctor — database layer.

SQLite-backed persistence for error entries, scan runs, and ignore state.
Database auto-created at ~/.hermes/log-doctor.db on first use.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from hermes_constants import get_hermes_home

DB_PATH = get_hermes_home() / "log-doctor.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error_hash(source: str, error_type: str, message: str) -> str:
    raw = f"{source}|{error_type}|{message}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS error_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_hash TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            error_type TEXT NOT NULL,
            message TEXT NOT NULL,
            context TEXT,
            file_path TEXT,
            line_number INTEGER,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            ignored_at TEXT,
            fix_description TEXT,
            fix_command TEXT,
            fix_applied_at TEXT,
            fix_result TEXT
        );

        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scanned_at TEXT NOT NULL,
            log_file TEXT,
            total_lines INTEGER,
            total_errors INTEGER,
            new_errors INTEGER,
            ignored_skipped INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_errors_hash ON error_entries(error_hash);
        CREATE INDEX IF NOT EXISTS idx_errors_status ON error_entries(status);
        CREATE INDEX IF NOT EXISTS idx_errors_last_seen ON error_entries(last_seen);
    """)


def upsert_error(
    conn: sqlite3.Connection,
    source: str,
    error_type: str,
    message: str,
    context: str = "",
    file_path: str = "",
    line_number: int = 0,
) -> dict:
    """Insert or update a deduplicated error entry. Returns the record as dict."""
    h = _error_hash(source, error_type, message)
    now = _now_iso()

    existing = conn.execute(
        "SELECT id, count, status FROM error_entries WHERE error_hash = ?",
        (h,),
    ).fetchone()

    if existing:
        # Update count and last_seen, but respect ignored status
        new_count = existing["count"] + 1
        conn.execute(
            "UPDATE error_entries SET count = ?, last_seen = ? WHERE error_hash = ?",
            (new_count, now, h),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM error_entries WHERE error_hash = ?", (h,)
        ).fetchone())
    else:
        conn.execute(
            """INSERT INTO error_entries
               (error_hash, source, error_type, message, context,
                file_path, line_number, first_seen, last_seen, count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (h, source, error_type, message, context,
             file_path, line_number, now, now),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM error_entries WHERE error_hash = ?", (h,)
        ).fetchone())


def list_errors(conn: sqlite3.Connection, status: str = "active") -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM error_entries WHERE status = ? ORDER BY last_seen DESC",
        (status,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_error(conn: sqlite3.Connection, error_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM error_entries WHERE id = ?", (error_id,)
    ).fetchone()
    return dict(row) if row else None


def ignore_error(conn: sqlite3.Connection, error_id: int) -> bool:
    now = _now_iso()
    conn.execute(
        "UPDATE error_entries SET status = 'ignored', ignored_at = ? WHERE id = ?",
        (now, error_id),
    )
    conn.commit()
    return True


def unignore_error(conn: sqlite3.Connection, error_id: int) -> bool:
    conn.execute(
        "UPDATE error_entries SET status = 'active', ignored_at = NULL WHERE id = ?",
        (error_id,),
    )
    conn.commit()
    return True


def set_fix(
    conn: sqlite3.Connection,
    error_id: int,
    description: str,
    command: str,
) -> bool:
    conn.execute(
        "UPDATE error_entries SET fix_description = ?, fix_command = ? WHERE id = ?",
        (description, command, error_id),
    )
    conn.commit()
    return True


def apply_fix(conn: sqlite3.Connection, error_id: int) -> dict:
    """Mark fix as applied. Returns the record."""
    now = _now_iso()
    conn.execute(
        "UPDATE error_entries SET status = 'fixed', fix_applied_at = ? WHERE id = ?",
        (now, error_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM error_entries WHERE id = ?", (error_id,)
    ).fetchone()
    return dict(row) if row else {}


def record_scan(
    conn: sqlite3.Connection,
    log_file: str,
    total_lines: int,
    total_errors: int,
    new_errors: int,
    ignored_skipped: int,
) -> int:
    now = _now_iso()
    cur = conn.execute(
        """INSERT INTO scan_runs
           (scanned_at, log_file, total_lines, total_errors, new_errors, ignored_skipped)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (now, log_file, total_lines, total_errors, new_errors, ignored_skipped),
    )
    conn.commit()
    return cur.lastrowid


def get_stats(conn: sqlite3.Connection) -> dict:
    active = conn.execute(
        "SELECT COUNT(*) as n FROM error_entries WHERE status = 'active'"
    ).fetchone()["n"]
    ignored = conn.execute(
        "SELECT COUNT(*) as n FROM error_entries WHERE status = 'ignored'"
    ).fetchone()["n"]
    fixed = conn.execute(
        "SELECT COUNT(*) as n FROM error_entries WHERE status = 'fixed'"
    ).fetchone()["n"]
    last_scan = conn.execute(
        "SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {
        "active": active,
        "ignored": ignored,
        "fixed": fixed,
        "last_scan": dict(last_scan) if last_scan else None,
    }
