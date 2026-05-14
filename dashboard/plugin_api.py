"""Log Doctor — dashboard API routes.

Mounted at /api/plugins/log-doctor/ by the dashboard plugin system.
Provides CRUD for error entries, log scanning, fix execution, and serves the UI page.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from hermes_constants import get_hermes_home

# Ensure the plugin's own modules are importable
import importlib.util
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_HERMES_AGENT_DIR = Path("/home/j1s/.hermes/hermes-agent")

def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

# Load plugin-local modules via importlib to avoid conflict with hermes-agent's tools/ package
_spec_db = importlib.util.spec_from_file_location(
    "log_doctor_db", str(_PLUGIN_DIR / "db.py")
)
_db_mod = importlib.util.module_from_spec(_spec_db)
sys.modules["log_doctor_db"] = _db_mod  # register before exec for inter-module refs
_spec_db.loader.exec_module(_db_mod)

# Also make db importable for tools.py
sys.modules["db"] = _db_mod

_spec_tools = importlib.util.spec_from_file_location(
    "log_doctor_tools", str(_PLUGIN_DIR / "tools.py")
)
_tools_mod = importlib.util.module_from_spec(_spec_tools)
sys.modules["log_doctor_tools"] = _tools_mod
_spec_tools.loader.exec_module(_tools_mod)

# Unpack needed symbols
_db_connect = _db_mod.connect
_db_init = _db_mod.init_db
_db_list = _db_mod.list_errors
_db_get = _db_mod.get_error
_db_ignore = _db_mod.ignore_error
_db_unignore = _db_mod.unignore_error
_db_set_fix = _db_mod.set_fix
_db_apply = _db_mod.apply_fix
_db_stats = _db_mod.get_stats
_tools_scan = _tools_mod._scan_log_file

log = logging.getLogger(__name__)

router = APIRouter()

_db = None


def _get_db():
    global _db
    if _db is None:
        _db = _db_connect()
        _db_init(_db)
    return _db


DEFAULT_LOG = get_hermes_home() / "logs" / "errors.log"


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@router.get("/errors")
def api_list_errors(
    status: str = Query("active", description="active | ignored | fixed | all"),
    error_type: str = Query("", description="Filter by type: WARNING, ERROR, CRITICAL (empty = all)"),
    limit: int = Query(200, ge=1, le=1000),
):
    conn = _get_db()
    try:
        type_clause = ""
        params: list = []
        if status == "all":
            if error_type:
                rows = conn.execute(
                    "SELECT * FROM error_entries WHERE error_type = ? ORDER BY last_seen DESC",
                    (error_type,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM error_entries ORDER BY last_seen DESC"
                ).fetchall()
            errors = [dict(r) for r in rows]
        else:
            if error_type:
                rows = conn.execute(
                    "SELECT * FROM error_entries WHERE status = ? AND error_type = ? ORDER BY last_seen DESC",
                    (status, error_type)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM error_entries WHERE status = ? ORDER BY last_seen DESC",
                    (status,)
                ).fetchall()
            errors = [dict(r) for r in rows]
        stats = _db_stats(conn)
        return {"ok": True, "errors": errors[:limit], "stats": stats}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/errors/ignored")
def api_list_ignored(limit: int = Query(200, ge=1, le=1000)):
    conn = _get_db()
    try:
        errors = _db_list(conn, "ignored")
        stats = _db_stats(conn)
        return {"ok": True, "errors": errors[:limit], "stats": stats}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/errors/{error_id}")
def api_get_error(error_id: int):
    conn = _get_db()
    try:
        record = conn.execute(
            "SELECT * FROM error_entries WHERE id = ?", (error_id,)
        ).fetchone()
        if not record:
            raise HTTPException(status_code=404, detail=f"Error {error_id} not found")
        return {"ok": True, "error": dict(record)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stats")
def api_get_stats():
    conn = _get_db()
    try:
        return {"ok": True, "stats": _db_stats(conn)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/scan")
def api_scan(log_file: str = "", limit: int = 200):
    log_path = Path(log_file) if log_file else DEFAULT_LOG
    try:
        result = _tools_scan(log_path, limit=limit)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/errors/{error_id}/ignore")
def api_ignore_error(error_id: int):
    conn = _get_db()
    try:
        record = _db_get(conn, error_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Error {error_id} not found")
        _db_ignore(conn, error_id)
        return {"ok": True, "ignored": True, "error_id": error_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/errors/{error_id}/unignore")
def api_unignore_error(error_id: int):
    conn = _get_db()
    try:
        record = _db_get(conn, error_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Error {error_id} not found")
        _db_unignore(conn, error_id)
        return {"ok": True, "unignored": True, "error_id": error_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/errors/{error_id}/fix")
def api_apply_fix(error_id: int, dry_run: bool = False):
    conn = _get_db()
    try:
        record = _db_get(conn, error_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Error {error_id} not found")

        command = record.get("fix_command", "")
        if not command:
            return {"ok": False, "error": "No fix command stored for this error"}

        if dry_run:
            return {"ok": True, "dry_run": True, "would_execute": command}

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(get_hermes_home()),
            )
            fix_result = {
                "exit_code": result.returncode,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000],
            }
            if result.returncode == 0:
                updated = _db_apply(conn, error_id)
                return {
                    "ok": True,
                    "fix_applied": True,
                    "result": fix_result,
                    "error": updated,
                }
            else:
                return {
                    "ok": False,
                    "fix_failed": True,
                    "result": fix_result,
                    "error": "Fix command exited with non-zero status",
                }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Fix command timed out (60s)"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
@router.post("/errors/{error_id}/analyze")
def api_analyze_with_agent(error_id: int):
    """Run agent analysis via a one-shot cron job. Returns job_id for polling."""
    conn = _get_db()
    try:
        record = conn.execute(
            "SELECT * FROM error_entries WHERE id = ?", (error_id,)
        ).fetchone()
        if not record:
            raise HTTPException(status_code=404, detail=f"Error {error_id} not found")
        r = dict(record)

        prompt = (
            f"You are a Log Doctor analysis agent. Analyze this error and call suggest_error_fix to store your diagnosis.\n\n"
            f"Error ID: {error_id}\n"
            f"Error Type: {r['error_type']}\n"
            f"Message: {r['message']}\n"
            f"Occurrences: {r['count']} times (first: {r['first_seen']}, last: {r['last_seen']})\n"
            f"Source: {r['source']}\n"
            f"Context: {r.get('context', 'N/A')[:500]}\n\n"
            f"Steps:\n"
            f"1. Call analyze_log_error(error_id={error_id}) to get full details\n"
            f"2. Diagnose the root cause\n"
            f"3. Call suggest_error_fix(error_id={error_id}, description=\"...\", command=\"...\")\n"
            f"   - description: human-readable root cause and fix explanation\n"
            f"   - command: shell command to apply the fix (or empty string if manual)\n\n"
            f"Be concise. Only output your diagnosis and then call suggest_error_fix."
        )

        name = f"log-doctor-analysis-{error_id}"

        # Create a one-shot cron job that runs immediately
        import sys
        sys.path.insert(0, str(_HERMES_AGENT_DIR))
        from cron.jobs import create_job

        job = create_job(
            prompt=prompt,
            schedule=_now_iso(),  # run once immediately
            name=name,
            repeat=1,
            deliver="local",
            skills=["log-doctor"],
            enabled_toolsets=["terminal", "file"],
        )

        # Store job_id in error record so frontend can poll
        conn.execute(
            "UPDATE error_entries SET fix_description = ?, fix_command = ? WHERE id = ?",
            (f"__analysis_job__:{job['id']}", "", error_id),
        )
        conn.commit()

        return {
            "ok": True,
            "analysis_queued": True,
            "error_id": error_id,
            "job_id": job["id"],
            "job_name": name,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/errors/{error_id}/analysis-status")
def api_analysis_status(error_id: int):
    """Check if the analysis cron job has completed."""
    conn = _get_db()
    try:
        record = conn.execute(
            "SELECT * FROM error_entries WHERE id = ?", (error_id,)
        ).fetchone()
        if not record:
            raise HTTPException(status_code=404, detail=f"Error {error_id} not found")
        r = dict(record)

        # Check if fix_description contains our job marker
        fd = r.get("fix_description") or ""
        if fd.startswith("__analysis_job__:"):
            job_id = fd.split(":", 1)[1]
            import sys
            sys.path.insert(0, str(_HERMES_AGENT_DIR))
            from cron.jobs import load_jobs

            jobs = load_jobs()
            job = next((j for j in jobs.get("jobs", []) if j["id"] == job_id), None)

            if not job:
                return {"ok": True, "status": "unknown", "error_id": error_id}

            status = job.get("last_status", "pending")
            if status == "ok":
                # Job completed — check if fix was actually stored
                if r.get("fix_description") and not r["fix_description"].startswith("__analysis_job__:"):
                    return {
                        "ok": True,
                        "status": "completed",
                        "error_id": error_id,
                        "fix_description": r["fix_description"],
                        "fix_command": r["fix_command"],
                    }
                else:
                    return {
                        "ok": True,
                        "status": "completed_no_fix",
                        "error_id": error_id,
                        "message": "Analysis completed but no fix was suggested.",
                    }
            elif status in ("error", "failed"):
                return {
                    "ok": True,
                    "status": "failed",
                    "error_id": error_id,
                    "error": job.get("last_error", "Unknown error"),
                }
            else:
                return {"ok": True, "status": "running", "error_id": error_id}

        # No analysis job marker — check if fix already exists
        if r.get("fix_description"):
            return {
                "ok": True,
                "status": "completed",
                "error_id": error_id,
                "fix_description": r["fix_description"],
                "fix_command": r["fix_command"],
            }

        return {"ok": True, "status": "not_started", "error_id": error_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# UI page — served as HTML with embedded vanilla JS
# ---------------------------------------------------------------------------

UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Log Doctor</title>
<style>
  :root {
    --bg: #1a1b26; --surface: #24283b; --border: #414868;
    --text: #c0caf5; --muted: #565f89; --accent: #7aa2f7;
    --red: #f7768e; --yellow: #e0af68; --green: #9ece6a;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: var(--bg); color: var(--text); padding: 24px; line-height: 1.5; }
  h1 { font-size: 20px; margin-bottom: 16px; color: var(--accent); }
  .tab-bar { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
  .tab-btn { padding: 8px 16px; border: none; background: none; color: var(--muted);
             cursor: pointer; font-size: 14px; border-bottom: 2px solid transparent; }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-btn .count { margin-left: 6px; font-size: 12px; padding: 1px 6px;
                    border-radius: 10px; background: var(--surface); }
  .stats { display: flex; gap: 16px; margin-bottom: 16px; font-size: 13px; color: var(--muted); }
  .error-list { list-style: none; }
  .error-item { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px;
                background: var(--surface); overflow: hidden; }
  .error-header { display: flex; align-items: center; padding: 12px 16px; cursor: pointer;
                  user-select: none; gap: 12px; }
  .error-header:hover { background: rgba(122,162,247,0.05); }
  .error-type { font-weight: 700; font-size: 12px; padding: 2px 8px; border-radius: 4px;
                text-transform: uppercase; }
  .error-type.WARNING { background: rgba(224,175,104,0.2); color: var(--yellow); }
  .error-type.ERROR { background: rgba(247,118,142,0.2); color: var(--red); }
  .error-type.CRITICAL { background: rgba(247,118,142,0.4); color: var(--red); }
  .error-msg { flex: 1; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .error-count { font-size: 12px; color: var(--muted); white-space: nowrap; }
  .error-arrow { font-size: 12px; color: var(--muted); transition: transform 0.2s; }
  .error-item.expanded .error-arrow { transform: rotate(90deg); }
  .error-detail { display: none; padding: 0 16px 16px; font-size: 13px; }
  .error-item.expanded .error-detail { display: block; }
  .detail-row { margin-bottom: 8px; }
  .detail-label { color: var(--muted); font-size: 11px; text-transform: uppercase; }
  .detail-value { color: var(--text); word-break: break-all; }
  .pre { background: var(--bg); padding: 8px 12px; border-radius: 6px;
         font-family: 'JetBrains Mono', monospace; font-size: 12px;
         max-height: 200px; overflow-y: auto; white-space: pre-wrap; }
  .actions { display: flex; gap: 8px; margin-top: 12px; }
  .btn { padding: 6px 14px; border: 1px solid var(--border); border-radius: 6px;
         background: var(--surface); color: var(--text); cursor: pointer; font-size: 13px; }
  .btn:hover { background: var(--border); }
  .btn.fix { border-color: var(--green); color: var(--green); }
  .btn.fix:hover { background: rgba(158,206,106,0.15); }
  .btn.ignore { border-color: var(--yellow); color: var(--yellow); }
  .btn.ignore:hover { background: rgba(224,175,104,0.15); }
  .btn.analyze { border-color: var(--accent); color: var(--accent); }
  .btn.analyze:hover { background: rgba(122,162,247,0.15); }
  .empty { text-align: center; padding: 40px; color: var(--muted); font-size: 14px; }
  .flash { position: fixed; top: 16px; right: 16px; padding: 12px 20px; border-radius: 8px;
           font-size: 13px; z-index: 999; animation: fadeIn 0.3s; }
  .flash.success { background: rgba(158,206,106,0.2); color: var(--green); border: 1px solid var(--green); }
  .flash.error { background: rgba(247,118,142,0.2); color: var(--red); border: 1px solid var(--red); }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(-8px); }
                       to { opacity: 1; transform: translateY(0); } }
  .loading { text-align: center; padding: 20px; color: var(--muted); }
  .fix-result { margin-top: 8px; padding: 8px 12px; border-radius: 6px; font-size: 12px; }
  .fix-result.success { background: rgba(158,206,106,0.1); border: 1px solid var(--green); }
  .fix-result.fail { background: rgba(247,118,142,0.1); border: 1px solid var(--red); }
</style>
</head>
<body>
<h1>🩺 Log Doctor</h1>
<div class="tab-bar">
  <button class="tab-btn active" data-tab="active">Active <span class="count" id="count-active">0</span></button>
  <button class="tab-btn" data-tab="ignored">Ignored <span class="count" id="count-ignored">0</span></button>
  <button class="tab-btn" data-tab="fixed">Fixed <span class="count" id="count-fixed">0</span></button>
</div>
<div class="stats" id="stats"></div>
<div id="content"><div class="loading">Loading errors...</div></div>

<script>
const API = '/api/plugins/log-doctor';
const TOKEN = (window.parent !== window ? window.parent.__HERMES_SESSION_TOKEN__ : window.__HERMES_SESSION_TOKEN__)
            || new URLSearchParams(window.location.search).get('token') || '';

function authHeaders() {
  return TOKEN ? { 'Authorization': 'Bearer ' + TOKEN } : {};
}

async function api(path, opts = {}) {
  const url = API + path;
  const res = await fetch(url, { ...opts, headers: { ...authHeaders(), ...(opts.headers || {}) } });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

let currentTab = 'active';

async function load(tab) {
  currentTab = tab || currentTab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === currentTab));
  const data = await api('/errors?status=' + (currentTab === 'ignored' ? 'ignored' : currentTab === 'fixed' ? 'fixed' : 'active'));
  render(data);
  document.getElementById('count-active').textContent = data.stats.active || 0;
  document.getElementById('count-ignored').textContent = data.stats.ignored || 0;
  document.getElementById('count-fixed').textContent = data.stats.fixed || 0;
  const last = data.stats.last_scan;
  document.getElementById('stats').innerHTML = last
    ? `Last scan: ${last.scanned_at} · ${last.total_errors} errors (${last.new_errors} new, ${last.ignored_skipped} skipped)`
    : 'No scans yet.';
}

function render(data) {
  const el = document.getElementById('content');
  if (!data.errors || data.errors.length === 0) {
    el.innerHTML = `<div class="empty">No ${currentTab} errors found. 🎉</div>`;
    return;
  }
  el.innerHTML = '<ul class="error-list">' + data.errors.map(e => `
    <li class="error-item" id="err-${e.id}">
      <div class="error-header" onclick="toggleError(${e.id})">
        <span class="error-arrow">▶</span>
        <span class="error-type ${e.error_type}">${e.error_type}</span>
        <span class="error-msg">${esc(e.message)}</span>
        <span class="error-count">×${e.count}</span>
      </div>
      <div class="error-detail">
        <div class="detail-row"><div class="detail-label">First Seen</div><div class="detail-value">${e.first_seen}</div></div>
        <div class="detail-row"><div class="detail-label">Last Seen</div><div class="detail-value">${e.last_seen}</div></div>
        ${e.file_path ? `<div class="detail-row"><div class="detail-label">File</div><div class="detail-value">${esc(e.file_path)}${e.line_number ? ':' + e.line_number : ''}</div></div>` : ''}
        ${e.context ? `<div class="detail-row"><div class="detail-label">Raw Log</div><div class="pre">${esc(e.context)}</div></div>` : ''}
        ${e.fix_description ? `<div class="detail-row"><div class="detail-label">Fix Suggestion</div><div class="detail-value">${esc(e.fix_description)}</div></div>` : ''}
        ${e.fix_command ? `<div class="detail-row"><div class="detail-label">Fix Command</div><div class="pre">${esc(e.fix_command)}</div></div>` : ''}
        <div class="actions" id="actions-${e.id}">
          ${e.status === 'active' ? `
            <button class="btn analyze" onclick="requestAnalysis(${e.id})">Ask Agent</button>
            <button class="btn ignore" onclick="ignoreError(${e.id})">Ignore</button>
          ` : e.status === 'ignored' ? `
            <button class="btn" onclick="unignoreError(${e.id})">Un-ignore</button>
          ` : ''}
          ${e.fix_command && e.status === 'active' ? `<button class="btn fix" onclick="applyFix(${e.id})">Apply Fix</button>` : ''}
        </div>
        <div id="fix-result-${e.id}"></div>
      </div>
    </li>
  `).join('') + '</ul>';
}

function esc(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function toggleError(id) { document.getElementById('err-' + id).classList.toggle('expanded'); }

function flash(msg, type) {
  const f = document.createElement('div');
  f.className = 'flash ' + type;
  f.textContent = msg;
  document.body.appendChild(f);
  setTimeout(() => f.remove(), 3000);
}

async function ignoreError(id) {
  try { await api('/errors/' + id + '/ignore', { method: 'POST' }); flash('Ignored', 'success'); load(); }
  catch(e) { flash(e.message, 'error'); }
}

async function unignoreError(id) {
  try { await api('/errors/' + id + '/unignore', { method: 'POST' }); flash('Un-ignored', 'success'); load(); }
  catch(e) { flash(e.message, 'error'); }
}

async function applyFix(id) {
  const btn = document.querySelector(`#actions-${id} .fix`);
  if (btn) btn.disabled = true;
  try {
    const data = await api('/errors/' + id + '/fix', { method: 'POST' });
    const rdiv = document.getElementById('fix-result-' + id);
    if (data.ok) {
      rdiv.innerHTML = `<div class="fix-result success">Fix applied! Exit: ${data.result.exit_code}</div>`;
      setTimeout(() => load(), 1500);
    } else {
      rdiv.innerHTML = `<div class="fix-result fail">${data.error || 'Fix failed'}</div>`;
    }
  } catch(e) { flash(e.message, 'error'); }
}

async function requestAnalysis(id) {
  try {
    const data = await api('/errors/' + id + '/analyze', { method: 'POST' });
    if (data.analysis_prompt) {
      navigator.clipboard.writeText(data.analysis_prompt).then(() => {
        flash('Analysis prompt copied! Paste to Hermes agent.', 'success');
      });
    }
  } catch(e) { flash(e.message, 'error'); }
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => load(btn.dataset.tab));
});
load('active');
</script>
</body>
</html>"""


@router.get("/ui", response_class=HTMLResponse)
def serve_ui():
    return HTMLResponse(content=UI_HTML)
