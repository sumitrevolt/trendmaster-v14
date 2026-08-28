r"""
SUPERSEDED 2026-04-25 — replaced by tools/unified_dashboard.py.

This file is kept for git history but is NOT imported anywhere active.
Pytest's collect step raised DeprecationWarning on the `\m` in the old
docstring; switching to a raw string silences it without changing the
file's role.

Original purpose (preserved for future reference):
TrendMaster v14 - Mission Control dashboard.

Complementary to tools/dashboard.py (which focuses on PnL + signals).
This view shows full SYSTEM STATE: brain liveness, junction integrity,
per-team configs, schtasks, agent votes, live tick stream.

Runs on http://127.0.0.1:8001/  (separate port from /dashboard at :8000)

Endpoints
---------
  /                  — HTML mission-control single page
  /api/mission       — full JSON dump of system state
  /api/brain-tail    — last N brain log lines
  /api/agents        — per-symbol agent vote breakdown
  /actions/halt-all  — POST: pauses brain via state file
  /actions/resume    — POST: resumes brain
  /healthz           — liveness probe

Start:  python tools\mission_control.py
"""
from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

LOGS = REPO / "logs"
CANONICAL = Path(r"C:\TrendMaster_aita_canonical")

app = FastAPI(title="TrendMaster v14 Mission Control")


# ---------------------------------------------------------------------
# state collectors
# ---------------------------------------------------------------------

def _read_brain_state() -> dict:
    p = LOGS / "brain_state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _brain_pids() -> list[int]:
    p = LOGS / "brain.pid"
    if not p.exists():
        return []
    pids = []
    try:
        for line in p.read_text(encoding="ascii", errors="ignore").splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
    except Exception:
        pass
    return pids


def _is_pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        return False


def _brain_liveness() -> dict:
    pids = _brain_pids()
    alive = sum(1 for p in pids if _is_pid_alive(p))
    log = LOGS / "trend_master_brain.log"
    state = LOGS / "brain_state.json"
    err = LOGS / "trend_master_brain.err"
    log_age = (datetime.now() - datetime.fromtimestamp(log.stat().st_mtime)).total_seconds() if log.exists() else None
    state_age = (datetime.now() - datetime.fromtimestamp(state.stat().st_mtime)).total_seconds() if state.exists() else None
    err_size = err.stat().st_size if err.exists() else None
    if alive == 0:
        verdict = "DEAD"
    elif log_age is None or log_age > 180:
        verdict = "STALE"
    elif log_age > 90:
        verdict = "WARN"
    else:
        verdict = "ALIVE"
    return {
        "verdict": verdict,
        "pids": pids,
        "alive_count": alive,
        "log_age_sec": int(log_age) if log_age else None,
        "state_age_sec": int(state_age) if state_age else None,
        "err_size_bytes": err_size,
    }


def _junction_check() -> dict:
    out = {"ok": True, "checks": {}}
    junction = REPO / "ai_trading_agents"
    out["checks"]["exists"] = junction.exists()
    if not junction.exists():
        out["ok"] = False
        return out
    try:
        r = subprocess.run(["fsutil", "reparsepoint", "query", str(junction)],
                           capture_output=True, text=True, timeout=5)
        out["checks"]["is_junction"] = r.returncode == 0 and "Mount Point" in r.stdout
        out["checks"]["target_correct"] = "TrendMaster_aita_canonical" in r.stdout
    except Exception:
        out["checks"]["is_junction"] = False
        out["checks"]["target_correct"] = False
    out["checks"]["canonical_exists"] = CANONICAL.exists()
    if CANONICAL.exists():
        py_count = len(list(CANONICAL.glob("*.py")))
        out["checks"]["module_count"] = py_count
        out["checks"]["module_count_ok"] = py_count >= 38
    else:
        out["checks"]["module_count"] = 0
        out["checks"]["module_count_ok"] = False
    out["ok"] = all(v for k, v in out["checks"].items() if isinstance(v, bool))
    return out


