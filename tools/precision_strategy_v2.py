"""
precision_strategy_v2.py — Relaxed Precision: 70% WR + 2.5R
============================================================
V2: Relaxed layer weights + wider sessions + lower min_score target.
Key insight: Don't need ALL7 layers — need 4+ out of 7 in the RIGHT combination.

Weighted scoring: Some layers matter more than others.
- Layer 1 (Trend): weight 1.5 — MOST important
- Layer 2 (Momentum): weight 1.2
- Layer 3 (Volatility): weight 0.8
- Layer 4 (Volume): weight 0.7
- Layer 5 (Session): weight 1.0
- Layer 6 (Price Action): weight 1.3 — VERY important for WR
- Layer 7 (MTF): weight 1.5 — MOST important for WR

Max weighted score = 8.0. Threshold = 5.0 (= 62.5% of max)

Usage:
    python tools/precision_strategy_v2.py            # Run all pairs
    python tools/precision_strategy_v2.py GBPUSD     # Single pair
    python tools/precision_strategy_v2.py --grid     # Grid search
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Layer weights (importance ranking) ──
LAYER_WEIGHTS = {
    "trend": 1.5,      # MOST important
    "momentum": 1.2,
    "volatility": 0.8,
    "volume": 0.7,
    "session": 1.0,
    "price_action": 1.3,  # VERY important for WR
    "mtf": 1.5,           # MOST important for WR
}
MAX_WEIGHTED = sum(LAYER_WEIGHTS.values())  # 8.0

# ── Per-pair precision parameters ──
PAIR_PARAMS = {
    "GBPUSD": {"sl_atr": 0.8, "tp_atr": 2.0, "max_trades_day": 3,
               "peak_hours": [7,8,9,10,12,13,14,15,16]},
    "AUDUSD": {"sl_atr": 0.8, "tp_atr": 2.0, "max_trades_day": 3,
               "peak_hours": [0,1,2,7,8,12,13]},
    "USDCHF": {"sl_atr": 0.8, "tp_atr": 2.0, "max_trades_day": 3,
               "peak_hours": [7,8,9,12,13,14,15,16]},
    "NZDUSD": {"sl_atr": 0.8, "tp_atr": 2.0, "max_trades_day": 3,
               "peak_hours": [21,22,23,0,1,2,7,8]},
    "EURUSD": {"sl_atr": 0.8, "tp_atr": 2.0, "max_trades_day": 3,
               "peak_hours": [7,8,9,10,12,13,14,15]},
    "USDJPY": {"sl_atr": 0.8, "tp_atr": 2.0, "max_trades_day": 3,
               "peak_hours": [0,1,2,7,8,9,12,13,14,15]},
    "USDCAD": {"sl_atr": 0.8, "tp_atr": 2.0, "max_trades_day": 3,
               "peak_hours": [12,13,14,15,16,17]},
    "XAGUSD": {"sl_atr": 1.0, "tp_atr": 2.5, "max_trades_day": 2,
               "peak_hours": [7,8,9,10,12,13,14,15,16,17,18]},
    "XTIUSD": {"sl_atr": 1.0, "tp_atr": 2.5, "max_trades_day": 2,
               "peak_hours": [13,14,15,16,17,18]},
}

SYMBOL_TO_TEAM = {
    "XAUUSD": "METALS", "XAGUSD": "METALS",
    "GBPJPY": "FOREX", "USDCAD": "FOREX", "USDCHF": "FOREX", "EURUSD": "FOREX",
    "GBPUSD": "FOREX", "AUDUSD": "FOREX", "USDJPY": "FOREX", "NZDUSD": "FOREX",
    "EURJPY": "FOREX", "AUDJPY": "FOREX", "CADJPY": "FOREX", "EURGBP": "FOREX",
    "BTCUSD": "CRYPTO", "ETHUSD": "CRYPTO",
    "XTIUSD": "COMMODITIES", "XBRUSD": "COMMODITIES", "XNGUSD": "COMMODITIES",
}


def _atr_np(highs, lows, closes, n=14):
    prev_c = np.roll(closes, 1); prev_c[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_c), np.abs(lows - prev_c)))
    atr = np.full_like(tr, np.nan)
    for i in range(n - 1, len(tr)):
        atr[i] = np.mean(tr[i - n + 1: i + 1])
    return atr

def _ema_np(arr, n):
    alpha = 2.0 / (n + 1)
    out = np.empty_like(arr, dtype=float); out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out

def _adx_np(highs, lows, closes, n=14):
    up = np.diff(highs, prepend=highs[0])
    dn = -np.diff(lows, prepend=lows[0])
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    prev_c = np.roll(closes, 1); prev_c[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_c), np.abs(lows - prev_c)))
    tr[0] = highs[0] - lows[0]
    atr_s = _ema_np(tr, n); atr_s = np.where(atr_s == 0, np.nan, atr_s)
    pdi = 100 * _ema_np(plus_dm, n) / atr_s
    mdi = 100 * _ema_np(minus_dm, n) / atr_s
    dx = 100 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, np.nan, pdi + mdi)
    adx = _ema_np(np.nan_to_num(dx), n)
    return adx, np.nan_to_num(pdi), np.nan_to_num(mdi)

def _rsi_np(closes, n=14):
    d = np.diff(closes, prepend=closes[0])
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    avg_up = _ema_np(up, n); avg_dn = _ema_np(dn, n)
    rs = np.where(avg_dn == 0, 100, avg_up / avg_dn)
    return 100 - 100 / (1 + rs)

def _bb_np(closes, n=20, k=2.0):
    mid = _ema_np(closes, n)
    std = np.full_like(closes, np.nan)
    for i in range(n - 1, len(closes)):
        std[i] = np.std(closes[i - n + 1: i + 1], ddof=0)
    upper = mid + k * std; lower = mid - k * std
    bw = np.where(mid > 0, (upper - lower) / mid, np.nan)
    return mid, upper, lower, bw

def _macd_np(closes, fast=12, slow=26, sig=9):
    ema_f = _ema_np(closes, fast); ema_s = _ema_np(closes, slow)
    macd_line = ema_f - ema_s; signal_line = _ema_np(macd_line, sig)
    return macd_line, signal_line, macd_line - signal_line


def score_layers(i, o, h, l, c, v, adx_v, pdi_v, mdi_v, rsi_v,
                  ema8_i, ema20_i, ema50_i, ema200_i, bb_mid_i, bb_bw_val, bb_bw_avg_val,
                  atr_v, atr_avg_val, macd_hist, hist_prev, vol_avg_val, vol_sma20_val,
                  ema20_h4_i, ema50_h4_i, ema20_h1_i, ema50_h1_i,
                  direction, hour, peak_hours):
    """Compute weighted7-layer confluence score. Returns (weighted_score, details)."""
    price = float(c[i])
    scores = {}

    # ── Layer 1: TREND (weight 1.5) ──
    s = 0.0
    if adx_v >= 20: s += 0.2
    if adx_v >= 30: s += 0.2
    if adx_v >= 40: s += 0.1
    if direction == 1:
        if ema20_i > ema50_i: s += 0.2
        if ema50_i > ema200_i: s += 0.1
        if price > ema20_i: s += 0.15
        if pdi_v > mdi_v: s += 0.15
    else:
        if ema20_i < ema50_i: s += 0.2
        if ema50_i < ema200_i: s += 0.1
        if price < ema20_i: s += 0.15
        if mdi_v > pdi_v: s += 0.15
    scores["trend"] = min(s, 1.0)

    # ── Layer 2: MOMENTUM (weight 1.2) ──
    s = 0.0
    if direction == 1:
        if 35 <= rsi_v <= 65: s += 0.4
        elif 30 <= rsi_v <= 70: s += 0.2
    else:
        if 35 <= rsi_v <= 65: s += 0.4
        elif 30 <= rsi_v <= 70: s += 0.2
    if direction == 1 and macd_hist > hist_prev: s += 0.4
    elif direction == -1 and macd_hist < hist_prev: s += 0.4
    # MACD above/below zero
    if direction == 1 and macd_hist > 0: s += 0.15
    elif direction == -1 and macd_hist < 0: s += 0.15
    scores["momentum"] = min(s, 1.0)

    # ── Layer 3: VOLATILITY (weight 0.8) ──
    s = 0.0
    bw = bb_bw_val if np.isfinite(bb_bw_val) else 0
    bba = bb_bw_avg_val if np.isfinite(bb_bw_avg_val) else bw
    aa = atr_avg_val if np.isfinite(atr_avg_val) else atr_v
    if bw < bba: s += 0.3  # Below average = squeeze potential
    if atr_v > aa: s += 0.3  # Above average = expansion
    if atr_v > aa * 1.2: s += 0.2  # Strong expansion
    scores["volatility"] = min(s, 1.0)

    # ── Layer 4: VOLUME (weight 0.7) ──
    s = 0.0
    va = vol_avg_val if np.isfinite(vol_avg_val) else v[i]
    vs = vol_sma20_val if np.isfinite(vol_sma20_val) else v[i]
    if va > 0:
        vr = v[i] / va
        if vr > 1.3: s += 0.5
        elif vr > 1.0: s += 0.25
    if vs > 0 and v[i] > vs * 1.1: s += 0.3
    scores["volume"] = min(s, 1.0)

    # ── Layer 5: SESSION (weight 1.0) ──
    if hour in peak_hours:
        scores["session"] = 1.0
    elif any(abs(hour - p) <= 1 for p in peak_hours):
        scores["session"] = 0.5
    else:
        scores["session"] = 0.0

    # ── Layer 6: PRICE ACTION (weight 1.3) ──
    s = 0.0
    if i >= 3:
        body = abs(c[i] - o[i])
        full_range = h[i] - l[i] if h[i] > l[i] else 1e-10
        if direction == 1:
            # Bullish engulfing
            if c[i] > o[i] and c[i-1] < o[i-1] and c[i] > o[i-1]:
                s += 0.35
            # Pin bar (long lower wick)
            lower_wick = min(o[i], c[i]) - l[i]
            if lower_wick > body * 1.5 and lower_wick > full_range * 0.5:
                s += 0.35
            # Strong close
            if body / full_range > 0.5 and c[i] > o[i]:
                s += 0.15
            # Close above EMA8 (fast momentum)
            if c[i] > ema8_i:
                s += 0.15
        else:
            if c[i] < o[i] and c[i-1] > o[i-1] and c[i] < o[i-1]:
                s += 0.35
            upper_wick = h[i] - max(o[i], c[i])
            if upper_wick > body * 1.5 and upper_wick > full_range * 0.5:
                s += 0.35
            if body / full_range > 0.5 and c[i] < o[i]:
                s += 0.15
            if c[i] < ema8_i:
                s += 0.15
    scores["price_action"] = min(s, 1.0)

    # ── Layer 7: MTF (weight 1.5) ──
    h4d = 1 if ema20_h4_i > ema50_h4_i and price > ema20_h4_i else (
         -1 if ema20_h4_i < ema50_h4_i and price < ema20_h4_i else 0)
    h1d = 1 if ema20_h1_i > ema50_h1_i and price > ema20_h1_i else (
         -1 if ema20_h1_i < ema50_h1_i and price < ema20_h1_i else 0)
    m15d = direction  # M5 = M15 proxy
    s = 0.0
    if h4d == direction and h1d == direction and m15d == direction:
        s = 1.0  # Perfect alignment
    elif h4d == direction and h1d == direction:
        s = 0.75
    elif h4d == direction and m15d == direction:
        s = 0.6
    elif h1d == direction and m15d == direction:
        s = 0.5
    elif h4d == direction:
        s = 0.3
    scores["mtf"] = s

    # ── COMPUTE WEIGHTED SCORE ──
    weighted = sum(scores[k] * LAYER_WEIGHTS[k] for k in LAYER_WEIGHTS)
    return weighted, scores


def run_backtest(symbol: str, bars: int = 5000, min_weighted: float = 5.0,
                 sl_mult: float = 0.8, tp_mult: float = 2.0,
                 verbose: bool = True, max_hold: int = 24,
                 cooldown_bars: int = 36, max_day: int = 3) -> dict:
    """Run precision backtest on a single symbol."""
    if symbol not in PAIR_PARAMS:
        return {"symbol": symbol, "error": f"No params", "trades": 0}

    params = PAIR_PARAMS[symbol]
    peak_hours = params["peak_hours"]

    path = _ROOT / "data" / f"{symbol.lower()}_m5_history.csv"
    if not path.exists():
        return {"symbol": symbol, "error": "No data", "trades": 0}

    df = pd.read_csv(path, nrows=bars + 200)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].sort_index().tail(bars)

    o = df["open"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    c = df["close"].values.astype(float)
    v = df["volume"].values.astype(float)
    n = len(df)

    atr = _atr_np(h, l, c, 14)
    adx, pdi, mdi = _adx_np(h, l, c, 14)
    rsi = _rsi_np(c, 14)
    ema8 = _ema_np(c, 8)
    ema20 = _ema_np(c, 20)
    ema50 = _ema_np(c, 50)
    ema200 = _ema_np(c, 200)
    _, _, _, bb_bw = _bb_np(c, 20, 2.0)
    _, _, histogram = _macd_np(c)
    bb_bw_avg = _ema_np(np.nan_to_num(bb_bw), 50)
    atr_avg = _ema_np(np.nan_to_num(atr), 50)
    vol_avg = _ema_np(v, 50)
    vol_sma20 = _ema_np(v, 20)
    ema20_h4 = _ema_np(c, 20 * 12)
    ema50_h4 = _ema_np(c, 50 * 12)
    ema20_h1 = _ema_np(c, 20 * 3)
    ema50_h1 = _ema_np(c, 50 * 3)

    trades = []
    warmup = 600
    day_trade_count = {}
    cooldown_until = 0
    consec_losses = 0

    for i in range(warmup, n - max_hold - 1, 6):  # Check every 30 min
        a = atr[i]
        if not np.isfinite(a) or a <= 0: continue

        # Cooldown
        if consec_losses >= 3:
            cooldown_until = i + cooldown_bars
            consec_losses = 0
        if i < cooldown_until: continue

        # Session
        try: hour = df.index[i].hour
        except: hour = 12
        if symbol not in ("BTCUSD", "ETHUSD"):
            if not any(abs(hour - p) <= 1 for p in peak_hours): continue

        # Daily limit
        try: day_key = str(df.index[i].date())
        except: day_key = "x"
        if day_trade_count.get(day_key, 0) >= max_day: continue

        # Direction via EMA
        e20, e50, e200 = ema20[i], ema50[i], ema200[i]
        if not all(np.isfinite([e20, e50, e200])): continue
        price = float(c[i])

        if e20 > e50 > e200 and price > e20:
            direction = 1
        elif e20 < e50 < e200 and price < e20:
            direction = -1
        else:
            continue

        # RSI filter (no extremes)
        rv = rsi[i]
        if direction == 1 and rv > 72: continue
        if direction == -1 and rv < 28: continue

        # 7-LAYER SCORING
        bb_mid_arr = _bb_np(c, 20, 2.0)[0]
        weighted_score, layer_detail = score_layers(
            i, o, h, l, c, v, adx[i], pdi[i], mdi[i], rsi[i],
            ema8[i], ema20[i], ema50[i], ema200[i],
            bb_mid_arr[i], bb_bw[i], bb_bw_avg[i],
            a, atr_avg[i], histogram[i], histogram[i-1] if i > 0 else 0,
            vol_avg[i], vol_sma20[i], ema20_h4[i], ema50_h4[i], ema20_h1[i], ema50_h1[i],
            direction, hour, peak_hours
        )

        if weighted_score < min_weighted: continue

        # ── TRADE ──
        sd = sl_mult * a
        if direction == 1:
            sl_px, tp_px = price - sd, price + tp_mult * sd
        else:
            sl_px, tp_px = price + sd, price - tp_mult * sd

        trail_activate_r = 1.5
        trail_distance = 0.5 * a
        best_px = price
        r_mult = -1.0
        exit_px = sl_px
        trail_active = False
        exit_reason = "SL"

        for j in range(i + 1, min(i + 1 + max_hold, n)):
            if direction == 1:
                if l[j] <= sl_px:
                    exit_px = sl_px; break
                best_px = max(best_px, h[j])
                if (best_px - price) / sd >= trail_activate_r:
                    trail_active = True
                    new_trail = best_px - trail_distance
                    if new_trail > sl_px: sl_px = new_trail
                if h[j] >= tp_px:
                    r_mult = tp_mult; exit_px = tp_px; exit_reason = "TP"; break
            else:
                if h[j] >= sl_px:
                    exit_px = sl_px; break
                best_px = min(best_px, l[j])
                if (price - best_px) / sd >= trail_activate_r:
                    trail_active = True
                    new_trail = best_px + trail_distance
                    if new_trail < sl_px: sl_px = new_trail
                if l[j] <= tp_px:
                    r_mult = tp_mult; exit_px = tp_px; exit_reason = "TP"; break
        else:
            exit_px = float(c[min(i + max_hold, n - 1)])
            r_mult = round((exit_px - price) / sd * direction, 3)
            exit_reason = "TIME"

        if exit_reason == "SL" and r_mult == -1.0:
            r_mult = round((exit_px - price) / sd * direction, 3)

        trades.append({
            "time": str(df.index[i]),
            "direction": "BUY" if direction == 1 else "SELL",
            "entry": price, "exit": exit_px,
            "r": r_mult, "outcome": "win" if r_mult > 0 else "loss",
            "exit_reason": exit_reason, "score": weighted_score,
            "adx": round(adx[i], 1), "rsi": round(rsi[i], 1),
            "trail_active": trail_active,
        })

        day_trade_count[day_key] = day_trade_count.get(day_key, 0) + 1
        if r_mult <= 0: consec_losses += 1
        else: consec_losses = 0

    if not trades:
        return {"symbol": symbol, "trades": 0, "error": "no trades"}

    r_arr = np.array([t["r"] for t in trades])
    n_tr = len(trades)
    wins = int(np.sum(r_arr > 0))
    wr = wins / n_tr
    avg_r = float(np.mean(r_arr))
    gross = float(np.sum(r_arr))
    std = float(np.std(r_arr, ddof=1)) if n_tr > 1 else 1.0
    sharpe = avg_r / std if std > 0 else 0.0
    run = best_run = 0
    for r in r_arr:
        if r <= 0: run += 1; best_run = max(best_run, run)
        else: run = 0
    gw = float(np.sum(r_arr[r_arr > 0])) if wins > 0 else 0
    gl = float(np.abs(np.sum(r_arr[r_arr <= 0]))) if (n_tr - wins) > 0 else 1
    pf = gw / gl if gl > 0 else 999
    win_rs = r_arr[r_arr > 0]
    avg_win_r = float(np.mean(win_rs)) if len(win_rs) > 0 else 0
    tp_c = sum(1 for t in trades if t["exit_reason"] == "TP")
    sl_c = sum(1 for t in trades if t["exit_reason"] == "SL")
    time_c = sum(1 for t in trades if t["exit_reason"] == "TIME")
    trail_c = sum(1 for t in trades if t.get("trail_active"))

    eppt = avg_r * 5.0  # $5 risk per trade (0.5% of $1000)

    result = {
        "symbol": symbol, "team": SYMBOL_TO_TEAM.get(symbol, "FOREX"),
        "trades": n_tr, "wins": wins, "losses": n_tr - wins,
        "win_rate": wr, "avg_r": avg_r, "avg_win_r": avg_win_r,
        "gross_r": gross, "sharpe": sharpe, "profit_factor": pf,
        "max_consec_loss": best_run,
        "tp_exits": tp_c, "sl_exits": sl_c, "time_exits": time_c, "trail": trail_c,
        "viable": n_tr >= 20 and avg_r > 0,
        "expected_per_trade_usd": eppt,
        "target_70wr": wr >= 0.70, "target_2_5r": avg_win_r >= 2.0,
        "min_weighted": min_weighted, "sl_mult": sl_mult, "tp_mult": tp_mult,
    }

    if verbose:
        tf = "Y" if result["target_70wr"] else "-"
        rf = "Y" if result["target_2_5r"] else "-"
        vf = "V" if result["viable"] else "-"
        print(
            f"[{vf}{tf}{rf}] {symbol:8s} ({result['team']:12s}) "
            f"trades={n_tr:4d} WR={wr*100:5.1f}% avgR={avg_r:+.3f} "
            f"avgWR={avg_win_r:.2f} PF={pf:.2f} sharpe={sharpe:+.2f} "
            f"maxCL={best_run} TP={tp_c} SL={sl_c} TIME={time_c} TRAIL={trail_c} "
            f"~${eppt:+.2f}/tr  score>={min_weighted:.1f}"
        )
    return result


def grid_search(symbol: str, bars: int = 5000):
    """Grid search over min_weighted, sl_mult, tp_mult."""
    print(f"\n{'='*95}")
    print(f"GRID SEARCH: {symbol}")
    print(f"{'='*95}")

    results = []
    # Test combinations: min_weighted, sl, tp
    configs = list(product(
        [4.0, 4.5, 5.0, 5.5, 6.0],   # min_weighted
        [0.6, 0.8, 1.0],               # sl_mult
        [1.5, 2.0, 2.5],               # tp_mult
    ))

    print(f"{'minW':>5s} {'sl':>4s} {'tp':>4s} {'Trades':>6s} {'WR%':>6s} "
          f"{'AvgR':>6s} {'AvgWR':>6s} {'PF':>6s} {'Sharpe':>7s} {'70WR':>5s} {'2.5R':>5s}")
    print("-" * 95)

    for mw, sl, tp in configs:
        r = run_backtest(symbol, bars=bars, min_weighted=mw,
                         sl_mult=sl, tp_mult=tp, verbose=False)
        if r.get("trades", 0) >= 15:
            results.append(r)
            tf = "YES" if r["target_70wr"] else " - "
            rf = "YES" if r["target_2_5r"] else " - "
            print(
                f"{mw:5.1f} {sl:4.1f} {tp:4.1f} {r['trades']:6d} "
                f"{r['win_rate']*100:5.1f}% {r['avg_r']:+.3f} "
                f"{r['avg_win_r']:6.2f} {r['profit_factor']:6.2f} "
                f"{r['sharpe']:+7.2f} {tf:>5s} {rf:>5s}"
            )

    # Find best config
    if results:
        # Target: 70% WR + 2.5R, then maximize expectancy
        best = None
        best_score = -999
        for r in results:
            # Composite score: WR * avg_win_r * sqrt(trades)
            score = r["win_rate"] * r["avg_win_r"] * (r["trades"] ** 0.3)
            if score > best_score:
                best_score = score
                best = r
        if best:
            print(f"\n*** BEST CONFIG: minW={best['min_weighted']:.1f} "
                  f"SL={best['sl_mult']:.1f} TP={best['tp_mult']:.1f} "
                  f"=> WR={best['win_rate']*100:.1f}% avgWR={best['avg_win_r']:.2f} "
                  f"trades={best['trades']} PF={best['profit_factor']:.2f}")

    return results


def main():
    args = sys.argv[1:]

    if args and args[0] == "--grid":
        pair = args[1].upper() if len(args) > 1 else "GBPUSD"
        grid_search(pair)
        return 0

    if args:
        pairs = [a.upper() for a in args]
    else:
        pairs = list(PAIR_PARAMS.keys())

    print("=" * 115)
    print("PRECISION STRATEGY V2 — 70% WR + 2.5R Target")
    print("Weighted 7-layer confluence | Aggressive filtering | Trailing stops")
    print(f"Threshold: min weighted score >= 5.0 / {MAX_WEIGHTED:.1f} max")
    print("=" * 115)
    print(
        f"{'Pair':10s} {'Team':12s} {'Trades':>6s} {'WR%':>6s} {'AvgR':>7s} "
        f"{'AvgWR':>6s} {'PF':>6s} {'Sharpe':>7s} {'MaxCL':>5s} "
        f"{'TP':>4s} {'SL':>4s} {'TIME':>5s} {'TRAIL':>6s} {'$/Tr':>8s}"
    )
    print("-" * 115)

    t0 = time.time()
    results = []
    for sym in pairs:
        try:
            r = run_backtest(sym, bars=5000, verbose=True)
            results.append(r)
        except Exception as e:
            print(f"[!] {sym:8s} ERROR: {e}")

    dt = time.time() - t0
    print("-" * 115)

    viable = [r for r in results if r.get("viable")]
    target_hit = [r for r in viable if r.get("target_70wr") and r.get("target_2_5r")]
    total_trades = sum(r.get("trades", 0) for r in results)
    total_wins = sum(r.get("wins", 0) for r in results)
    overall_wr = total_wins / total_trades if total_trades > 0 else 0

    print(f"\nTotal trades: {total_trades}  |  Overall WR: {overall_wr*100:.1f}%")
    print(f"Viable: {len(viable)}/{len(results)}  |  Target hit (70%WR+2.5R): {len(target_hit)}/{len(results)}")
    print(f"Time: {dt:.1f}s")

    if target_hit:
        print(f"\n*** TARGET HIT (70% WR + 2.5R): ***")
        for r in target_hit:
            print(f"  {r['symbol']:8s}: WR={r['win_rate']*100:.1f}% avgWinR={r['avg_win_r']:.2f} "
                  f"PF={r['profit_factor']:.2f} trades={r['trades']} ~${r['expected_per_trade_usd']:+.2f}/tr")

    if viable:
        print(f"\nVIABLE (positive expectancy):")
        for r in viable:
            print(f"  {r['symbol']:8s}: WR={r['win_rate']*100:.1f}% avgR={r['avg_r']:+.3f} "
                  f"PF={r['profit_factor']:.2f} trades={r['trades']}")

    non_viable = [r for r in results if not r.get("viable") and r.get("trades", 0) > 0]
    if non_viable:
        print(f"\nNON-VIABLE:")
        for r in non_viable:
            print(f"  {r['symbol']:8s}: WR={r['win_rate']*100:.1f}% avgR={r['avg_r']:+.3f} "
                  f"trades={r['trades']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
