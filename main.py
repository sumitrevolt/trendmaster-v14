#!/usr/bin/env python
"""
main.py — Unified CLI for TrendMaster v14
==========================================

Usage:
    python main.py scan                # One-shot multi-pair scan (offline-safe)
    python main.py run                 # Live brain loop (needs MT5 + EA)
    python main.py supervise           # Auto-restart brain + dashboard
    python main.py dashboard           # Dashboard only (http://localhost:8000)
    python main.py backtest XAUUSD     # Walk-forward backtest
    python main.py pull-history --bars 50000  # M5 history pull
    python main.py train XAUUSD        # Retrain LightGBM model
    python main.py health              # Health probe (exit 0 if OK)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


# ── Argument parser ──────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="trendmaster",
        description="TrendMaster v14 — Multi-Market AI Trading System",
    )
    sub = p.add_subparsers(dest="cmd", help="Available commands")

    # scan
    scan_p = sub.add_parser("scan", help="One-shot multi-pair scan (offline-safe)")
    scan_p.add_argument("--min-votes", type=int, default=3, help="Minimum agent votes")

    # run
    run_p = sub.add_parser("run", help="Live brain inference loop")
    run_p.add_argument("--interval-ms", type=int, default=None, help="Override inference interval (ms)")

    # supervise
    sub.add_parser("supervise", help="Auto-restart brain + dashboard")

    # dashboard
    dash_p = sub.add_parser("dashboard", help="Dashboard only (http://localhost:8000)")
    dash_p.add_argument("--port", type=int, default=8000, help="Dashboard port")

    # backtest
    bt_p = sub.add_parser("backtest", help="Walk-forward backtest for a symbol")
    bt_p.add_argument("symbol", nargs="?", default="XAUUSD", help="Symbol to backtest")
    bt_p.add_argument("--csv", type=str, default=None, help="Custom CSV path")
    bt_p.add_argument("--bars", type=int, default=50000, help="Number of bars")
    bt_p.add_argument("--min-votes", type=int, default=3, help="Minimum agent votes")

    # pull-history
    ph_p = sub.add_parser("pull-history", help="Pull M5 history for all pairs")
    ph_p.add_argument("--bars", type=int, default=50000, help="Number of bars per pair")

    # train
    tr_p = sub.add_parser("train", help="Retrain LightGBM model for a symbol")
    tr_p.add_argument("symbol", nargs="?", default="XAUUSD", help="Symbol to train on")

    # health
    sub.add_parser("health", help="Health probe (exit 0 if OK)")

    return p


# ── Commands ─────────────────────────────────────────────────────────────

def cmd_scan(args: argparse.Namespace) -> int:
    """One-shot scan across all symbols using offline CSVs if available."""
    from ai_trading_agents.trend_master_brain import TrendMasterBrain, ALL_SYMBOLS
    from config import settings

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("scan")
    logger.info("Starting one-shot scan for %d symbols", len(ALL_SYMBOLS))

    brain = TrendMasterBrain()
    results = {}
    for sym in ALL_SYMBOLS:
        try:
            r = brain.tick_once(symbol=sym)
            results[sym] = r
            if r:
                logger.info("[%s] %s (conf=%.2f)", sym, r.get("direction"), r.get("confidence", 0))
            else:
                logger.info("[%s] NONE", sym)
        except Exception as e:
            logger.warning("[%s] scan failed: %s", sym, e)
            results[sym] = None

    buy = sum(1 for r in results.values() if r and r.get("direction") == "BUY")
    sell = sum(1 for r in results.values() if r and r.get("direction") == "SELL")
    none = sum(1 for r in results.values() if r is None or r.get("direction") == "NONE")
    logger.info("Scan complete: BUY=%d SELL=%d NONE=%d", buy, sell, none)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Live brain loop — needs MT5 running + EA attached."""
    from ai_trading_agents.trend_master_brain import TrendMasterBrain

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    brain = TrendMasterBrain()
    brain.run_forever()
    return 0


def cmd_supervise(args: argparse.Namespace) -> int:
    """Auto-restart brain + dashboard."""
    try:
        from tools.supervisor import main as supervisor_main
        return supervisor_main()
    except ImportError:
        logging.error("tools/supervisor.py not found or failed to import.")
        return 1


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Launch the dashboard on http://localhost:{port}."""
    try:
        from tools.dashboard import create_app
        import uvicorn

        app = create_app()
        uvicorn.run(app, host="0.0.0.0", port=args.port)
        return 0
    except ImportError:
        logging.error("tools/dashboard.py not found or failed to import.")
        return 1


def cmd_backtest(args: argparse.Namespace) -> int:
    """Walk-forward backtest for a single symbol."""
    try:
        from tools.backtest import run_backtest
        csv_path = args.csv
        if not csv_path:
            csv_dir = _HERE / "data"
            csv_path = str(csv_dir / f"{args.symbol}_M5.csv")
        return run_backtest(args.symbol, csv_path=csv_path, bars=args.bars)
    except ImportError:
        logging.error("tools/backtest.py not found or failed to import.")
        return 1


def cmd_pull_history(args: argparse.Namespace) -> int:
    """Pull M5 history for all trading pairs."""
    try:
        from tools.pull_history import pull_all
        return pull_all(bars=args.bars)
    except ImportError:
        logging.error("tools/pull_history.py not found or failed to import.")
        return 1


def cmd_train(args: argparse.Namespace) -> int:
    """Retrain LightGBM model for a symbol."""
    try:
        from tools.retrain_from_trades import retrain_symbol
        return retrain_symbol(args.symbol)
    except ImportError:
        logging.error("tools/retrain_from_trades.py not found or failed to import.")
        return 1


def cmd_health(args: argparse.Namespace) -> int:
    """Health probe: exit 0 if signal is fresh + dashboard up."""
    from ai_trading_agents.trend_master_brain import TRENDMASTER_V14
    from config import settings

    cfg = getattr(settings, "TRENDMASTER_V14", {})
    primary = cfg.get("primary_symbol", "XAUUSD")
    stale_secs = 120  # 2 minutes

    # Check signal file freshness
    import time
    try:
        from ai_trading_agents.trend_master_brain import TrendMasterBrain, _HAS_MT5, SIG_FILE, _ROOT
        brain = TrendMasterBrain()
        sig_path = brain._resolve_signal_path()
        data = json.loads(sig_path.read_text(encoding="ascii"))
        ts = data.get("ts", 0)
        age = int(time.time()) - ts
        if age > stale_secs:
            print(f"STALE: signal file is {age}s old (>{stale_secs}s)")
            return 1
        print(f"OK: {primary} {data.get('direction')} conf={data.get('confidence')} age={age}s")
    except FileNotFoundError:
        print("WARN: signal file not found — brain may not be running")
        return 0  # soft fail
    except Exception as e:
        print(f"WARN: health check error: {e}")
        return 0

    # Check dashboard
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:8000/healthz", timeout=3)
        if r.status == 200:
            print("OK: dashboard /healthz responds")
        else:
            print(f"WARN: dashboard /healthz returned {r.status}")
    except Exception:
        print("WARN: dashboard not reachable")

    return 0


# ── Dispatch ─────────────────────────────────────────────────────────────

_COMMANDS = {
    "scan": cmd_scan,
    "run": cmd_run,
    "supervise": cmd_supervise,
    "dashboard": cmd_dashboard,
    "backtest": cmd_backtest,
    "pull-history": cmd_pull_history,
    "train": cmd_train,
    "health": cmd_health,
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return 1

    handler = _COMMANDS.get(args.cmd)
    if handler is None:
        parser.error(f"Unknown command: {args.cmd}")

    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
