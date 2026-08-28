"""
openclaw_brief.py - one-page status snapshot for OpenClaw / Opus session start.

Reads logs/brain_state.json + recent log lines + brain_signal.json.
Does NOT call MT5 (zero side-effects, fast, safe to run anytime).
Use:  .venv\\Scripts\\python.exe tools\\openclaw_brief.py

Goal: <50 lines of output, dense, factual, scannable. Designed to fit
cheaply into an Opus context window at session start.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---- locate project root robustly (this file is in tools/, NOT in the junction) ----
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS = PROJECT_ROOT / "logs"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def _safe_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _tail_lines(p: Path, n: int = 5) -> list[str]:
    try:
        with p.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = min(size, 8192 * n)
            f.seek(size - block)
            data = f.read().decode("utf-8", errors="replace")
        return [ln for ln in data.splitlines() if ln.strip()][-n:]
    except Exception:
        return []


def _fmt_ts(ts: float | str | None) -> str:
    if ts is None or ts == 0:
        return "-"
    try:
        if isinstance(ts, str):
            return ts
        f = float(ts)
        if f <= 0:
            return "-"
        dt = datetime.fromtimestamp(f, tz=timezone.utc).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return str(ts)


def main() -> int:
    print("=" * 64)
    print(f"  TrendMaster v14 - OpenClaw session brief")
    print(f"  generated: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}")
    print("=" * 64)

    # 1) brain process
    pid_file = LOGS / "brain.pid"
    pid_str = pid_file.read_text().strip() if pid_file.exists() else None
    alive = False
    if pid_str:
        try:
            import psutil  # type: ignore
            alive = psutil.pid_exists(int(pid_str))
        except Exception:
            alive = None  # unknown
    print(f"\n[brain] pid={pid_str or '-'}  alive={alive}")

    # 2) brain_state.json — equity / DD / trading_paused
    st = _safe_json(LOGS / "brain_state.json") or {}
    sod_eq = st.get("start_of_day_equity")
    peak_eq = st.get("daily_drawdown_peak_eq")
    sess_low = st.get("session_low_equity")
    paused = st.get("trading_paused")
    halt_until = st.get("drawdown_lockout_until")
    cooldown = st.get("cooldown_until_ts")
    last_started = st.get("last_started_at")
    restart_count = st.get("restart_count")

    dd_pct = None
    if (
        isinstance(peak_eq, (int, float))
        and isinstance(sess_low, (int, float))
        and peak_eq > 0
        and sess_low > 0  # 0 means uninitialized session, ignore
    ):
        dd_pct = round((peak_eq - sess_low) / peak_eq * 100, 2)

    print(f"[state] sod_eq={sod_eq}  peak_eq={peak_eq}  low_eq={sess_low}  dd%={dd_pct}")
    print(f"[state] trading_paused={paused}  dd_lockout_until={_fmt_ts(halt_until)}")
    print(f"[state] cooldown_until={_fmt_ts(cooldown)}")
    print(f"[state] restart_count={restart_count}  last_started={_fmt_ts(last_started)}")

    # 3) last signal per symbol — count + most recent 5
    lsps = st.get("last_signal_per_symbol") or {}
    if isinstance(lsps, dict) and lsps:
        items = []
        for sym, payload in lsps.items():
            if isinstance(payload, dict):
                items.append((payload.get("ts") or payload.get("timestamp") or "", sym, payload))
        items.sort(key=lambda x: str(x[0]), reverse=True)
        print(f"\n[signals] tracked={len(lsps)} symbols, top 5 by recency:")
        for ts, sym, p in items[:5]:
            direction = p.get("direction") or p.get("dir") or "?"
            conf = p.get("conf") or p.get("confidence") or "?"
            print(f"   {sym:<10} {direction:<5} conf={conf} ts={ts}")
    else:
        print("\n[signals] last_signal_per_symbol is empty")

    # 4) recent_results — last 5 trades
    rr = st.get("recent_results") or []
    if isinstance(rr, list) and rr:
        print(f"\n[recent_results] {len(rr)} entries, last 5:")
        for r in rr[-5:]:
            print(f"   {r}")
    else:
        print("\n[recent_results] empty (sparse, expected — see brain_memory.json for backtest history)")

    # 5) brain.err tail
    err_file = LOGS / "trend_master_brain.err"
    if err_file.exists() and err_file.stat().st_size > 0:
        last = _tail_lines(err_file, 3)
        print(f"\n[brain.err] last {len(last)} non-empty lines:")
        for ln in last:
            print(f"   {ln[:180]}")
    else:
        print("\n[brain.err] (no error output)")

    # 6) hint to run diagnose if anything looks off
    print("\n[next] for deeper triage run:  .venv\\Scripts\\python.exe tools\\diagnose_zero_trades.py")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
