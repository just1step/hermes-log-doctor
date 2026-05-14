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
    ├── plugin_api.py          # FastAPI router + background analysis threads
    └── dist/
        ├── index.js           # Frontend React component (vanilla JS via SDK)
        └── style.css          # Stylesheet (currently empty — styles inline in JS)
```

## Development Environment

```bash
# Deploy to Hermes
cp -r . ~/.hermes/plugins/log-doctor/

# Restart dashboard
systemctl --user restart hermes-dashboard

# Watch logs
tail -f ~/.hermes/logs/agent.log | grep -i log-doctor
```

## Architecture

### Three surfaces, one database

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
                  ┌─────────────────▼─────┐
                  │  Analysis Engine      │
                  │  (background thread)  │
                  │  AIAgent + SessionDB  │
                  └─────────┬─────────────┘
                            │
                   ┌────────▼────────┐
                   │  Dashboard UI   │
                   │  (React SDK)    │
                   │  polling loop   │
                   └─────────────────┘
```

### Error Analysis Flow

1. User clicks "Ask Agent" → `POST /errors/:id/analyze`
2. Backend creates queue + starts background thread
3. Thread creates `AIAgent` with `session_id="log-doctor-session"` and `SessionDB`
4. Agent runs analysis prompt with strict rules:
   - **ONLY** allowed: `analyze_log_error` + `suggest_error_fix`
   - **FORBIDDEN**: terminal, patch, write_file, any state-changing tool
5. Frontend polls `GET /errors/:id/analysis-status` every 2s
6. On completion, stores `fix_description` in SQLite → survives page refresh
7. User can click "Apply Fix" to execute the stored `fix_command`

### Session Strategy

All analyses share one session: `log-doctor-session`. Only ONE analysis runs at a time
(global `analysisRunning` lock in frontend). Other "Ask Agent" buttons show "⏳ Waiting..."
until the running analysis completes.

### Button States

| State | Ask Agent | Apply Fix | Ignore |
|-------|-----------|-----------|--------|
| Not analyzed | 🟢 Ask Agent | 🔒 greyed | 🟢 Ignore |
| Running (this) | 🔒 Analyzing... | 🔒 greyed | 🟢 Ignore |
| Running (other) | ⏳ Waiting... | 🔒 greyed | 🟢 Ignore |
| Done | ✅ Analyzed (grey) | 🟢 enabled | 🟢 Ignore |
| Failed | ✗ failed (grey) | 🔒 greyed | 🟢 Ignore |

### Status Badges

Each error item shows a colored badge in the header:
- `analyzing...` (blue) — analysis in progress
- `✓ analyzed` (green) — analysis complete
- `✗ failed` (red) — analysis failed
- (none) — not yet analyzed

## Import Rules

**CRITICAL**: The plugin's `tools.py` module name conflicts with Hermes's built-in `tools/` package.

```python
# In __init__.py (loaded as a package by the plugin system)
from .tools import handler_scan_logs   # ✓ relative

# In tools.py (may be loaded standalone by dashboard API)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import connect  # ✓ absolute with path injection

# In dashboard/plugin_api.py (loaded via importlib to avoid collision)
import importlib.util
spec = importlib.util.spec_from_file_location("log_doctor_db", str(PLUGIN_DIR / "db.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["db"] = mod  # register before exec for inter-module refs
spec.loader.exec_module(mod)
```

## Database

SQLite at `~/.hermes/log-doctor.db`. Auto-created on first use.

Tables:
- `error_entries` — deduplicated errors (hash, type, message, context, count, status, fix_description, fix_command)
- `scan_runs` — audit log of each scan

Deduplication key: `SHA256(source|error_type|message)[:16]`

Status flow: `active → ignored (manual) → fixed (after fix applied)`

## Common Pitfalls

1. **`useState` must be CALLED**: `useState('default')` returns `[value, setter]`. Writing `var s = useState` references the function, not the result.
2. **Dashboard JS entry must register**: Must call `PLUGINS.register('log-doctor', Component)` or tab is blank.
3. **Handler must return JSON string**: Returning a dict causes "unhashable type" errors.
4. **`tools` import collision**: Never do `from tools import ...` in plugin code.
5. **SQLite cross-thread**: Analysis thread must create its own DB connection. Cannot reuse the dashboard main-thread connection.
6. **Variable rename sync**: When renaming variables (`showResult`→`isDone`), update ALL references.
7. **No git push without user approval**: Per system_prompt: commit+push requires explicit user confirmation.
8. **Agent analysis sandbox**: Agent prompt must explicitly forbid terminal/patch/write_file — diagnosis only.
