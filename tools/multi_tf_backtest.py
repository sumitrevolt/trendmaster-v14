"""Multi-timeframe backtest — finds the BEST timeframe per pair.

For each of 19 pairs, runs the same reversal signal logic (RSI extremes +
price-in-range position, mirroring Rocket Prime's reversal style) across
M5/M15/H1/H4. Simulates the live 2-leg + trailing strategy. Reports per-
(pair, TF) win rate, expectancy, total R. Selects the BEST TF per pair.

Output:
  reports/multi_tf_backtest_YYYY-MM-DD.json
  reports/best_tf_per_pair.json    (input for TV alert reconfig)

Run:
  python tools/multi_tf_backtest.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = [
    "XAUUSD", "XAGUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY",
    "CADJPY", "EURGBP",
    "BTCUSD", "ETHUSD",
    "XTIUSD", "XBRUSD", "XNGUSD",
]

# Timeframe definitions: bar duration in minutes
TIMEFRAMES = {
    "M5":  5,
    "M15": 15,
    "H1":  60,
    "H4":  240,
}

# Strategy parameters (mirror live executor)
QUICK_TP_ATR = 1.5
QUICK_SL_ATR = 3.0
TREND_TP_ATR = 5.0
TREND_SL_ATR = 3.0
TRAIL_ACTIVATE_ATR = 1.0
TRAIL_DISTANCE_ATR = 1.5
ATR_PERIOD = 14
RSI_PERIOD = 14
RANGE_LOOKBACK = 20
MAX_HOLD_BARS = 96  # max bars to hold any trade (4 days on H1)
MIN_SIGNALS_FOR_RANK = 10  # don't rank a TF with < N signals (insufficient sample)


def load_m5(symbol: str) -> pd.DataFrame:
    """Load M5 CSV. Returns DataFrame with datetime index + ohlcv cols."""
    p = DATA_DIR / f"{symbol.lower()}_m5_history.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if "time" not in df.columns:
        # Try alternate
        df.columns = [c.lower() for c in df.columns]
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time").sort_index()
    return df


def resample_m5(df_m5: pd.DataFrame, tf_minutes: int) -> pd.DataFrame:
    """Aggregate M5 bars to higher TF."""
    if tf_minutes == 5:
        return df_m5.copy()
    rule = f"{tf_minutes}min" if tf_minutes < 60 else f"{tf_minutes // 60}h"
    out = df_m5.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return out


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add ATR(14), RSI(14), pos_in_range(20) columns."""
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()
    # RSI
    delta = c.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    avg_up = up.rolling(RSI_PERIOD).mean()
    avg_down = down.rolling(RSI_PERIOD).mean()
    rs = avg_up / avg_down.replace(0, 1e-9)
    df["rsi"] = 100 - (100 / (1 + rs))
    # Position in range (0 = at low of last N bars, 1 = at high)
    rolling_high = h.rolling(RANGE_LOOKBACK).max()
    rolling_low = l.rolling(RANGE_LOOKBACK).min()
    df["pos_in_range"] = (c - rolling_low) / (rolling_high - rolling_low).replace(0, 1e-9)
    return df


def generate_signals(df: pd.DataFrame) -> List[Tuple[int, str]]:
    """Reversal signals at extremes (mirrors Rocket Prime's reversal style).
    Returns list of (bar_index, "BUY"|"SELL")."""
    signals = []
    for i in range(max(ATR_PERIOD, RSI_PERIOD, RANGE_LOOKBACK) + 5, len(df)):
        if pd.isna(df["atr"].iloc[i]) or pd.isna(df["rsi"].iloc[i]):
            continue
        rsi = df["rsi"].iloc[i]
        pos = df["pos_in_range"].iloc[i]
        # BUY: oversold reversal — bottom of range AND oversold RSI
        if pos < 0.3 and rsi < 35:
            signals.append((i, "BUY"))
        # SELL: overbought reversal — top of range AND overbought RSI
        elif pos > 0.7 and rsi > 65:
            signals.append((i, "SELL"))
    return signals


def simulate_trade(df: pd.DataFrame, entry_idx: int, direction: str,
                   sl_atr: float, tp_atr: float, trailing: bool) -> Dict:
    """Simulate one trade. Returns {'exit_reason', 'r': R-multiple, 'bars_held'}."""
    if entry_idx + 1 >= len(df):
        return None
    atr = df["atr"].iloc[entry_idx]
    if pd.isna(atr) or atr <= 0:
        return None
    entry_price = df["close"].iloc[entry_idx]
    sl_dist = sl_atr * atr
    tp_dist = tp_atr * atr
    is_buy = direction == "BUY"
    if is_buy:
        sl = entry_price - sl_dist
        tp = entry_price + tp_dist
    else:
        sl = entry_price + sl_dist
        tp = entry_price - tp_dist

    # Walk forward
    cur_sl = sl
    activated = False
    for j in range(entry_idx + 1, min(entry_idx + 1 + MAX_HOLD_BARS, len(df))):
        h = df["high"].iloc[j]
        l = df["low"].iloc[j]
        # Trailing logic (Trend leg only)
        if trailing:
            if is_buy:
                favorable = h - entry_price
                if favorable >= TRAIL_ACTIVATE_ATR * atr:
                    activated = True
                    new_sl = h - TRAIL_DISTANCE_ATR * atr
                    if new_sl > cur_sl:
                        cur_sl = new_sl
            else:
                favorable = entry_price - l
                if favorable >= TRAIL_ACTIVATE_ATR * atr:
                    activated = True
                    new_sl = l + TRAIL_DISTANCE_ATR * atr
                    if new_sl < cur_sl:
                        cur_sl = new_sl
        # Hit SL or TP?
        if is_buy:
            if l <= cur_sl:
                exit_price = cur_sl
                r = (exit_price - entry_price) / sl_dist
                return {"exit_reason": "SL" if cur_sl == sl else "TRAIL", "r": r, "bars_held": j - entry_idx}
            if h >= tp:
                exit_price = tp
                r = (exit_price - entry_price) / sl_dist
                return {"exit_reason": "TP", "r": r, "bars_held": j - entry_idx}
        else:
            if h >= cur_sl:
                exit_price = cur_sl
                r = (entry_price - exit_price) / sl_dist
                return {"exit_reason": "SL" if cur_sl == sl else "TRAIL", "r": r, "bars_held": j - entry_idx}
            if l <= tp:
                exit_price = tp
                r = (entry_price - exit_price) / sl_dist
                return {"exit_reason": "TP", "r": r, "bars_held": j - entry_idx}

    # Time exit
    exit_price = df["close"].iloc[min(entry_idx + MAX_HOLD_BARS, len(df) - 1)]
    if is_buy:
        r = (exit_price - entry_price) / sl_dist
    else:
        r = (entry_price - exit_price) / sl_dist
    return {"exit_reason": "TIME", "r": r, "bars_held": MAX_HOLD_BARS}


