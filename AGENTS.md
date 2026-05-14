# Log Doctor — Development Guide

Instructions for AI coding assistants working on the log-doctor plugin.

## Project Structure

```
log-doctor/
├── plugin.yaml              # Agent-plugin manifest (kind: standalone)
├── __init__.py               # Hermes plugin register(ctx) entry point
├── tools.py                  # Agent tool handlers (scan, analyze, fix, ignore)
├── schemas.py                # JSON schemas for all tools
├── db.py                     # SQLite persistence layer
├── SKILL.md                  # Agent skill — loaded by Hermes when tool is called
├── LICENSE                   # MIT
├── AGENTS.md                 # This file
├── README.md                 # User-facing docs
└── dashboard/
    ├── manifest.json          # Dashboard tab declaration (name, icon, entry, api)
    ├── plugin_api.py          # FastAPI router mounted at /api/plugins/log-doctor/
    └── dist/
        ├── index.js           # Frontend React component (vanilla JS via SDK)
        └── style.css          # Stylesheet (currently empty — styles inline in JS)
```

## Development Environment

The plugin runs inside the Hermes Agent process. No separate venv needed.

```bash
# Deploy to Hermes
cp -r . ~/.hermes/plugins/log-doctor/

# Enable in config.yaml
#   plugins.enabled: [log-doctor]

# Restart dashboard
systemctl --user restart hermes-dashboard

# Watch logs
tail -f ~/.hermes/logs/agent.log | grep -i log-doctor
```

## Architecture

### Two surfaces, one database

```
┌─────────────────────┐     ┌──────────────────────┐
│   Agent Tools (6)    │     │  Dashboard API       │
│  scan_hermes_logs    │     │  /api/plugins/       │
│  get_log_errors      │     │    log-doctor/*      │
│  analyze_log_error   │     │                      │
│  suggest_error_fix   │────▶│  SQLite              │
│  apply_error_fix     │     │  ~/.hermes/          │
│  ignore_log_error    │     │    log-doctor.db     │
└─────────────────────┘     └──────────────────────┘
                                    │
                             ┌──────▼──────┐
                             │  Dashboard   │
                             │  UI (React)  │
                             └─────────────┘
```

### Tool handlers

All handlers in `tools.py` follow the Hermes plugin contract:
- Accept `(args, **kwargs)` — `**kwargs` required for forward compatibility
- Return `json.dumps(...)` — NEVER a raw dict
- Catch all exceptions and return `{"ok": False, "error": str(e)}`

### Dashboard plugin

The dashboard surface uses two files:
- `manifest.json` — declares tab name, icon, JS entry, API file
- `plugin_api.py` — FastAPI `APIRouter` with a `router` attribute
- `dist/index.js` — React component using `window.__HERMES_PLUGIN_SDK__`

The JS module calls `window.__HERMES_PLUGINS__.register('log-doctor', Component)`.

The API is mounted at `/api/plugins/log-doctor/` by the dashboard's plugin loader.

## Import Rules

**CRITICAL**: The plugin's `tools.py` module name conflicts with Hermes's built-in `tools/` package. Use relative imports within the plugin package:

```python
# In __init__.py (loaded as a package by the plugin system)
from .tools import handler_scan_logs   # ✓ relative
```

```python
# In tools.py (may be loaded standalone by dashboard API)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # ✓ absolute with path injection
```

```python
# In dashboard/plugin_api.py (loaded via importlib)
import importlib.util
spec = importlib.util.spec_from_file_location("log_doctor_db", str(PLUGIN_DIR / "db.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
```

## Database

SQLite at `~/.hermes/log-doctor.db`. Auto-created on first use.

Tables:
- `error_entries` — deduplicated errors with hash, count, status, fix info
- `scan_runs` — audit log of each scan

Deduplication key: `SHA256(source|error_type|message)[:16]`

Status flow: `active → ignored (manual) → fixed (after fix applied)`

## Common Pitfalls

1. **`useState` must be called, not referenced**: `useState('default')` returns `[value, setter]`. Just writing `var s = useState` does nothing.
2. **Dashboard JS entry must register**: Failure to call `PLUGINS.register(...)` results in blank tab.
3. **Handler must return JSON string**: Returning a dict causes "unhashable type" errors.
4. **`tools` import collision**: Never do `from tools import ...` in plugin code — always use `.tools` or importlib.
