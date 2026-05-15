"""Log Doctor — plugin registration.

Called by Hermes plugin loader on startup.
Registers agent tools for log scanning, error analysis, and fix management.
"""

from __future__ import annotations


def register(ctx) -> None:
    from .scanner import (
        handler_scan_logs,
        handler_get_errors,
        handler_analyze_error,
        handler_suggest_fix,
        handler_apply_fix,
        handler_ignore_error,
    )
    from .schemas import (
        SCAN_LOGS_SCHEMA,
        GET_ERRORS_SCHEMA,
        ANALYZE_ERROR_SCHEMA,
        SUGGEST_FIX_SCHEMA,
        APPLY_FIX_SCHEMA,
        IGNORE_ERROR_SCHEMA,
    )

    T = "log-doctor"  # toolset name

    ctx.register_tool(
        name="scan_hermes_logs",
        toolset=T,
        description=(
            "Scan Hermes agent/error logs for WARNING and ERROR entries. "
            "Deduplicates identical errors and tracks occurrence counts. "
            "Use when investigating repeated errors in agent.log or errors.log. "
            "Returns active errors plus scan statistics. "
            "Previously-ignored errors are automatically skipped."
        ),
        handler=handler_scan_logs,
        schema=SCAN_LOGS_SCHEMA,
    )

    ctx.register_tool(
        name="get_log_errors",
        toolset=T,
        description=(
            "Get stored error entries from Log Doctor database. "
            "Filter by status: 'active' (default), 'ignored', 'fixed', or 'all'. "
            "Returns error list with counts, first/last seen timestamps, and fix status."
        ),
        handler=handler_get_errors,
        schema=GET_ERRORS_SCHEMA,
    )

    ctx.register_tool(
        name="analyze_log_error",
        toolset=T,
        description=(
            "Get full details for a specific error entry including full context lines. "
            "Use after scan_hermes_logs to deep-dive into a particular error. "
            "Returns the complete error record: message, context, file path, line number, "
            "existing fix suggestion (if any), and occurrence history."
        ),
        handler=handler_analyze_error,
        schema=ANALYZE_ERROR_SCHEMA,
    )

    ctx.register_tool(
        name="suggest_error_fix",
        toolset=T,
        description=(
            "Store a fix suggestion for an error entry. "
            "Call after analyzing an error — provide a human-readable root cause description "
            "and an optional shell command to fix it. "
            "The fix will appear in the Log Doctor dashboard tab with an 'Apply Fix' button."
        ),
        handler=handler_suggest_fix,
        schema=SUGGEST_FIX_SCHEMA,
    )

    ctx.register_tool(
        name="apply_error_fix",
        toolset=T,
        description=(
            "Execute the stored fix for an error entry and mark it as fixed. "
            "Use 'dry_run': true to preview without executing."
        ),
        handler=handler_apply_fix,
        schema=APPLY_FIX_SCHEMA,
    )

    ctx.register_tool(
        name="ignore_log_error",
        toolset=T,
        description=(
            "Ignore a specific error entry. Future occurrences of the same error "
            "will be automatically skipped during log scans. "
            "Ignored errors can still be viewed via get_log_errors with status='ignored'."
        ),
        handler=handler_ignore_error,
        schema=IGNORE_ERROR_SCHEMA,
    )
