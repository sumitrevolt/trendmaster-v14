"""
main.py — TrendMaster v14 unified CLI entry point.

Subcommands
-----------
    python main.py scan            One-shot scan across all TRADING_PAIRS, print signals, exit.
    python main.py run             Run the brain loop (what START_TRENDMASTER_v14.bat launches).
    python main.py dashboard       Launch the local dashboard (tools/dashboard.py).
    python main.py supervise       Run the brain + dashboard under the supervisor (auto-restart).
    python main.py backtest SYM    Walk-forward backtest on a CSV in data/.
    python main.py train SYM       Retrain LightGBM from labelled trades.csv + feature history.
    python main.py pull-history    Pull M5 bars for every pair in TRADING_PAIRS to data/.
    python main.py health          Probe brain PID + dashboard HTTP, print result, exit(0/1).

All subcommands import lazily so a broken optional dep (e.g. lightgbm missing)
doesn't prevent you from running the ones that don't need it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# [enhancement 2026-04-23] Install the JSON-lines formatter when
# LOG_FORMAT=json is set in the environment. No-op otherwise. Called
# once per process, before any other module's logger is used so the
# formatter attaches cleanly.
try:
    from ai_trading_agents.structured_log import configure as _sl_configure
    _sl_configure()
except Exception:
    # Defensive — structured logging must never prevent brain boot.
    pass


def _cmd_scan(args: argparse.Namespace) -> int:
    from ai_trading_agents.multi_market_dispatcher import scan_once
    results = scan_once(symbols=args.symbols, min_votes=args.min_votes)
    for sym, sig in results.items():
        print(f"{sym:>8s}  {sig['direction']:>4s}  conf={sig['confidence']:.2f}  "
              f"agents={sig.get('agent_summary', 'n/a')}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from ai_trading_agents.trend_master_brain import main as brain_main
    return int(brain_main() or 0)


def _cmd_dashboard(args: argparse.Namespace) -> int:
    import runpy
    runpy.run_path(str(ROOT / "tools" / "dashboard.py"), run_name="__main__")
    return 0


def _cmd_supervise(args: argparse.Namespace) -> int:
    from tools.supervisor import Supervisor
    sup = Supervisor.default()
    sup.run_forever()
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    from tools.backtest import run_backtest
    report = run_backtest(symbol=args.symbol,
                          csv_path=args.csv,
                          min_votes=args.min_votes)
    print(report.format())
    return 0 if report.is_viable() else 2


def _cmd_train(args: argparse.Namespace) -> int:
    from tools.retrain_from_trades import retrain
    return int(retrain(symbol=args.symbol,
                       trades_csv=args.trades,
                       history_csv=args.history) or 0)


def _cmd_pull_history(args: argparse.Namespace) -> int:
    from tools.pull_history import pull_all
    return int(pull_all(bars=args.bars) or 0)


def _cmd_health(args: argparse.Namespace) -> int:
    from tools.supervisor import probe_health
    ok = probe_health()
    print("OK" if ok else "UNHEALTHY")
    return 0 if ok else 1


# [enhancement 2026-04-23 R4] Operator-grade CLI commands.
def _cmd_smoke(args: argparse.Namespace) -> int:
    """Full-stack health probe — every module + settings + brain state."""
    import json
    from config import settings
    from ai_trading_agents import (
        drift_detector, kelly_sizer, metrics, portfolio_risk,
        event_log, performance, market_calendar,
    )
    print("== modules ==")
    print("  drift_detector    OK")
    print("  kelly_sizer       OK")
    print("  metrics           OK")
    print("  portfolio_risk    OK")
    print("  event_log         OK")
    print("  performance       OK")
    print("  market_calendar   OK")
    print("== settings flags ==")
    for k in ("METRICS", "DRIFT", "KELLY_SIZING", "PORTFOLIO_RISK",
              "EVENT_LOG", "MARKET_CALENDAR", "DAILY_DIGEST",
              "OPS_MAINTENANCE", "MODEL_GOVERNANCE"):
        v = getattr(settings, k, None)
        en = v.get("enabled", "n/a") if isinstance(v, dict) else "MISSING"
        print(f"  {k:20s} enabled={en}")
    # Snapshot metrics / VaR to confirm they're running.
    txt = metrics.render_text()
    print(f"== metrics == ({len(txt)} bytes, uptime line "
          f"{'OK' if 'trendmaster_uptime_seconds' in txt else 'MISSING'})")
    return 0


def _cmd_rotate(args: argparse.Namespace) -> int:
    from ai_trading_agents import ops_maintenance as _om
    report = _om.run_all()
    import json
    print(json.dumps(report.as_dict(), indent=2))
    return 0


def _cmd_daily_report(args: argparse.Namespace) -> int:
    from ai_trading_agents import daily_digest as _dd
    from ai_trading_agents.state_store import StateStore
    try:
        from ai_trading_agents.risk_manager import team_of
    except Exception:
        team_of = None
    state = StateStore().load()
    digest = _dd.generate_report(state, team_of_fn=team_of)
    paths = _dd.write_daily(digest, ROOT / "reports")
    if args.telegram:
        _dd.push_telegram(digest)
    print(f"Wrote {paths['md']}")
    print(f"Wrote {paths['json']}")
    return 0


def _cmd_stress(args: argparse.Namespace) -> int:
    from tools.stress_test import main as stress_main
    return int(stress_main() or 0)


def _cmd_gates(args: argparse.Namespace) -> int:
    from ai_trading_agents import gate_value as _gv
    report = _gv.analyze(window_days=args.days)
    print(report.human())
    return 0


def _cmd_perf(args: argparse.Namespace) -> int:
    from ai_trading_agents import performance as _p
    from ai_trading_agents.state_store import StateStore
    state = StateStore().load()
    trades = state.get("recent_results", [])
    import json
    try:
        from ai_trading_agents.risk_manager import team_of
    except Exception:
        team_of = None
    snap = _p.snapshot(trades, team_of_fn=team_of)
    print(json.dumps(snap, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trendmaster",
                                description="TrendMaster v14 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_scan = sub.add_parser("scan", help="One-shot multi-pair signal scan")
    s_scan.add_argument("--symbols", nargs="*", default=None,
                        help="Override TRADING_PAIRS. Default: all configured pairs.")
    s_scan.add_argument("--min-votes", type=int, default=3)
    s_scan.set_defaults(func=_cmd_scan)

    s_run = sub.add_parser("run", help="Run brain loop (MT5 required)")
    s_run.set_defaults(func=_cmd_run)

    s_dash = sub.add_parser("dashboard", help="Launch local dashboard")
    s_dash.set_defaults(func=_cmd_dashboard)

    s_sup = sub.add_parser("supervise",
                           help="Run brain + dashboard under supervisor")
    s_sup.set_defaults(func=_cmd_supervise)

    s_bt = sub.add_parser("backtest", help="Walk-forward backtest a CSV")
    s_bt.add_argument("symbol")
    s_bt.add_argument("--csv", default=None,
                      help="Path to OHLCV csv. Default: data/{symbol}_m5_history.csv")
    s_bt.add_argument("--min-votes", type=int, default=3)
    s_bt.set_defaults(func=_cmd_backtest)

    s_tr = sub.add_parser("train", help="Retrain from labelled trades")
    s_tr.add_argument("symbol")
    s_tr.add_argument("--trades", default=None)
    s_tr.add_argument("--history", default=None)
    s_tr.set_defaults(func=_cmd_train)

    s_ph = sub.add_parser("pull-history", help="Pull M5 bars for every pair")
    s_ph.add_argument("--bars", type=int, default=50000)
    s_ph.set_defaults(func=_cmd_pull_history)

    s_h = sub.add_parser("health", help="Probe brain + dashboard health")
    s_h.set_defaults(func=_cmd_health)

    # [enhancement 2026-04-23 R4] Operator-grade subcommands.
    s_sm = sub.add_parser("smoke", help="One-shot full-stack validation")
    s_sm.set_defaults(func=_cmd_smoke)

    s_rt = sub.add_parser("rotate",
                          help="Rotate logs + snapshot state + vacuum events")
    s_rt.set_defaults(func=_cmd_rotate)

    s_dr = sub.add_parser("daily-report",
                          help="Generate today's daily digest (MD + JSON)")
    s_dr.add_argument("--telegram", action="store_true",
                      help="Also push to Telegram")
    s_dr.set_defaults(func=_cmd_daily_report)

    s_st = sub.add_parser("stress",
                          help="Run the Monte Carlo stress-test harness")
    s_st.set_defaults(func=_cmd_stress)

    s_gt = sub.add_parser("gates",
                          help="Show gate-value attribution over N days")
    s_gt.add_argument("--days", type=int, default=30)
    s_gt.set_defaults(func=_cmd_gates)

    s_pf = sub.add_parser("perf",
                          help="Print performance snapshot (JSON)")
    s_pf.set_defaults(func=_cmd_perf)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
