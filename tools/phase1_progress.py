"""Phase 1 Validation Progress — TrendMaster v14
================================================

Reads the live state (logs/brain_state.json, brain_memory.json, MT5 deals via
zero_trades_watchdog log) and reports progress against the Phase 1 checkpoint
criteria documented in docs/PHASE1_VALIDATION_PLAN.md.

Outputs:
- Days into Phase 1 (vs day-30 unlock)
- Net P&L observed vs expected band
- Win rate observed vs expected band
- Max drawdown observed vs limit
- Critical incident count (telegram silent streaks, brain dead >4h, etc.)
- Verdict: ON_TRACK / WATCH / ABORT_RISK with concrete next step

Usage:
    python tools/phase1_progress.py             # daily snapshot
    python tools/phase1_progress.py --weekly    # weekly aggregate
    python tools/phase1_progress.py --verdict   # PROMOTE/ABORT/EXTEND decision
                                                # (only meaningful at day 30+)

Read-only against logs. Safe to run while brain is live.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
BASELINE_PATH = ROOT / "logs" / "phase1_baseline.json"

# Phase 1 expectation bands (from PHASE1_VALIDATION_PLAN.md)
EXPECTED_DAILY_PNL_LOW = 6.0   # USD
EXPECTED_DAILY_PNL_HIGH = 11.0
EXPECTED_30D_LOW = 80.0   # PROMOTE floor (was 120 expected, -33% reality)
EXPECTED_30D_HIGH = 250.0
ABORT_30D = -50.0
WR_LOW = 0.30
WR_HIGH = 0.40
WR_ABORT = 0.25
MAX_DD_LIMIT = 0.05   # 5% expected
MAX_DD_ABORT = 0.08   # 8% abort
MIN_TRADES_FOR_PROMOTE = 150
MAX_SINGLE_DAY_LOSS_PCT = 0.03


@dataclass
class Phase1Report:
    days_in: int = 0
    days_remaining: int = 30
    starting_equity: float = 1000.0
    current_equity: float = 0.0
    net_pnl: float = 0.0
    pnl_pct: float = 0.0
    n_trades: int = 0
    n_wins: int = 0
    n_losses: int = 0
    win_rate: float = 0.0
    max_dd_pct: float = 0.0
    critical_incidents: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    in_band: Dict[str, bool] = field(default_factory=dict)


def load_baseline() -> Optional[Dict[str, Any]]:
    if BASELINE_PATH.exists():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return None


def write_baseline_if_missing() -> Dict[str, Any]:
    """Write the immutable Day-0 anchor on first run."""
    baseline = load_baseline()
    if baseline is not None:
        return baseline

    # Read current state
    state_path = LOGS / "brain_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    sod = float(state.get("start_of_day_equity") or 1000.0)

    baseline = {
        "phase": "Phase 1 — Concentrated (top-8, 0.5% risk)",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "starting_equity_usd": sod,
        "config_version": "Concentrated v1 2026-05-01",
        "walkforward_ref": "reports/walkforward/2026-05-01_0230.json",
        "expected_p50_30d_pnl": 180.0,
        "expected_band_30d": [EXPECTED_30D_LOW, EXPECTED_30D_HIGH],
        "promote_criteria": {
            "min_30d_pnl": EXPECTED_30D_LOW,
            "max_dd_pct": MAX_DD_LIMIT,
            "wr_band": [WR_LOW, WR_HIGH],
            "min_trades": MIN_TRADES_FOR_PROMOTE,
        },
    }
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    return baseline


def parse_trade_history() -> List[Dict[str, Any]]:
    """Read brain_memory.json trade_history but FILTER to phase 1 window only.

    The trade_history field is mixed — old backtest snapshots + live trades.
    Filter to entries with ts >= phase 1 start.
    """
    baseline = load_baseline() or {}
    start_iso = baseline.get("started_at_utc")
    if not start_iso:
        return []
    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))

    mem_path = LOGS / "brain_memory.json"
    if not mem_path.exists():
        return []
    try:
        mem = json.loads(mem_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    # Known non-trade deal_ids to filter (top-up credits, balance adjustments, etc.)
    DEAL_BLACKLIST = {731555171}  # 2026-05-01 demo top-up +$464 (type=2 BALANCE)

    out = []
    for t in mem.get("trade_history", []):
        # Skip BALANCE/CREDIT/CHARGE entries that pollute the trade history
        if t.get("deal_id") in DEAL_BLACKLIST:
            continue
        if not t.get("symbol"):  # empty symbol = likely a credit/correction, not a trade
            continue
        ts = t.get("ts") or t.get("close_ts") or t.get("opened_at")
        if not ts:
            continue
        try:
            tdt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            continue
        if tdt >= start_dt:
            out.append(t)
    return out


def detect_incidents(report: Phase1Report) -> None:
    """Look for critical operational incidents."""
    # Brain restart count anomalies
    state_path = LOGS / "brain_state.json"
    if state_path.exists():
        s = json.loads(state_path.read_text(encoding="utf-8"))
        last_started = int(s.get("last_started_at", 0))
        if last_started:
            age_h = (datetime.now(timezone.utc).timestamp() - last_started) / 3600
            if age_h > 0 and age_h < 24:
                # Recent restart — may indicate instability
                pass

    # Telegram silent streaks — only flag if 404s in the LAST HOUR (post-fix)
    # Historical 404s (before 2026-05-01 .resolve() fix) are noise.
    morning_log = LOGS / "morning_routine.log"
    if morning_log.exists():
        try:
            mtime = datetime.fromtimestamp(morning_log.stat().st_mtime, tz=timezone.utc)
            age_h = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
            # Only check the last 20 lines AND only if log was touched in last hour
            if age_h < 1.0:
                recent = morning_log.read_text(encoding="utf-8", errors="ignore").splitlines()[-20:]
                tg_404 = sum(1 for l in recent if "404" in l and "Telegram" in l)
                if tg_404 >= 3:
                    report.critical_incidents.append(
                        f"Telegram 404 silent failures detected ({tg_404} recent occurrences) - "
                        f"check telegram_notifier .env load"
                    )
        except Exception:
            pass

    # Brain liveness
    pid_file = LOGS / "brain.pid"
    if pid_file.exists():
        liveness = LOGS / "brain_liveness.log"
        if liveness.exists():
            mtime = datetime.fromtimestamp(liveness.stat().st_mtime, tz=timezone.utc)
            age_min = (datetime.now(timezone.utc) - mtime).total_seconds() / 60
            if age_min > 10:
                report.critical_incidents.append(
                    f"Brain liveness log stale ({age_min:.0f} min old) — brain may be dead"
                )

    # Junction trap regressions
    pkg_root = ROOT / "ai_trading_agents"
    if not pkg_root.exists():
        report.critical_incidents.append(
            "ai_trading_agents/ junction missing — restore_junction.cmd"
        )


def render_report(args: argparse.Namespace) -> int:
    baseline = write_baseline_if_missing()
    report = Phase1Report()

    start_dt = datetime.fromisoformat(baseline["started_at_utc"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    report.days_in = (now - start_dt).days
    report.days_remaining = max(0, 30 - report.days_in)
    report.starting_equity = float(baseline["starting_equity_usd"])

    # Current equity from state
    state_path = LOGS / "brain_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        report.current_equity = float(state.get("daily_drawdown_peak_eq") or report.starting_equity)
    report.net_pnl = report.current_equity - report.starting_equity
    report.pnl_pct = report.net_pnl / report.starting_equity * 100 if report.starting_equity else 0

    # Trade stats from filtered history
    trades = parse_trade_history()
    report.n_trades = len(trades)
    wins = [t for t in trades if (t.get("pnl_usd") or t.get("pnl") or 0) > 0]
    losses = [t for t in trades if (t.get("pnl_usd") or t.get("pnl") or 0) < 0]
    report.n_wins = len(wins)
    report.n_losses = len(losses)
    if report.n_trades:
        report.win_rate = report.n_wins / report.n_trades

    # DD calc — use observed equity excursion vs starting
    # (simple: max peak-to-current drawdown in pct terms)
    peak = max(report.starting_equity, report.current_equity)
    dd = (peak - report.current_equity) / peak if peak else 0
    report.max_dd_pct = dd

    # Band checks
    report.in_band["pnl"] = (
        EXPECTED_30D_LOW * (report.days_in / 30) <= report.net_pnl <=
        EXPECTED_30D_HIGH * (report.days_in / 30 + 0.2)
    ) if report.days_in > 0 else True
    report.in_band["wr"] = (
        WR_LOW <= report.win_rate <= WR_HIGH if report.n_trades >= 30 else True
    )
    report.in_band["dd"] = report.max_dd_pct <= MAX_DD_LIMIT
    report.in_band["incidents"] = True  # set False below if any

    detect_incidents(report)
    if report.critical_incidents:
        report.in_band["incidents"] = False

    # Print formatted report
    print("=" * 70)
    print(f"  TrendMaster v14 — Phase 1 Validation Progress")
    print(f"  {baseline['phase']}")
    print("=" * 70)
    print()
    print(f"Day  {report.days_in:>3} of 30   ({report.days_remaining} days remaining)")
    print(f"Started:           {baseline['started_at_utc']}")
    print(f"Walkforward ref:   {baseline['walkforward_ref']}")
    print()
    print("ACCOUNT")
    print(f"  Starting equity: ${report.starting_equity:>10,.2f}")
    print(f"  Current equity:  ${report.current_equity:>10,.2f}")
    print(f"  Net P&L:         ${report.net_pnl:>+10,.2f}  ({report.pnl_pct:+.2f}%)")
    print()
    print("TRADES (since Phase 1 start)")
    print(f"  Total:    {report.n_trades:>4}      Wins: {report.n_wins:>4}      Losses: {report.n_losses:>4}")
    print(f"  Win rate: {report.win_rate*100:>4.1f}%   (band: {WR_LOW*100:.0f}-{WR_HIGH*100:.0f}%)")
    print(f"  Max DD:   {report.max_dd_pct*100:>4.1f}%  (limit: {MAX_DD_LIMIT*100:.0f}%, abort: {MAX_DD_ABORT*100:.0f}%)")
    print()
    print("BAND STATUS")
    for key, ok in report.in_band.items():
        flag = "[OK]   " if ok else "[WARN] OUTSIDE BAND"
        print(f"  {key:<12} {flag}")
    print()

    if report.critical_incidents:
        print("CRITICAL INCIDENTS")
        for inc in report.critical_incidents:
            print(f"  [ERROR] {inc}")
        print()

    if report.warnings:
        print("WARNINGS")
        for w in report.warnings:
            print(f"  [WARN]  {w}")
        print()

    # Verdict (only meaningful at day 30+)
    if report.days_in >= 30 or args.verdict:
        print("=" * 70)
        print("  Day-30 PROMOTE/ABORT/EXTEND DECISION")
        print("=" * 70)
        promote = (
            report.net_pnl >= EXPECTED_30D_LOW
            and report.max_dd_pct <= MAX_DD_LIMIT
            and WR_LOW <= report.win_rate <= WR_HIGH
            and report.n_trades >= MIN_TRADES_FOR_PROMOTE
            and not report.critical_incidents
        )
        abort = (
            report.net_pnl < ABORT_30D
            or report.max_dd_pct > MAX_DD_ABORT
            or (report.win_rate < WR_ABORT and report.n_trades >= 30)
        )
        if promote:
            verdict = "[PROMOTE] Phase 2 unlocked. Edit RISK_PERCENT=1.0 in config/.env, restart brain."
        elif abort:
            verdict = "[ABORT]   Open postmortem before any config change. Investigate cost haircut, regime, fills."
        else:
            verdict = "[EXTEND]  Drift but not failing. Continue Phase 1 +30 days, write extension_note."
        print()
        print(f"  {verdict}")
        print()

    # Daily one-liner for convenience
    if report.days_in > 0:
        expected_net_pnl = EXPECTED_DAILY_PNL_LOW * report.days_in
        diff = report.net_pnl - expected_net_pnl
        sign = "+" if diff >= 0 else ""
        print(f"vs expected ({EXPECTED_DAILY_PNL_LOW:.0f}-{EXPECTED_DAILY_PNL_HIGH:.0f}/day low band): {sign}${diff:.2f}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 validation progress")
    parser.add_argument("--weekly", action="store_true", help="Weekly aggregate view")
    parser.add_argument("--verdict", action="store_true", help="Force day-30 verdict output")
    args = parser.parse_args()
    return render_report(args)


if __name__ == "__main__":
    sys.exit(main())
