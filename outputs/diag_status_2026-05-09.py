"""Post-restart diagnostic — lists all TrendMaster python processes and
all open MT5 positions. Read-only; does NOT close trades or kill anything.

Run via: outputs\\diag_status_2026-05-09.cmd
"""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # OK: outside the junction
sys.path.insert(0, str(ROOT))


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def list_trendmaster_python_procs() -> list[dict]:
    """Return every python/pythonw process whose cmdline mentions a
    TrendMaster module. Identifies role from the script name."""
    try:
        import psutil
    except ImportError:
        print("psutil missing — install via:  .venv\\Scripts\\pip install psutil")
        return []

    role_keys = [
        ("trend_master_brain", "BRAIN"),
        ("python_signal_executor", "EXECUTOR-MT5"),
        ("ctrader_executor", "EXECUTOR-CTRADER"),
        ("trailing_stop_manager", "TRAILING-STOP"),
        ("tv_webhook_receiver", "TV-WEBHOOK"),
        ("health_watchdog", "WATCHDOG"),
        ("multi_market_dispatcher", "DISPATCHER"),
    ]

    rows: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            name = (p.info.get("name") or "").lower()
            if "python" not in name:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if "trendmaster" not in cmd.lower() and "autmated trading" not in cmd.lower():
                continue
            role = "?"
            for key, label in role_keys:
                if key in cmd:
                    role = label
                    break
            rows.append(
                {
                    "pid": p.info["pid"],
                    "role": role,
                    "started": datetime.fromtimestamp(p.info["create_time"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "cmd": cmd,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return rows


def detect_duplicates(rows: list[dict]) -> dict[str, list[dict]]:
    """Roles that should have at most ONE instance."""
    singletons = {"BRAIN", "EXECUTOR-MT5", "EXECUTOR-CTRADER", "TRAILING-STOP", "TV-WEBHOOK", "DISPATCHER"}
    by_role: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_role[r["role"]].append(r)
    return {role: procs for role, procs in by_role.items() if role in singletons and len(procs) > 1}


def list_open_mt5_positions() -> list[dict]:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("MetaTrader5 module missing")
        return []

    if not mt5.initialize():
        print(f"MT5 initialize failed: {mt5.last_error()}")
        return []

    try:
        positions = mt5.positions_get()
        if positions is None:
            print(f"positions_get returned None: {mt5.last_error()}")
            return []

        team_map = {
            "XAUUSD": "METALS", "XAGUSD": "METALS",
            "EURUSD": "FOREX", "GBPUSD": "FOREX", "USDJPY": "FOREX", "USDCHF": "FOREX",
            "AUDUSD": "FOREX", "NZDUSD": "FOREX", "USDCAD": "FOREX", "EURJPY": "FOREX",
            "GBPJPY": "FOREX", "AUDJPY": "FOREX", "CADJPY": "FOREX", "EURGBP": "FOREX",
            "BTCUSD": "CRYPTO", "ETHUSD": "CRYPTO",
            "XTIUSD": "COMMODITIES", "XBRUSD": "COMMODITIES", "XNGUSD": "COMMODITIES",
        }

        rows: list[dict] = []
        for p in positions:
            sym = p.symbol
            direction = "BUY" if p.type == 0 else "SELL"
            opened_ts = p.time
            age_min = int((time.time() - opened_ts) / 60)
            rows.append(
                {
                    "ticket": p.ticket,
                    "symbol": sym,
                    "direction": direction,
                    "team": team_map.get(sym, "?"),
                    "vol": p.volume,
                    "open_price": p.price_open,
                    "current_price": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "pnl": p.profit,
                    "swap": p.swap,
                    "age_min": age_min,
                    "comment": p.comment,
                }
            )
        return rows
    finally:
        mt5.shutdown()


def usd_concentration(positions: list[dict]) -> tuple[int, int]:
    """Counts long-USD and short-USD direction (matches safeguards.py)."""
    LONG_USD_RULES = {
        ("USDJPY", "BUY"), ("USDCHF", "BUY"), ("USDCAD", "BUY"),
        ("EURUSD", "SELL"), ("GBPUSD", "SELL"), ("AUDUSD", "SELL"),
        ("NZDUSD", "SELL"), ("XAUUSD", "SELL"), ("XAGUSD", "SELL"),
        ("XTIUSD", "SELL"), ("XBRUSD", "SELL"), ("XNGUSD", "SELL"),
        ("BTCUSD", "SELL"), ("ETHUSD", "SELL"),
    }
    SHORT_USD_RULES = {
        ("USDJPY", "SELL"), ("USDCHF", "SELL"), ("USDCAD", "SELL"),
        ("EURUSD", "BUY"), ("GBPUSD", "BUY"), ("AUDUSD", "BUY"),
        ("NZDUSD", "BUY"), ("XAUUSD", "BUY"), ("XAGUSD", "BUY"),
        ("XTIUSD", "BUY"), ("XBRUSD", "BUY"), ("XNGUSD", "BUY"),
        ("BTCUSD", "BUY"), ("ETHUSD", "BUY"),
    }
    long_usd = sum(1 for p in positions if (p["symbol"], p["direction"]) in LONG_USD_RULES)
    short_usd = sum(1 for p in positions if (p["symbol"], p["direction"]) in SHORT_USD_RULES)
    return long_usd, short_usd


def main() -> int:
    print(f"TrendMaster post-restart diagnostic  ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"Project root: {ROOT}")

    # ---- 1. Python processes ----
    section("[1/3] TrendMaster python processes")
    procs = list_trendmaster_python_procs()
    if not procs:
        print("(none found — processes likely not started)")
    else:
        print(f"{'PID':>7}  {'ROLE':<18} {'STARTED':<20} CMD")
        for r in sorted(procs, key=lambda x: (x["role"], x["started"])):
            print(f"{r['pid']:>7}  {r['role']:<18} {r['started']:<20} {r['cmd'][:120]}")

    # ---- 2. Duplicate detection ----
    section("[2/3] Duplicate singleton processes")
    dups = detect_duplicates(procs)
    if not dups:
        print("OK - no duplicate singletons.")
    else:
        for role, procs_dup in dups.items():
            print(f"DUPLICATE {role}: {len(procs_dup)} instances")
            procs_dup_sorted = sorted(procs_dup, key=lambda x: x["started"])
            for r in procs_dup_sorted:
                print(f"   PID={r['pid']}  started={r['started']}")
            keep = procs_dup_sorted[-1]
            kill = [p for p in procs_dup_sorted if p["pid"] != keep["pid"]]
            print(f"   recommend KEEP: PID={keep['pid']} (newest)")
            for k in kill:
                print(f"   recommend KILL: PID={k['pid']} (older duplicate)")

    # ---- 3. MT5 open positions ----
    section("[3/3] MT5 open positions")
    positions = list_open_mt5_positions()
    if not positions:
        print("(no open positions)")
    else:
        total_pnl = sum(p["pnl"] for p in positions)
        total_swap = sum(p["swap"] for p in positions)
        long_usd, short_usd = usd_concentration(positions)

        print(f"Total: {len(positions)} positions  |  unrealised P&L = ${total_pnl:+.2f}  swap = ${total_swap:+.2f}")
        print(f"USD concentration:  long-USD={long_usd}/3 cap   short-USD={short_usd}/3 cap")
        if long_usd > 3 or short_usd > 3:
            print("   WARNING: cap breach (probably from positions opened pre-cap)")
        print()

        by_team: dict[str, list[dict]] = defaultdict(list)
        for p in positions:
            by_team[p["team"]].append(p)

        for team in ("METALS", "FOREX", "CRYPTO", "COMMODITIES", "?"):
            team_pos = by_team.get(team, [])
            if not team_pos:
                continue
            team_pnl = sum(p["pnl"] for p in team_pos)
            print(f"--- {team} ({len(team_pos)} pos, P&L ${team_pnl:+.2f}) ---")
            print(f"  {'TICKET':>10}  {'SYMBOL':<7} {'DIR':<4} {'VOL':>5}  {'OPEN':>10} {'NOW':>10}  {'P&L':>8}  age")
            for p in sorted(team_pos, key=lambda x: x["pnl"]):
                print(
                    f"  {p['ticket']:>10}  {p['symbol']:<7} {p['direction']:<4} {p['vol']:>5.2f}  "
                    f"{p['open_price']:>10.4f} {p['current_price']:>10.4f}  ${p['pnl']:>+7.2f}  {p['age_min']:>4}m"
                )

    section("Summary + suggested actions")
    if dups:
        print(f"ACTION 1: kill duplicate executor(s).")
        print(f"  Run:  outputs\\fix_duplicate_executor_2026-05-09.cmd")
    else:
        print("ACTION 1: no duplicate executors detected.")
    print()
    print(f"ACTION 2: review {len(positions)} open positions in MT5.")
    print("  Operator decision: which to keep / close.  Cowork policy = no auto-close.")
    print("  Quick rule of thumb: close any position with age > 4h on losing side, or")
    print("  symbols outside your 8-pair concentrated config (look at team='?' and FX")
    print("  pairs not in your TRADING_PAIRS list).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
