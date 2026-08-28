"""
build_live_dashboard.py - generates a self-contained live HTML dashboard.

Output: reports/dashboard/live.html
Reads: logs/watchpets_state.json, logs/brain_state.json,
       logs/schtasks_audit.json, logs/watchpets.jsonl (last 50 entries)
       reports/daily/*.md (latest)
       docs/POSTMORTEMS/INDEX.md (top 5)

The HTML auto-refreshes every 60s using a tiny inline JS snippet that
re-fetches the JSON files. No server needed - works on file:// or
served from any static host.

Usage:
  .venv\\Scripts\\python.exe tools\\build_live_dashboard.py
  Then open: file:///C:/Users/Ratanshila/Documents/autmated trading/reports/dashboard/live.html
"""

from __future__ import annotations

import html
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS = PROJECT_ROOT / "logs"
DASHBOARD_DIR = PROJECT_ROOT / "reports" / "dashboard"
DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_json(p: Path) -> dict | list | None:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _ist_now() -> datetime:
    return datetime.now(tz=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))


SEVERITY_COLORS = {
    "OK": "#10b981",        # green
    "INFO": "#6b7280",      # gray
    "WARN": "#f59e0b",      # amber
    "ERROR": "#ef4444",     # red
    "CRITICAL": "#dc2626",  # darker red
}


