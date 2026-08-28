"""Rank 19 pairs to pick top 5 for multi-TF setup.

Scoring (lower spread = better, higher signal count = better, higher P/L = better):
  spread_score   = 1 - normalized(spread/ATR ratio)        # 0..1, lower spread → higher score
  signal_score   = normalized(rocket_prime fire count)     # 0..1, more fires → higher score
  pnl_score      = normalized(7-day P/L total)             # 0..1, profitable → higher score

Final = 0.4*spread + 0.3*signal + 0.3*pnl
Output: ranked table + top 5 list saved to reports/top_5_pairs.json
"""
from __future__ import annotations
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parent.parent
SIGNALS_PATH = ROOT / "logs" / "tv_signals.jsonl"
REPORT_PATH = ROOT / "reports" / "top_5_pairs.json"

SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
           "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "EURGBP",
           "EURAUD", "BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD", "XNGUSD"]


def get_spread_ratio(sym: str) -> float | None:
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if not info or not tick:
        return None
    spread_pr = tick.ask - tick.bid
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 15)
    if rates is None or len(rates) < 15:
        return None
    trs = []
    for i in range(1, len(rates)):
        h, l, pc = rates[i]["high"], rates[i]["low"], rates[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else 0
    if atr <= 0:
        return None
    return spread_pr / atr  # 0 = best, 1.0 = spread equals full ATR (terrible)


def get_signal_count(sym: str) -> int:
    if not SIGNALS_PATH.exists():
        return 0
    n = 0
    for line in SIGNALS_PATH.open(encoding="utf-8"):
        try:
            o = json.loads(line)
            if o.get("symbol") == sym and "rocket_prime" in str(o.get("tv_strategy", "")).lower():
                n += 1
        except Exception:
            continue
    return n


def get_pnl_7d(sym: str) -> float:
    since = datetime.now() - timedelta(days=7)
    deals = mt5.history_deals_get(since, datetime.now()) or []
    return sum(d.profit for d in deals if d.symbol == sym and d.entry == mt5.DEAL_ENTRY_OUT)


def main():
    if not mt5.initialize():
        print("mt5 init failed")
        return 1

    rows = []
    for sym in SYMBOLS:
        sr = get_spread_ratio(sym)
        sc = get_signal_count(sym)
        pn = get_pnl_7d(sym)
        rows.append({"symbol": sym, "spread_ratio": sr, "signal_count": sc, "pnl_7d": pn})
    mt5.shutdown()

    # Normalize
    spreads = [r["spread_ratio"] for r in rows if r["spread_ratio"] is not None]
    sig_max = max((r["signal_count"] for r in rows), default=1) or 1
    pnls = [r["pnl_7d"] for r in rows]
    pnl_min, pnl_max = min(pnls), max(pnls)
    pnl_range = max(pnl_max - pnl_min, 0.01)
    spread_max = max(spreads) if spreads else 1

    for r in rows:
        sr = r["spread_ratio"] if r["spread_ratio"] is not None else spread_max
        r["spread_score"] = round(1 - (sr / spread_max), 3) if spread_max > 0 else 0
        r["signal_score"] = round(r["signal_count"] / sig_max, 3)
        r["pnl_score"] = round((r["pnl_7d"] - pnl_min) / pnl_range, 3)
        r["final"] = round(0.4 * r["spread_score"] + 0.3 * r["signal_score"] + 0.3 * r["pnl_score"], 3)

    rows.sort(key=lambda x: -x["final"])
    print()
    print(f"{'Rank':<5} {'Symbol':<10} {'Spread%ATR':<11} {'Signals':<8} {'P/L 7d':<10} {'SprS':<6} {'SigS':<6} {'PnLS':<6} {'Final':<6}")
    print("-" * 80)
    for i, r in enumerate(rows, 1):
        sr_disp = f"{r['spread_ratio']*100:.1f}%" if r['spread_ratio'] is not None else "n/a"
        marker = "  <-- TOP 5" if i <= 5 else ""
        print(f"{i:<5} {r['symbol']:<10} {sr_disp:<11} {r['signal_count']:<8} {r['pnl_7d']:<+10.2f} "
              f"{r['spread_score']:<6} {r['signal_score']:<6} {r['pnl_score']:<6} {r['final']:<6}{marker}")

    top_5 = [r["symbol"] for r in rows[:5]]
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps({"top_5": top_5, "ranked": rows,
                                          "computed_at": datetime.now().isoformat()},
                                         indent=2), encoding="utf-8")
    print(f"\nTop 5: {top_5}")
    print(f"Saved -> {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
