"""Log Doctor — JSON schemas for agent tools."""

SCAN_LOGS_SCHEMA = {
    "type": "object",
    "properties": {
        "log_file": {
            "type": "string",
            "description": "Path to log file to scan. Default: ~/.hermes/logs/errors.log",
            "default": "",
        },
        "limit": {
            "type": "integer",
            "description": "Max number of error entries to return. Default: 50",
            "default": 50,
        },
    },
    "required": [],
}

ANALYZE_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error_id": {
            "type": "integer",
            "description": "The error entry ID to analyze",
        },
    },
    "required": ["error_id"],
}

SUGGEST_FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "error_id": {
            "type": "integer",
            "description": "The error entry ID to suggest a fix for",
        },
        "description": {
            "type": "string",
            "description": "Human-readable description of the root cause and fix",
        },
        "command": {
            "type": "string",
            "description": "Shell command to execute the fix (or empty string for manual fix)",
        },
    },
    "required": ["error_id", "description", "command"],
}

APPLY_FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "error_id": {
            "type": "integer",
            "description": "The error entry ID to apply the stored fix for",
        },
        "dry_run": {
            "type": "boolean",
            "description": "If true, show what would be done without executing",
            "default": False,
        },
    },
    "required": ["error_id"],
}

IGNORE_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error_id": {
            "type": "integer",
            "description": "The error entry ID to ignore",
        },
    },
    "required": ["error_id"],
}

GET_ERRORS_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["active", "ignored", "fixed", "all"],
            "description": "Filter by error status. Default: active",
            "default": "active",
        },
    },
    "required": [],
}
