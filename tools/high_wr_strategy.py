"""
high_wr_strategy.py — High win-rate strategy targeting 80%+ WR.

Key insight from diagnosis:
  Winners: higher volume, RSI in 40-65 zone, ADX > 30, 3-bar continuation
  Losers: peak session traps, low volume, RSI divergence

Strategy: Only take trades where 6+ out of 7 confluence layers agree.
This drastically reduces trade count but maximizes win rate.
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_trading_agents.multi_agent import vote_all
from tools.backtest import _resample


# ── Fast numpy indicators ────────────────────────────────────────────────
def _ema(arr, n):
    alpha = 2.0 / (n + 1)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out

def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    avg_up = _ema(up, n)
    avg_dn = _ema(dn, n)
    rs = np.where(avg_dn == 0, 100, avg_up / avg_dn)
    return 100 - 100 / (1 + rs)

def _atr(h, l, c, n=14):
    prev_c = np.roll(c, 1); prev_c[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    out = np.full_like(tr, np.nan)
    for i in range(n - 1, len(tr)):
        out[i] = np.mean(tr[i - n + 1: i + 1])
    return out

def _adx(h, l, c, n=14):
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr_s = _ema(tr, n); atr_s = np.where(atr_s == 0, np.nan, atr_s)
    pdi = 100 * _ema(plus_dm, n) / atr_s
    mdi = 100 * _ema(minus_dm, n) / atr_s
    dx = 100 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, np.nan, pdi + mdi)
    return _ema(np.nan_to_num(dx), n), np.nan_to_num(pdi), np.nan_to_num(mdi)

def _bb(c, n=20, k=2.0):
    sma = np.array([np.mean(c[max(0, i-n+1):i+1]) for i in range(len(c))])
    std = np.array([np.std(c[max(0, i-n+1):i+1]) for i in range(len(c))])
    return sma, sma + k * std, sma - k * std

def _macd(c, fast=12, slow=26, sig=9):
    line = _ema(c, fast) - _ema(c, slow)
    signal = _ema(line, sig)
    return line, signal, line - signal

def _stoch_rsi(c, rsi_n=14, stoch_n=14, k=3):
    r = _rsi(c, rsi_n)
    out_k = np.zeros_like(r)
    for i in range(stoch_n - 1, len(r)):
        w = r[i - stoch_n + 1: i + 1]
        mn, mx = np.min(w), np.max(w)
        out_k[i] = ((r[i] - mn) / (mx - mn) * 100) if mx != mn else 50
    return out_k, _ema(out_k, k)

def _vwap(h, l, c, v):
    tp = (h + l + c) / 3
    return np.cumsum(tp * v) / np.where(np.cumsum(v) == 0, 1, np.cumsum(v))


# ── 7-Layer Confluence Scoring ───────────────────────────────────────────
def compute_7layer_score(direction, i, c, h, l, v, ind):
    """
    7 independent confirmation layers. Each returns pass/fail.
    Score = number of layers passing (0-7).
    All 7 must pass for a trade (or 6/7 with high confidence).
    """
    px = float(c[i])
    passed = 0
    reasons = []

    # Layer 1: ADX Trend Strength
    adx_val = ind["adx"][i]
    if adx_val >= 30:
        passed += 1
        reasons.append(f"L1:ADX={adx_val:.0f}")

    # Layer 2: EMA Stack (full alignment)
    e8, e20, e50, e200 = ind["ema8"][i], ind["ema20"][i], ind["ema50"][i], ind["ema200"][i]
    if direction == 1 and e8 > e20 > e50 > e200 and px > e20:
        passed += 1
        reasons.append("L2:EMA_STACK_BULL")
    elif direction == -1 and e8 < e20 < e50 < e200 and px < e20:
        passed += 1
        reasons.append("L2:EMA_STACK_BEAR")

    # Layer 3: RSI Sweet Spot (not extreme, in trend zone)
    rsi_val = ind["rsi"][i]
    if direction == 1 and 40 <= rsi_val <= 65:
        passed += 1
        reasons.append(f"L3:RSI={rsi_val:.0f}")
    elif direction == -1 and 35 <= rsi_val <= 60:
        passed += 1
        reasons.append(f"L3:RSI={rsi_val:.0f}")

    # Layer 4: MACD Momentum Agreement
    mh = ind["macd_h"][i]
    mh_prev = ind["macd_h"][i-1] if i > 0 else mh
    if direction == 1 and mh > 0 and mh > mh_prev:
        passed += 1
        reasons.append("L4:MACD_BULL_RISING")
    elif direction == -1 and mh < 0 and mh < mh_prev:
        passed += 1
        reasons.append("L4:MACD_BEAR_FALLING")

    # Layer 5: Bollinger Band Zone (not at extremes)
    bb_m, bb_u, bb_l = ind["bb_mid"][i], ind["bb_up"][i], ind["bb_lo"][i]
    if bb_u > bb_l:
        if direction == 1 and bb_m < px < bb_u * 0.95:
            passed += 1
            reasons.append("L5:BB_BULL")
        elif direction == -1 and bb_l * 1.05 < px < bb_m:
            passed += 1
            reasons.append("L5:BB_BEAR")

    # Layer 6: Volume Confirmation (> 1.2x average)
    vol_avg = np.mean(v[max(0, i-50):i]) if i >= 50 else np.mean(v[:i+1])
    vol_ratio = v[i] / (vol_avg + 1)
    if vol_ratio >= 1.2:
        passed += 1
        reasons.append(f"L6:VOL={vol_ratio:.1f}x")

    # Layer 7: Price Action (3-bar continuation)
    if i >= 3:
        if direction == 1 and c[i] > c[i-1] > c[i-2]:
            passed += 1
            reasons.append("L7:3BAR_BULL")
        elif direction == -1 and c[i] < c[i-1] < c[i-2]:
            passed += 1
            reasons.append("L7:3BAR_BEAR")

    return passed, reasons


def run_high_wr_backtest(symbol, bars=5000, min_layers=6, verbose=True):
    path = _ROOT / "data" / f"{symbol.lower()}_m5_history.csv"
    df = pd.read_csv(path, nrows=bars + 200)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].sort_index().tail(bars)

    h, l, c, v = (df["high"].values.astype(float), df["low"].values.astype(float),
                   df["close"].values.astype(float), df["volume"].values.astype(float))

    ind = {
        "adx": _adx(h, l, c, 14)[0],
        "rsi": _rsi(c, 14),
        "ema8": _ema(c, 8), "ema20": _ema(c, 20),
        "ema50": _ema(c, 50), "ema200": _ema(c, 200),
        "bb_mid": _bb(c)[0], "bb_up": _bb(c)[1], "bb_lo": _bb(c)[2],
        "macd_h": _macd(c)[2],
        "stoch_k": _stoch_rsi(c)[0],
        "atr": _atr(h, l, c, 14),
        "vwap": _vwap(h, l, c, v),
    }

    n = len(df)
    trades = []
    warmup = 600

    for i in range(warmup, n - 24, 12):
        a = ind["atr"][i]
        if not np.isfinite(a) or a <= 0: continue

        # Session filter
        try: hour = df.index[i].hour
        except: hour = 12
        if not (7 <= hour <= 20): continue

        # Agent vote (for direction)
        win_df = df.iloc[:i+1]
        frames = {'M30': _resample(win_df, 30), 'H1': _resample(win_df, 60), 'H4': _resample(win_df, 240)}
        direction, _ = vote_all(frames, min_votes=2)
        if direction == 0: continue

        # 7-Layer Confluence Score
        score, reasons = compute_7layer_score(direction, i, c, h, l, v, ind)
        if score < min_layers: continue

        px = float(c[i])
        sl_m = 1.0; rr = 2.5
        sd = sl_m * a
        hold = 18

        if direction == 1:
            sl_px, tp_px = px - sd, px + rr * sd
        else:
            sl_px, tp_px = px + sd, px - rr * sd

        r_mult = -1.0
        exit_px = sl_px
        for j in range(i+1, min(i+1+hold, n)):
            if direction == 1:
                if l[j] <= sl_px: exit_px = sl_px; break
                if h[j] >= tp_px: r_mult = rr; exit_px = tp_px; break
            else:
                if h[j] >= sl_px: exit_px = sl_px; break
                if l[j] <= tp_px: r_mult = rr; exit_px = tp_px; break
        else:
            exit_px = float(c[min(i+hold, n-1)])
            r_mult = round((exit_px - px) / sd * (1 if direction == 1 else -1), 3)

        trades.append({
            "r": r_mult, "score": score, "reasons": reasons,
            "outcome": "W" if r_mult > 0 else "L",
        })

    if not trades:
        return None

    r_arr = np.array([t["r"] for t in trades])
    n_tr = len(trades)
    wins = int(np.sum(r_arr > 0))
    wr = wins / n_tr
    avg_r = float(np.mean(r_arr))
    gross = float(np.sum(r_arr))
    std = float(np.std(r_arr, ddof=1)) if n_tr > 1 else 1.0
    sharpe = avg_r / std if std > 0 else 0
    run = best = 0
    for r in r_arr:
        if r <= 0: run += 1; best = max(best, run)
        else: run = 0

    if verbose:
        tag = "V" if wr >= 0.80 else "G" if wr >= 0.60 else "-" if wr >= 0.45 else "X"
        print(f"[{tag}] {symbol:8s} layers>={min_layers} trades={n_tr:4d} WR={wr*100:5.1f}% avgR={avg_r:+.3f} grossR={gross:+.1f} sharpe={sharpe:+.2f} maxCL={best}")

    return {"symbol": symbol, "trades": n_tr, "wins": wins, "win_rate": wr, "avg_r": avg_r,
            "gross_r": gross, "sharpe": sharpe, "maxCL": best, "min_layers": min_layers}


def main():
    print("=" * 80)
    print("HIGH WIN-RATE STRATEGY — 7-Layer Confluence Scoring")
    print("=" * 80)

    pairs = ["XAGUSD", "GBPUSD", "AUDUSD", "USDCHF", "NZDUSD", "EURUSD", "USDJPY", "USDCAD", "XTIUSD"]

    # Test different min_layers thresholds
    for min_layers in [5, 6, 7]:
        print(f"\n--- min_layers = {min_layers}/7 ---")
        print(f"{'Pair':10s} {'Trades':>6s} {'WR%':>6s} {'AvgR':>7s} {'GrossR':>7s} {'Sharpe':>7s} {'MaxCL':>5s}")
        print("-" * 60)

        all_results = []
        for sym in pairs:
            r = run_high_wr_backtest(sym, bars=5000, min_layers=min_layers)
            if r:
                all_results.append(r)

        if all_results:
            total_t = sum(r["trades"] for r in all_results)
            total_w = sum(r["wins"] for r in all_results)
            total_r = sum(r["gross_r"] for r in all_results)
            avg_wr = total_w / total_t if total_t > 0 else 0
            viable = [r for r in all_results if r["win_rate"] >= 0.80]
            print(f"\n  TOTAL: {total_t} trades, WR={avg_wr*100:.1f}%, grossR={total_r:+.1f}, 80%+ pairs: {len(viable)}/{len(all_results)}")

    # Best configuration deep dive
    print("\n" + "=" * 80)
    print("OPTIMAL CONFIGURATION — min_layers=5 (balance of WR + trade frequency)")
    print("=" * 80)

    for sym in pairs:
        run_high_wr_backtest(sym, bars=5000, min_layers=5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