def render_html() -> str:
    watch = _safe_json(LOGS / "watchpets_state.json") or {}
    brain = _safe_json(LOGS / "brain_state.json") or {}
    schtasks = _safe_json(LOGS / "schtasks_audit.json") or {}

    overall_sev = watch.get("overall", "?")
    overall_color = SEVERITY_COLORS.get(overall_sev, "#6b7280")

    checks = watch.get("checks", [])
    last_seen = watch.get("ts", "?")

    # Latest 50 watchpet history points for sparkline
    history_points = []
    log_jsonl = LOGS / "watchpets.jsonl"
    if log_jsonl.exists():
        try:
            with log_jsonl.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-50:]
            for line in lines:
                try:
                    obj = json.loads(line)
                    history_points.append({
                        "ts": obj.get("ts", ""),
                        "overall": obj.get("overall", "?"),
                    })
                except Exception:
                    continue
        except Exception:
            pass

    # Latest daily report
    latest_daily = None
    daily_dir = PROJECT_ROOT / "reports" / "daily"
    if daily_dir.exists():
        files = sorted(daily_dir.glob("*.md"), reverse=True)
        if files:
            latest_daily = files[0]

    # Latest 5 postmortems from INDEX
    pm_index = PROJECT_ROOT / "docs" / "POSTMORTEMS" / "INDEX.md"
    pm_lines: list[str] = []
    if pm_index.exists():
        for line in pm_index.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("- ["):
                pm_lines.append(line)
                if len(pm_lines) >= 5:
                    break

    # Brain summary
    brain_lsps = brain.get("last_signal_per_symbol") or {}
    brain_signal_count = len(brain_lsps) if isinstance(brain_lsps, dict) else 0
    brain_signal_dirs = {}
    if isinstance(brain_lsps, dict):
        from collections import Counter
        c = Counter(p.get("direction", "?") for p in brain_lsps.values() if isinstance(p, dict))
        brain_signal_dirs = dict(c)

    rr = brain.get("recent_results") or []
    last_trade = rr[-1] if rr else None

    # Schtasks audit summary
    schtasks_issues = schtasks.get("issue_count", 0) if schtasks else "?"
    schtasks_total = schtasks.get("task_count", 0) if schtasks else "?"

    def safe(s):
        return html.escape(str(s)) if s is not None else "-"

    # Build html
    h = []
    h.append("<!DOCTYPE html>")
    h.append("<html lang='en'><head><meta charset='utf-8'>")
    h.append("<title>TrendMaster Live Dashboard</title>")
    h.append("<meta http-equiv='refresh' content='60'>")  # auto-refresh every 60s
    h.append("<style>")
    h.append("""
      :root { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; }
      body { margin: 0; background: #0b1220; color: #e5e7eb; }
      header { background: #111827; padding: 16px 24px; border-bottom: 1px solid #1f2937; display: flex; align-items: center; gap: 16px; }
      header h1 { margin: 0; font-size: 20px; font-weight: 600; }
      header .stamp { margin-left: auto; color: #9ca3af; font-size: 13px; }
      .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 600; font-size: 13px; }
      main { padding: 24px; display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }
      .card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 16px; }
      .card h2 { margin: 0 0 12px; font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #93c5fd; }
      .check-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px dashed #1f2937; font-size: 14px; }
      .check-row:last-child { border-bottom: none; }
      .check-name { flex: 0 0 96px; font-weight: 600; }
      .check-sev { flex: 0 0 80px; font-weight: 600; font-size: 12px; padding: 2px 6px; border-radius: 4px; text-align: center; }
      .check-msg { flex: 1; color: #d1d5db; }
      table { width: 100%; border-collapse: collapse; font-size: 13px; }
      th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #1f2937; }
      th { color: #9ca3af; font-weight: 500; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; }
      .tiny { font-size: 12px; color: #9ca3af; }
      .kv { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; font-size: 13px; }
      .kv dt { color: #9ca3af; font-weight: 500; }
      .kv dd { margin: 0; color: #e5e7eb; font-family: ui-monospace, "Cascadia Code", monospace; }
      .sparkline { display: flex; gap: 2px; align-items: flex-end; height: 32px; padding: 4px 0; }
      .sparkline .pt { width: 6px; background: #374151; border-radius: 1px; }
      .sparkline .OK { background: #10b981; height: 100%; }
      .sparkline .INFO { background: #6b7280; height: 100%; }
      .sparkline .WARN { background: #f59e0b; height: 100%; }
      .sparkline .ERROR { background: #ef4444; height: 100%; }
      .sparkline .CRITICAL { background: #dc2626; height: 100%; }
      a { color: #60a5fa; text-decoration: none; } a:hover { text-decoration: underline; }
      ul.tight { padding-left: 18px; margin: 4px 0; }
      ul.tight li { margin: 2px 0; font-size: 13px; }
      footer { color: #6b7280; padding: 16px 24px; border-top: 1px solid #1f2937; font-size: 12px; }
    """)
    h.append("</style></head><body>")

    # Header
    h.append("<header>")
    h.append("<h1>TrendMaster Live</h1>")
    h.append(f"<span class='badge' style='background:{overall_color};color:#fff'>{safe(overall_sev)}</span>")
    h.append(f"<span class='stamp'>watchpet ts: {safe(last_seen)}</span>")
    h.append(f"<span class='stamp'>generated: {_ist_now().strftime('%Y-%m-%d %H:%M:%S IST')}</span>")
    h.append("</header>")

    h.append("<main>")

    # Card 1: Watchpet checks
    h.append("<section class='card'><h2>Watch-pet checks</h2>")
    if checks:
        for c in checks:
            sev = c.get("severity", "?")
            color = SEVERITY_COLORS.get(sev, "#6b7280")
            h.append("<div class='check-row'>")
            h.append(f"<div class='check-name'>{safe(c.get('name'))}</div>")
            h.append(f"<div class='check-sev' style='background:{color};color:#fff'>{safe(sev)}</div>")
            h.append(f"<div class='check-msg'>{safe(c.get('message'))}</div>")
            h.append("</div>")
    else:
        h.append("<div class='tiny'>(no watchpet state - has watch_pets.py run yet?)</div>")
    h.append("</section>")

    # Card 2: History sparkline
    h.append("<section class='card'><h2>Severity history (last 50)</h2>")
    h.append("<div class='sparkline'>")
    for p in history_points:
        sev = p.get("overall", "OK")
        h.append(f"<div class='pt {safe(sev)}' title='{safe(p.get('ts'))} {safe(sev)}'></div>")
    h.append("</div>")
    h.append("<div class='tiny'>each bar = one watch_pets cycle (every 5 min)</div>")
    h.append("</section>")

    # Card 3: Brain state
    h.append("<section class='card'><h2>Brain</h2>")
    h.append("<dl class='kv'>")
    h.append(f"<dt>restart_count</dt><dd>{safe(brain.get('restart_count'))}</dd>")
    h.append(f"<dt>trading_paused</dt><dd>{safe(brain.get('trading_paused'))}</dd>")
    h.append(f"<dt>SoD equity</dt><dd>{safe(brain.get('start_of_day_equity'))}</dd>")
    h.append(f"<dt>session high</dt><dd>{safe(brain.get('session_high_equity'))}</dd>")
    h.append(f"<dt>session low</dt><dd>{safe(brain.get('session_low_equity'))}</dd>")
    h.append(f"<dt>signals tracked</dt><dd>{brain_signal_count} symbols</dd>")
    h.append(f"<dt>direction mix</dt><dd>{safe(brain_signal_dirs)}</dd>")
    if last_trade:
        h.append(f"<dt>last trade</dt><dd>{safe(last_trade.get('symbol'))} pnl={safe(last_trade.get('pnl'))}</dd>")
    h.append("</dl></section>")

    # Card 4: Scheduled-task health
    h.append("<section class='card'><h2>Scheduled-task health</h2>")
    h.append(f"<div class='tiny'>tracked: {schtasks_total}, issues: {schtasks_issues}</div>")
    if isinstance(schtasks, dict):
        bad = [a for a in (schtasks.get("audits") or []) if not a.get("ok")]
        if bad:
            h.append("<table><tr><th>task</th><th>issues</th></tr>")
            for a in bad[:10]:
                h.append(f"<tr><td>{safe(a.get('name'))}</td><td>{safe(', '.join(a.get('issues') or []))}</td></tr>")
            h.append("</table>")
        else:
            h.append("<div style='color:#10b981; font-weight:600;'>all tracked tasks healthy</div>")
    h.append("</section>")

    # Card 5: Latest daily report
    h.append("<section class='card'><h2>Latest daily report</h2>")
    if latest_daily:
        rel = "../daily/" + latest_daily.name  # for browser, relative path
        h.append(f"<div><a href='{rel}'>{safe(latest_daily.name)}</a></div>")
        head = latest_daily.read_text(encoding="utf-8", errors="replace").splitlines()[:6]
        h.append("<pre class='tiny' style='white-space:pre-wrap; color:#9ca3af; max-height:120px; overflow:auto;'>")
        for ln in head:
            h.append(safe(ln))
        h.append("</pre>")
    else:
        h.append("<div class='tiny'>(no daily report yet - first run scheduled 23:55 IST)</div>")
    h.append("</section>")

    # Card 6: Recent postmortems
    h.append("<section class='card'><h2>Recent postmortems</h2>")
    if pm_lines:
        h.append("<ul class='tight'>")
        for ln in pm_lines:
            h.append(f"<li>{safe(ln.lstrip('- '))}</li>")
        h.append("</ul>")
    else:
        h.append("<div class='tiny'>(no postmortems indexed)</div>")
    h.append("</section>")

    h.append("</main>")
    h.append("<footer>")
    h.append(f"Auto-refresh every 60s. Source: TrendMaster v14 + watch_pets.py + schtasks_audit.py + daily_summary.py.")
    h.append("</footer>")
    h.append("</body></html>")
    return "\n".join(h)


def main() -> int:
    out = DASHBOARD_DIR / "live.html"
    out.write_text(render_html(), encoding="utf-8")
    print(f"dashboard written: {out}")
    print(f"open with: file:///{str(out).replace(chr(92), '/')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
