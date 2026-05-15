"""

Each handler returns a JSON string (required by Hermes plugin contract).
All handlers accept **kwargs for forward compatibility.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import sys
from pathlib import Path

# Make plugin-local modules importable when loaded standalone (not as a package)
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from hermes_constants import get_hermes_home

from db import (
    connect,
    init_db,
    upsert_error,
    list_errors,
    get_error,
    ignore_error as db_ignore,
    set_fix,
    apply_fix as db_apply_fix,
    get_stats,
    record_scan,
    gc_deleted_errors,
    _error_hash,
)

log = logging.getLogger(__name__)

# Regex for parsing Hermes log lines.
# Format: 2026-05-14 22:00:07,123 WARNING [session_id] module: message
LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(WARNING|ERROR|CRITICAL)\s+"
    r"\[([^\]]+)\]\s+"
    r"(.+)$"
)

DEFAULT_LOG = get_hermes_home() / "logs" / "errors.log"


def _parse_log_line(line: str) -> dict | None:
    m = LOG_PATTERN.match(line.strip())
    if not m:
        return None
    ts, level, session, message = m.groups()
    return {
        "timestamp": ts,
        "level": level,
        "session": session,
        "message": message.strip(),
    }


def _scan_log_file(log_file: Path, limit: int = 50) -> dict:
    """Scan a log file and upsert error entries into the database.

    Returns summary dict for agent consumption.
    """
    if not log_file.exists():
        return {"ok": False, "error": f"Log file not found: {log_file}"}

    lines = log_file.read_text(errors="replace").splitlines()
    total_lines = len(lines)

    entries = []
    for line in lines:
        parsed = _parse_log_line(line)
        if parsed:
            # Extract source file reference from message if present
            # e.g., "FileNotFoundError: /opt/data/cron/..." or
            #        "file_path.py:42: SomeError"
            source = str(log_file)
            file_path = ""
            line_number = 0

            # Try to find file:line pattern
            file_match = re.search(
                r'([/\w.]+\.(?:py|yaml|json|toml|sh|conf|md))(?::(\d+))?',
                parsed["message"],
            )
            if file_match:
                file_path = file_match.group(1)
                ln = file_match.group(2)
                if ln:
                    line_number = int(ln)

            entries.append({
                "source": source,
                "error_type": parsed["level"],
                "message": parsed["message"],
                "context": line,
                "file_path": file_path,
                "line_number": line_number,
            })

    # Upsert into DB with dedup
    conn = connect()
    init_db(conn)
    new_count = 0
    ignored_count = 0

    try:
        for entry in entries[:limit]:
            record = upsert_error(
                conn,
                source=entry["source"],
                error_type=entry["error_type"],
                message=entry["message"],
                context=entry["context"],
                file_path=entry["file_path"],
                line_number=entry["line_number"],
            )
            if record["count"] == 1:
                new_count += 1
            if record["status"] == "ignored":
                ignored_count += 1

        record_scan(
            conn,
            log_file=str(log_file),
            total_lines=total_lines,
            total_errors=len(entries),
            new_errors=new_count,
            ignored_skipped=ignored_count,
        )

        # GC: remove deleted entries whose errors no longer exist in logs
        live_hashes = {_error_hash(e["source"], e["error_type"], e["message"]) for e in entries}
        gc_count = gc_deleted_errors(conn, live_hashes)

        # Return active errors for agent to see
        active = list_errors(conn, "active")
        stats = get_stats(conn)

        return {
            "ok": True,
            "log_file": str(log_file),
            "total_lines": total_lines,
            "total_errors": len(entries),
            "new_errors": new_count,
            "ignored_skipped": ignored_count,
            "active_errors": active[:limit],
            "stats": stats,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def handler_scan_logs(args, **kwargs) -> str:
    """Scan Hermes logs for WARNING/ERROR entries, deduplicate, and return summary."""
    try:
        log_file = args.get("log_file", "") or str(DEFAULT_LOG)
        limit = int(args.get("limit", 50))
        result = _scan_log_file(Path(log_file), limit=limit)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def handler_get_errors(args, **kwargs) -> str:
    """Get stored error entries filtered by status."""
    try:
        status = args.get("status", "active")
        conn = connect()
        init_db(conn)
        try:
            if status == "all":
                active = list_errors(conn, "active")
                ignored = list_errors(conn, "ignored")
                fixed = list_errors(conn, "fixed")
                errors = active + ignored + fixed
            else:
                errors = list_errors(conn, status)
            stats = get_stats(conn)
            return json.dumps(
                {"ok": True, "errors": errors, "stats": stats},
                ensure_ascii=False, default=str,
            )
        finally:
            conn.close()
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def handler_analyze_error(args, **kwargs) -> str:
    """Get full details for a specific error entry."""
    try:
        error_id = int(args["error_id"])
        conn = connect()
        init_db(conn)
        try:
            record = get_error(conn, error_id)
            if not record:
                return json.dumps({"ok": False, "error": f"Error {error_id} not found"})
            return json.dumps({"ok": True, "error": record}, ensure_ascii=False, default=str)
        finally:
            conn.close()
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def handler_suggest_fix(args, **kwargs) -> str:
    """Store an agent-suggested fix for an error entry."""
    try:
        error_id = int(args["error_id"])
        description = args.get("description", "")
        command = args.get("command", "")
        conn = connect()
        init_db(conn)
        try:
            record = get_error(conn, error_id)
            if not record:
                return json.dumps({"ok": False, "error": f"Error {error_id} not found"})
            set_fix(conn, error_id, description, command)
            updated = get_error(conn, error_id)
            return json.dumps(
                {"ok": True, "error": updated, "fix_stored": True},
                ensure_ascii=False, default=str,
            )
        finally:
            conn.close()
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def handler_apply_fix(args, **kwargs) -> str:
    """Apply the stored fix for an error entry."""
    try:
        error_id = int(args["error_id"])
        dry_run = args.get("dry_run", False)
        conn = connect()
        init_db(conn)
        try:
            record = get_error(conn, error_id)
            if not record:
                return json.dumps({"ok": False, "error": f"Error {error_id} not found"})
            if not record.get("fix_command"):
                return json.dumps({"ok": False, "error": "No fix command stored"})
            if dry_run:
                return json.dumps({
                    "ok": True,
                    "dry_run": True,
                    "would_execute": record["fix_command"],
                })
            # In production, the fix is executed by the dashboard API
            # via POST /api/plugins/log-doctor/errors/:id/fix
            # Here we just mark it as applied.
            updated = db_apply_fix(conn, error_id)
            return json.dumps(
                {"ok": True, "fix_applied": True, "error": updated},
                ensure_ascii=False, default=str,
            )
        finally:
            conn.close()
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def handler_ignore_error(args, **kwargs) -> str:
    """Ignore an error entry. Future occurrences won't be shown."""
    try:
        error_id = int(args["error_id"])
        conn = connect()
        init_db(conn)
        try:
            record = get_error(conn, error_id)
            if not record:
                return json.dumps({"ok": False, "error": f"Error {error_id} not found"})
            db_ignore(conn, error_id)
            return json.dumps(
                {"ok": True, "ignored": True, "error_id": error_id},
                ensure_ascii=False,
            )
        finally:
            conn.close()
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})