def _mt5_status() -> dict:
    try:
        import MetaTrader5 as mt5
        ok = mt5.initialize()
        if not ok:
            return {"connected": False, "error": "init failed"}
        ti = mt5.terminal_info()
        ai = mt5.account_info()
        out = {
            "connected": bool(ti.connected) if ti else False,
            "build": ti.build if ti else None,
            "account": ai.login if ai else None,
            "balance": ai.balance if ai else None,
            "equity": ai.equity if ai else None,
            "profit": ai.profit if ai else None,
        }
        mt5.shutdown()
        return out
    except Exception as e:
        return {"connected": False, "error": str(e)[:80]}


def _team_configs() -> dict:
    try:
        from ai_trading_agents.team_params import TEAM_PARAMS
        return TEAM_PARAMS
    except Exception:
        return {}


def _schtasks() -> list[dict]:
    try:
        r = subprocess.run(
            ["schtasks", "/query", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return []
        out = []
        for line in r.stdout.splitlines():
            if "TrendMaster" not in line:
                continue
            parts = [p.strip('"') for p in line.split(",")]
            if len(parts) >= 3:
                out.append({"name": parts[0], "next_run": parts[1], "status": parts[2]})
        return out
    except Exception:
        return []


def _last_log_lines(n: int = 30) -> list[str]:
    p = LOGS / "trend_master_brain.log"
    if not p.exists():
        return []
    try:
        with p.open(encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except Exception:
        return []


def _per_symbol_signals() -> dict:
    state = _read_brain_state()
    return state.get("last_signal_per_symbol", {}) or {}


def _open_positions() -> list[dict]:
    state = _read_brain_state()
    return state.get("open_positions", []) or []


# ---------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------

@app.get("/api/mission")
def api_mission():
    return JSONResponse({
        "ts": datetime.now(timezone.utc).isoformat(),
        "brain": _brain_liveness(),
        "junction": _junction_check(),
        "mt5": _mt5_status(),
        "team_params": _team_configs(),
        "schtasks": _schtasks(),
        "signals_per_symbol": _per_symbol_signals(),
        "open_positions": _open_positions(),
        "trading_paused": _read_brain_state().get("trading_paused", False),
    })


@app.get("/api/brain-tail")
def api_brain_tail(n: int = 30):
    return JSONResponse({"lines": _last_log_lines(n)})


@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})


@app.post("/actions/halt-all")
def action_halt_all():
    state = _read_brain_state()
    state["trading_paused"] = True
    state["paused_via"] = "mission_control"
    state["paused_at"] = datetime.now(timezone.utc).isoformat()
    (LOGS / "brain_state.json").write_text(json.dumps(state, indent=2))
    return JSONResponse({"ok": True, "paused": True})


@app.post("/actions/resume")
def action_resume():
    state = _read_brain_state()
    state["trading_paused"] = False
    state["resumed_at"] = datetime.now(timezone.utc).isoformat()
    (LOGS / "brain_state.json").write_text(json.dumps(state, indent=2))
    return JSONResponse({"ok": True, "paused": False})


@app.post("/actions/test-telegram")
def action_test_telegram():
    try:
        from ai_trading_agents.telegram_notifier import get_notifier
        n = get_notifier()
        ok = n.send(f"[Mission Control test] {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        return JSONResponse({"ok": bool(ok)})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:100]})


# ---------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>TrendMaster v14 — Mission Control</title>
<style>
* { box-sizing: border-box; }
body { font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;
       margin: 0; padding: 16px; background: #0e1116; color: #d8dee4; font-size: 13px; }
h1 { margin: 0 0 8px 0; font-size: 18px; color: #4fc3f7; }
h2 { font-size: 13px; color: #888; margin: 12px 0 4px 0; text-transform: uppercase; letter-spacing: 1px; }
.grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.card { background: #1a1f2b; border: 1px solid #2a2f3b; border-radius: 6px; padding: 10px 12px; }
.card .label { font-size: 11px; color: #888; text-transform: uppercase; }
.card .value { font-size: 20px; font-weight: 600; margin: 4px 0; }
.alive { color: #4caf50; }
.warn  { color: #ffc107; }
.dead  { color: #f44336; }
.ok    { color: #4caf50; }
.bad   { color: #f44336; }
table { width: 100%; border-collapse: collapse; margin: 8px 0; background: #1a1f2b; }
th, td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #2a2f3b; font-size: 12px; }
th { background: #232838; color: #888; font-weight: 600; text-transform: uppercase; font-size: 11px; }
.tag { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; }
.tag-green { background: #1b5e20; color: #c8e6c9; }
.tag-red   { background: #b71c1c; color: #ffcdd2; }
.tag-amber { background: #e65100; color: #ffe0b2; }
button { background: #2a2f3b; color: #d8dee4; border: 1px solid #3a3f4b; padding: 6px 12px;
         border-radius: 4px; cursor: pointer; margin: 0 4px 0 0; font-size: 12px; }
button:hover { background: #3a3f4b; }
button.danger { background: #5a1a1a; border-color: #7a2a2a; }
button.danger:hover { background: #7a2a2a; }
.log { background: #0a0d12; border: 1px solid #2a2f3b; border-radius: 4px; padding: 8px;
       max-height: 240px; overflow-y: auto; font-family: ui-monospace,Menlo,Consolas,monospace;
       font-size: 11px; line-height: 1.4; color: #b0b8c2; }
.log .err { color: #ef5350; }
.log .info { color: #b0b8c2; }
.muted { color: #666; }
.row { display: flex; justify-content: space-between; align-items: center; }
.refresh { font-size: 11px; color: #555; }
</style>
</head>
<body>

<div class="row">
  <h1>TrendMaster v14 — Mission Control</h1>
  <div class="refresh">auto-refresh: <span id="rcount">0</span>s ago · <button onclick="reload()">refresh</button></div>
</div>

<div class="grid">
  <div class="card"><div class="label">Brain</div>
    <div class="value" id="brain-verdict">...</div>
    <div id="brain-detail" class="muted">...</div></div>
  <div class="card"><div class="label">Junction</div>
    <div class="value" id="junction-verdict">...</div>
    <div id="junction-detail" class="muted">...</div></div>
  <div class="card"><div class="label">MT5</div>
    <div class="value" id="mt5-verdict">...</div>
    <div id="mt5-detail" class="muted">...</div></div>
  <div class="card"><div class="label">Open Positions</div>
    <div class="value" id="positions-count">0</div>
    <div id="positions-detail" class="muted">...</div></div>
</div>

<h2>Per-team v14.5 Configs</h2>
<table id="teams"><thead><tr><th>Team</th><th>SL</th><th>TP</th><th>ADX min</th><th>ST mult</th><th>BB floor</th><th>Sharpe (bt)</th></tr></thead><tbody></tbody></table>

<h2>Latest signals per symbol (live)</h2>
<table id="signals"><thead><tr><th>Symbol</th><th>Direction</th><th>Confidence</th><th>Last seen</th></tr></thead><tbody></tbody></table>

<h2>Scheduled tasks (10 should be Ready)</h2>
<table id="schtasks"><thead><tr><th>Task</th><th>Next run</th><th>Status</th></tr></thead><tbody></tbody></table>

<h2>Brain log (live tail, last 30 lines)</h2>
<div class="log" id="brain-log">loading...</div>

<h2>Actions</h2>
<div>
  <button onclick="action('halt-all')">Halt brain</button>
  <button onclick="action('resume')">Resume brain</button>
  <button onclick="action('test-telegram')">Send test Telegram</button>
  <button class="danger" onclick="confirmRestart()">Restart brain (manual)</button>
</div>
<div id="action-result" class="muted" style="margin-top:8px"></div>

<script>
let lastRefresh = Date.now();

function reload() {
  Promise.all([
    fetch('/api/mission').then(r => r.json()),
    fetch('/api/brain-tail?n=30').then(r => r.json()),
  ]).then(([m, t]) => {
    renderMission(m);
    renderTail(t);
    lastRefresh = Date.now();
    document.getElementById('rcount').textContent = '0';
  }).catch(e => console.error(e));
}

function renderMission(d) {
  // Brain
  const v = d.brain.verdict;
  const cls = v === 'ALIVE' ? 'alive' : (v === 'WARN' ? 'warn' : 'dead');
  document.getElementById('brain-verdict').className = 'value ' + cls;
  document.getElementById('brain-verdict').textContent = v;
  document.getElementById('brain-detail').textContent =
    `PIDs: ${d.brain.pids.join(',')} · log ${d.brain.log_age_sec}s ago · err ${d.brain.err_size_bytes}B`;

  // Junction
  const ok = d.junction.ok;
  document.getElementById('junction-verdict').className = 'value ' + (ok ? 'ok' : 'bad');
  document.getElementById('junction-verdict').textContent = ok ? 'HEALTHY' : 'BAD';
  const c = d.junction.checks;
  document.getElementById('junction-detail').textContent =
    `${c.module_count}/39 modules · target ${c.target_correct ? 'OK' : 'BAD'}`;

  // MT5
  const conn = d.mt5.connected;
  document.getElementById('mt5-verdict').className = 'value ' + (conn ? 'ok' : 'bad');
  document.getElementById('mt5-verdict').textContent = conn ? 'CONNECTED' : 'DISCONNECTED';
  document.getElementById('mt5-detail').textContent = d.mt5.account
    ? `acct ${d.mt5.account} · bal ${d.mt5.balance} · equity ${d.mt5.equity} · build ${d.mt5.build}`
    : (d.mt5.error || '');

  // Positions
  document.getElementById('positions-count').textContent = d.open_positions.length;
  document.getElementById('positions-detail').textContent =
    d.trading_paused ? '*** TRADING PAUSED ***' : 'trading active';
  if (d.trading_paused) {
    document.getElementById('positions-detail').className = 'warn';
  } else {
    document.getElementById('positions-detail').className = 'muted';
  }

  // Teams
  const tbody = document.querySelector('#teams tbody');
  tbody.innerHTML = '';
  for (const [t, cfg] of Object.entries(d.team_params)) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><b>${t}</b></td><td>${cfg.sl_atr_mult}</td><td>${cfg.tp_atr_mult}</td>` +
      `<td>${cfg.adx_min}</td><td>${cfg.st_mult || '-'}</td><td>${cfg.bb_width_floor_pct || '-'}</td>` +
      `<td>${(cfg.sharpe || 0).toFixed(3)}</td>`;
    tbody.appendChild(tr);
  }

  // Signals
  const stbody = document.querySelector('#signals tbody');
  stbody.innerHTML = '';
  const sigs = d.signals_per_symbol;
  for (const sym of Object.keys(sigs).sort()) {
    const s = sigs[sym] || {};
    const dir = s.direction || 'NONE';
    const dirClass = dir === 'BUY' ? 'tag-green' : dir === 'SELL' ? 'tag-red' : 'tag-amber';
    const conf = s.conf || s.confidence || 0;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${sym}</td><td><span class="tag ${dirClass}">${dir}</span></td>` +
      `<td>${typeof conf === 'number' ? conf.toFixed(3) : '-'}</td><td class="muted">${s.ts || '-'}</td>`;
    stbody.appendChild(tr);
  }

  // Schtasks
  const ttbody = document.querySelector('#schtasks tbody');
  ttbody.innerHTML = '';
  for (const t of d.schtasks) {
    const cls = t.status === 'Ready' ? 'tag-green' : 'tag-amber';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${t.name.replace(/^\\\\/, '').replace('TrendMaster ', '')}</td>` +
      `<td>${t.next_run}</td><td><span class="tag ${cls}">${t.status}</span></td>`;
    ttbody.appendChild(tr);
  }
}

function renderTail(d) {
  const el = document.getElementById('brain-log');
  el.innerHTML = d.lines.map(l => {
    const cls = /ERROR|Traceback|FATAL|CRITICAL/.test(l) ? 'err' : 'info';
    return `<div class="${cls}">${escapeHtml(l)}</div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

function action(name) {
  fetch('/actions/' + name, { method: 'POST' }).then(r => r.json()).then(j => {
    document.getElementById('action-result').textContent = `Action ${name}: ${JSON.stringify(j)}`;
    setTimeout(reload, 500);
  });
}

function confirmRestart() {
  alert('Open a terminal and run: start_brain_clean.cmd  (this dashboard does NOT restart brain to avoid taskkill issues)');
}

setInterval(() => {
  document.getElementById('rcount').textContent = Math.floor((Date.now() - lastRefresh) / 1000);
}, 1000);

setInterval(reload, 5000);
reload();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(HTML)


def main():
    port = int(os.environ.get("MISSION_PORT", "8001"))
    print(f"Mission Control listening on http://127.0.0.1:{port}/")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