def backtest_pair_tf(symbol: str, tf_name: str, tf_minutes: int) -> Dict:
    df_m5 = load_m5(symbol)
    if df_m5 is None or len(df_m5) < 200:
        return None
    df = resample_m5(df_m5, tf_minutes)
    if len(df) < 200:
        return None
    df = compute_indicators(df)
    signals = generate_signals(df)
    if not signals:
        return None

    # Per-leg simulation
    quick_results = []
    trend_results = []
    last_signal_bar = -1
    cooldown_bars = max(60 // tf_minutes, 1) * 5  # ~5h cooldown
    for bar_idx, direction in signals:
        if bar_idx - last_signal_bar < cooldown_bars:
            continue
        last_signal_bar = bar_idx
        q = simulate_trade(df, bar_idx, direction, QUICK_SL_ATR, QUICK_TP_ATR, trailing=False)
        t = simulate_trade(df, bar_idx, direction, TREND_SL_ATR, TREND_TP_ATR, trailing=True)
        if q:
            quick_results.append(q)
        if t:
            trend_results.append(t)

    n = len(quick_results)
    if n == 0:
        return None

    def metrics(results):
        if not results:
            return {"n": 0, "wr": 0, "total_r": 0, "avg_r": 0}
        wins = sum(1 for r in results if r["r"] > 0)
        total_r = sum(r["r"] for r in results)
        return {
            "n": len(results),
            "wr": round(wins / len(results) * 100, 1),
            "total_r": round(total_r, 2),
            "avg_r": round(total_r / len(results), 3),
        }

    q_m = metrics(quick_results)
    t_m = metrics(trend_results)
    combined_total_r = q_m["total_r"] + t_m["total_r"]
    return {
        "n_signals": n,
        "quick": q_m,
        "trend": t_m,
        "combined_r": round(combined_total_r, 2),
        "combined_per_signal_r": round(combined_total_r / n, 3) if n else 0,
    }


def select_best_tf(pair_results: Dict[str, Dict]) -> str:
    """Pick TF with the highest expected R per signal, with min sample size."""
    candidates = []
    for tf, res in pair_results.items():
        if res is None or res["n_signals"] < MIN_SIGNALS_FOR_RANK:
            continue
        candidates.append((tf, res["combined_per_signal_r"], res["combined_r"]))
    if not candidates:
        return "H1"  # fallback
    # Rank by per-signal R first (stable across sample sizes)
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def main():
    print(f"Multi-TF backtest started — {datetime.now().isoformat(timespec='seconds')}\n")
    all_results = {}
    summary = []

    for sym in SYMBOLS:
        per_tf = {}
        for tf_name, tf_min in TIMEFRAMES.items():
            res = backtest_pair_tf(sym, tf_name, tf_min)
            per_tf[tf_name] = res
        all_results[sym] = per_tf

        # Print per-pair table
        print(f"=== {sym} ===")
        print(f"{'TF':<5} {'Signals':<8} {'Q wr':<6} {'Q R':<8} {'T wr':<6} {'T R':<8} {'Total R':<10} {'R/sig':<7}")
        for tf in TIMEFRAMES.keys():
            res = per_tf.get(tf)
            if res is None:
                print(f"{tf:<5} (insufficient data)")
                continue
            print(f"{tf:<5} {res['n_signals']:<8} "
                  f"{res['quick']['wr']:<6} {res['quick']['total_r']:<8} "
                  f"{res['trend']['wr']:<6} {res['trend']['total_r']:<8} "
                  f"{res['combined_r']:<10} {res['combined_per_signal_r']:<7}")
        best = select_best_tf(per_tf)
        print(f"  -> BEST TF: {best}\n")
        summary.append({"symbol": sym, "best_tf": best, "all": per_tf})

    # Save full report
    today = datetime.now().strftime("%Y-%m-%d")
    full_path = REPORT_DIR / f"multi_tf_backtest_{today}.json"
    full_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
    print(f"\nFull report -> {full_path}")

    # Save best-TF map
    best_map = {s["symbol"]: s["best_tf"] for s in summary}
    best_path = REPORT_DIR / "best_tf_per_pair.json"
    best_path.write_text(json.dumps(best_map, indent=2), encoding="utf-8")
    print(f"Best-TF map -> {best_path}")

    # Print summary table
    print("\n=== BEST TF SELECTION SUMMARY ===")
    print(f"{'Symbol':<10} {'Best TF':<8}")
    for s in summary:
        print(f"{s['symbol']:<10} {s['best_tf']:<8}")


if __name__ == "__main__":
    sys.exit(main() or 0)
