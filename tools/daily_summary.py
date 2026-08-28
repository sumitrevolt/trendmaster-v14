"""
daily_summary.py - end-of-day digest for TrendMaster.

Runs at 23:55 IST via Scheduled Task "TrendMaster Daily Summary".
Writes reports/daily/YYYY-MM-DD.md with:
  - brain uptime + restart count today
  - signals generated per symbol
  - trades placed (recent_results entries dated today)
  - net P&L today vs daily limit
  - drift alerts of the day
  - watchpet severity timeline
  - schtasks audit summary
  - "next morning" context for the operator and the trader agent

Both Claude Code and OpenClaw read these files for next-day context.
The trader agent should invoke `tools/openclaw_brief.py` followed by
`type reports/daily/<yesterday>.md` at session start for full context.

Pure Python; reads only logs/ + config/. No network, no MT5 calls.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS = PROJECT_ROOT / "logs"
REPORTS_DIR = PROJECT_ROOT / "reports" / "daily"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _ist_now() -> datetime:
    """Return current time in India Standard Time (UTC+5:30)."""
    return datetime.now(tz=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))


def _safe_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _ts_to_ist(ts: float | int | str | None) -> str:
    if ts is None or ts == 0:
        return "-"
    try:
        if isinstance(ts, str):
            return ts
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone(
            timezone(timedelta(hours=5, minutes=30))
        ).strftime("%H:%M:%S")
    except Exception:
        return str(ts)


def collect_brain_state() -> dict:
    state = _safe_json(LOGS / "brain_state.json") or {}
    pid_file = LOGS / "brain.pid"
    pid_str = pid_file.read_text(errors="ignore").strip() if pid_file.exists() else None
    return {
        "pid": pid_str,
        "restart_count": state.get("restart_count"),
        "last_started": state.get("last_started_at"),
        "trading_paused": state.get("trading_paused"),
        "trading_paused_at": state.get("trading_paused_at"),
        "trading_resumed_at": state.get("trading_resumed_at"),
        "sod_equity": state.get("start_of_day_equity"),
        "session_high": state.get("session_high_equity"),
        "session_low": state.get("session_low_equity"),
        "peak_eq": state.get("daily_drawdown_peak_eq"),
        "daily_pnl_close": state.get("daily_pnl_close"),
        "drawdown_lockout_until": state.get("drawdown_lockout_until"),
    }


def collect_signals_today(today_utc: datetime) -> dict:
    """Count NONE vs BUY vs SELL per symbol from last_signal_per_symbol.
    NOTE: this is a snapshot, not the day's full signal stream. For full
    stream summary, the brain should write a separate signals.jsonl."""
    state = _safe_json(LOGS / "brain_state.json") or {}
    lsps = state.get("last_signal_per_symbol") or {}
    if not isinstance(lsps, dict):
        return {"per_symbol": {}, "summary": {}}

    by_symbol: dict[str, dict] = {}
    direction_count: Counter = Counter()
    for sym, payload in lsps.items():
        if not isinstance(payload, dict):
            continue
        direction = payload.get("direction") or payload.get("dir") or "?"
        conf = payload.get("conf") or payload.get("confidence")
        ts = payload.get("ts") or payload.get("timestamp")
        by_symbol[sym] = {
            "direction": direction,
            "conf": conf,
            "ts": _ts_to_ist(ts),
        }
        direction_count[direction] += 1
    return {"per_symbol": by_symbol, "summary": dict(direction_count)}


def collect_trades_today(today_ist: datetime) -> list[dict]:
    state = _safe_json(LOGS / "brain_state.json") or {}
    rr = state.get("recent_results") or []
    if not isinstance(rr, list):
        return []
    today_start = today_ist.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_end = today_start + 86400
    out = []
    for entry in rr:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("ts")
        try:
            ts_f = float(ts)
        except Exception:
            continue
        if today_start <= ts_f < today_end:
            out.append(entry)
    return out


def collect_drift_alerts_today(today_ist: datetime) -> list[dict]:
    drift = LOGS / "drift_alerts.jsonl"
    if not drift.exists():
        return []
    today_start = today_ist.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    out = []
    try:
        with drift.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    ts = obj.get("ts") or obj.get("timestamp") or 0
                    if isinstance(ts, str):
                        try:
                            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                        except Exception:
                            continue
                    if float(ts) >= today_start:
                        out.append(obj)
                except Exception:
                    continue
    except Exception:
        pass
    return out


def collect_watchpet_timeline(today_ist: datetime) -> list[dict]:
    """All watchpet entries from today, summarized to severity transitions."""
    log = LOGS / "watchpets.jsonl"
    if not log.exists():
        return []
    today_start = today_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    transitions: list[dict] = []
    last_severity = None
    try:
        with log.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    ts_str = obj.get("ts", "")
                    ts_dt = datetime.fromisoformat(ts_str)
                    if ts_dt < today_start:
                        continue
                    sev = obj.get("overall", "OK")
                    if sev != last_severity:
                        # build per-failed-check brief
                        failed = [
                            f"{c['name']}={c['severity']}"
                            for c in obj.get("checks", [])
                            if c.get("severity") not in ("OK", "INFO")
                        ]
                        transitions.append({
                            "ts": ts_dt.strftime("%H:%M"),
                            "overall": sev,
                            "failed": ", ".join(failed) if failed else "-",
                        })
                        last_severity = sev
                except Exception:
                    continue
    except Exception:
        pass
    return transitions


def collect_schtasks_summary() -> dict:
    s = _safe_json(LOGS / "schtasks_audit.json")
    if not s:
        return {"available": False}
    return {
        "available": True,
        "ts": s.get("ts"),
        "task_count": s.get("task_count"),
        "issue_count": s.get("issue_count"),
        "issues": [
            {"name": a["name"], "issues": a["issues"]}
            for a in s.get("audits", [])
            if not a.get("ok")
        ],
    }


def write_report(today_ist: datetime) -> Path:
    date_str = today_ist.strftime("%Y-%m-%d")
    out_path = REPORTS_DIR / f"{date_str}.md"

    brain = collect_brain_state()
    signals = collect_signals_today(today_ist)
    trades = collect_trades_today(today_ist)
    drift = collect_drift_alerts_today(today_ist)
    watch = collect_watchpet_timeline(today_ist)
    schtasks = collect_schtasks_summary()

    pnl_text = "n/a"
    if isinstance(brain["sod_equity"], (int, float)) and isinstance(brain["session_low"], (int, float)) and brain["sod_equity"] > 0:
        # rough: net change vs SoD; if no live brain, this is meaningless
        if isinstance(brain["session_high"], (int, float)) and brain["session_high"] > 0:
            pnl_text = (
                f"SoD={brain['sod_equity']}, "
                f"high={brain['session_high']}, low={brain['session_low']}"
            )

    lines: list[str] = []
    lines.append(f"# Daily summary - {date_str}")
    lines.append("")
    lines.append(f"_Generated {datetime.now(tz=timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}_")
    lines.append("")

    lines.append("## Brain")
    lines.append(f"- pid: `{brain['pid'] or '-'}`")
    lines.append(f"- restart_count: `{brain['restart_count']}`")
    lines.append(f"- last_started: `{brain['last_started']}`")
    lines.append(f"- trading_paused: `{brain['trading_paused']}`")
    if brain.get("trading_paused_at"):
        lines.append(f"- paused_at: `{brain['trading_paused_at']}`")
    if brain.get("trading_resumed_at"):
        lines.append(f"- resumed_at: `{brain['trading_resumed_at']}`")
    lines.append(f"- equity: {pnl_text}")
    lines.append(f"- daily_pnl_close (last close): `{brain['daily_pnl_close']}`")
    lines.append(f"- drawdown_lockout_until: `{brain['drawdown_lockout_until']}`")
    lines.append("")

    lines.append("## Signals (snapshot at EoD)")
    if signals["summary"]:
        lines.append(f"- direction counts: `{signals['summary']}`")
        lines.append("")
        lines.append("| symbol | direction | conf | ts (IST) |")
        lines.append("|---|---|---|---|")
        for sym, p in sorted(signals["per_symbol"].items()):
            lines.append(f"| {sym} | {p['direction']} | {p['conf']} | {p['ts']} |")
    else:
        lines.append("- (no signal state in brain_state.json)")
    lines.append("")

    lines.append("## Trades today")
    if trades:
        lines.append(f"- count: {len(trades)}")
        for t in trades:
            sym = t.get("symbol", "?")
            pnl = t.get("pnl") or t.get("profit") or 0
            r = t.get("r_mult") or t.get("r")
            ts = _ts_to_ist(t.get("ts"))
            lines.append(f"- {ts} {sym} pnl={pnl} R={r}")
    else:
        lines.append("- no trades closed today")
    lines.append("")

    lines.append("## Drift alerts today")
    if drift:
        lines.append(f"- count: {len(drift)}")
        for d in drift[:10]:
            lines.append(f"- {d}")
        if len(drift) > 10:
            lines.append(f"- (+{len(drift)-10} more)")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Watchpet severity transitions today")
    if watch:
        lines.append("| time | overall | failed checks |")
        lines.append("|---|---|---|")
        for w in watch:
            lines.append(f"| {w['ts']} | {w['overall']} | {w['failed']} |")
    else:
        lines.append("- no severity changes recorded today (or watchpets not yet running)")
    lines.append("")

    lines.append("## Scheduled-task audit")
    if schtasks["available"]:
        lines.append(f"- last audit: `{schtasks['ts']}`")
        lines.append(f"- tasks tracked: {schtasks['task_count']}, issues: {schtasks['issue_count']}")
        if schtasks["issues"]:
            lines.append("")
            for it in schtasks["issues"]:
                lines.append(f"  - **{it['name']}**: {', '.join(it['issues'])}")
    else:
        lines.append("- (audit data not available; first run not yet completed)")
    lines.append("")

    lines.append("## For next session (operator + trader agent)")
    lines.append("Read this file plus `tools/openclaw_brief.py` output before resuming.")
    lines.append("If any section above shows red flags, open the corresponding postmortem")
    lines.append("draft under `docs/POSTMORTEMS/_draft_*.md` (auto-created when watch_pets")
    lines.append("flags CRITICAL).")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    today = _ist_now()
    out_path = write_report(today)
    print(f"daily_summary written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
