---
name: log-doctor
description: Hermes log error scanner — scan, analyze, fix, and ignore repeated errors with persistent memory
version: 1.0.0
---

# Log Doctor

## When to use

- User reports seeing repeated errors in Hermes logs
- User asks "what's wrong with my Hermes?" or "why is this error happening?"
- User wants to understand and fix recurring log errors
- User wants to clean up ignored errors or review fix history

## How it works

### Scan
Run `scan_hermes_logs` to scan `~/.hermes/logs/errors.log` (or any log file).
The tool deduplicates identical errors by computing a hash of (source + type + message).
Duplicates increment a `count` field and update `last_seen`.
Previously-ignored errors are skipped automatically.

### Analyze
After scanning, use `analyze_log_error(error_id=N)` to get full context for a specific error.
The returned record includes the raw log line, extracted file path and line number,
any existing fix suggestion, and occurrence count.

### Fix
Call `suggest_error_fix(error_id=N, description="...", command="...")` to record a fix.
The description should explain the root cause in plain language.
The command should be a shell command that fixes it (or empty string for manual fix).

Then call `apply_error_fix(error_id=N)` to execute the fix.
The error status changes to `fixed` and won't appear in active scans.

### Ignore
Call `ignore_log_error(error_id=N)` to ignore an error permanently.
Future scans will skip it. View ignored errors with `get_log_errors(status='ignored')`.

### Query
Use `get_log_errors(status='active')` to see current errors.
Use `get_log_errors(status='all')` for everything including ignored and fixed.

## Dashboard

Errors also appear in the Hermes web dashboard under the "Log Doctor" tab.
The dashboard shows a list of errors with expand/collapse for details.
Each error has "Fix" and "Ignore" buttons.
The tab bar switches between Active and Ignored views.

## Database

Persistent state is stored at `~/.hermes/log-doctor.db` (SQLite).
Tables: `error_entries`, `scan_runs`.
Auto-created on first use.
