# 🩺 Log Doctor

Hermes Agent plugin that scans logs for errors, deduplicates them, and helps you diagnose and fix them — right from the web dashboard.

## Features

| Feature | Description |
|---------|-------------|
| 🔍 **Auto-scan** | Parses `~/.hermes/logs/errors.log` for WARNING/ERROR/CRITICAL entries |
| 📊 **Deduplication** | Identical errors grouped into one entry with occurrence count |
| 🧠 **Ignore memory** | Ignored errors stay ignored across restarts (SQLite-backed) |
| 🤖 **Agent analysis** | Ask Hermes to diagnose root cause via `scan_hermes_logs` tool |
| 🔧 **One-click fixes** | Agent-suggested fixes appear as "Apply Fix" button in dashboard |
| 🌐 **Dashboard tab** | Native web-dashboard integration (no CLI needed) |

## Screenshots

```
┌─ Log Doctor ──────────────────────────────────────────┐
│ [🔍 Scan Now]  Last scan: 2026-05-14T23:00 · 34 errors│
│                                                        │
│ Active (34)  Ignored (2)  Fixed (5)                    │
│                                                        │
│ ▶ WARNING  tirith spawn failed: Exec format error  ×35 │
│ ▶ WARNING  run_agent: Tool terminal returned error  ×12│
│ ▶ ERROR    ModuleNotFoundError: No module named '...' ×3│
│                                                        │
│   ┌─ Expanded ────────────────────────────────────┐   │
│   │ First Seen: 2026-05-10T...                    │   │
│   │ Raw Log: [full line context]                  │   │
│   │ Fix: Update binary path in config.yaml        │   │
│   │ [Ask Agent] [Ignore] [Apply Fix]              │   │
│   └───────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

## Installation

```bash
# 1. Clone to Hermes plugins directory
git clone https://github.com/YOUR_USER/hermes-log-doctor.git ~/.hermes/plugins/log-doctor

# 2. Enable in config.yaml (add to plugins.enabled)
hermes plugins enable log-doctor

# 3. Restart dashboard
systemctl --user restart hermes-dashboard
```

Or from the dashboard:
1. **Plugins Hub** → search "log-doctor" → **Install**
2. Click **Scan Now** to populate the database
3. Browse errors under the **Log Doctor** tab

## Agent Tools

| Tool | Description |
|------|-------------|
| `scan_hermes_logs` | Scan error logs, deduplicate, store in DB |
| `get_log_errors` | Query stored errors by status (active/ignored/fixed/all) |
| `analyze_log_error` | Get full context for one error entry |
| `suggest_error_fix` | Record a fix description + shell command |
| `apply_error_fix` | Execute the stored fix |
| `ignore_log_error` | Permanently ignore an error pattern |

Example agent interaction:
```
User: "Check why I have so many errors in the logs"
Agent: [calls scan_hermes_logs] → 34 active errors
       [calls analyze_log_error id=1] → tirith binary missing
       [calls suggest_error_fix id=1, description="...", command="..."]
       → Fix stored. User can apply it from the dashboard.
```

## API

All endpoints under `/api/plugins/log-doctor/` (requires dashboard session token).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/errors?status=active` | List errors |
| `GET` | `/errors/ignored` | List ignored errors |
| `GET` | `/errors/:id` | Get error detail |
| `POST` | `/scan` | Trigger log scan |
| `POST` | `/errors/:id/ignore` | Ignore an error |
| `POST` | `/errors/:id/unignore` | Un-ignore |
| `POST` | `/errors/:id/fix` | Execute stored fix |
| `POST` | `/errors/:id/analyze` | Get analysis prompt for agent |
| `GET` | `/stats` | Summary counts |
| `GET` | `/ui` | Standalone HTML UI |

## Database

SQLite at `~/.hermes/log-doctor.db`. Auto-created.

**Deduplication**: `SHA256(source + error_type + message)` — identical errors merged.

**Status flow**: `active` → `ignored` (manual) → `fixed` (after fix applied).

## License

MIT — do whatever you want with it.
