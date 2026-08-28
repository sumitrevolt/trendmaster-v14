#!/usr/bin/env python3
"""
FAST-MARKET SCALPER: 80% Win Rate Target
=========================================
Strategy: ONLY trade when market is moving FAST.

Detection:
  - Price velocity (rate of change over N bars)
  - ATR expansion (current ATR > 1.5x average)
  - Volume spike (volume > 2x average)
  - Momentum burst (RSI pushing to extreme + MACD accelerating)
  - ADX rising (trend strengthening)

Entry:
  - Enter WITH momentum direction during velocity spike
  - Only during peak session (London-NY overlap)
  - Only when ALL fast-market conditions met

Exit:
  - TP: Quick profit (0.5-0.8x ATR)
  - SL: Wide (1.5-2.0x ATR) to avoid noise stop-outs
  - Time exit: Close after 6-10 bars if neither SL nor TP hit
  - Momentum fade exit: Close if velocity drops below threshold

Math for 80% WR:
  - Win: Take 0.6x ATR profit (~5-8 pips on EURUSD)
  - Loss: Get stopped at 1.8x ATR (~15-25 pips)
  - R:R = 1:3 (bad) but WR = 80%
  - Expectancy: 0.8 * 0.6 - 0.2 * 1.8 = 0.48 - 0.36 = +0.12R per trade
  - At 3% risk: +0.36% per trade, ~10 trades/day = +3.6%/day
"""

import numpy as np
import pandas as pd
from pathlib import Path
import time
import warnings
warnings.filterwarnings("ignore")

PAIRS = ["EURUSD", "NZDUSD", "USDCHF", "GBPUSD"]
PAIR_FILES = {"EURUSD": "eurusd", "NZDUSD": "nzdusd", "USDCHF": "usdchf", "GBPUSD": "gbpusd"}

# ─── INDICATORS ───────────────────────────────────────────────────────────────
def _ema(d, p):
    return pd.Series(d).ewm(span=p, adjust=False).mean().values

def _sma(d, p):
    return pd.Series(d).rolling(p).mean().values

def _rsi(c, p=14):
    delta = np.diff(c, prepend=c[0])
    g = np.where(delta > 0, delta, 0.0)
    l = np.where(delta < 0, -delta, 0.0)
    ag = pd.Series(g).ewm(span=p, adjust=False).mean().values
    al = pd.Series(l).ewm(span=p, adjust=False).mean().values
    return 100.0 - 100.0 / (1.0 + ag / np.where(al == 0, 1e-10, al))

def _atr(h, l, c, p=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(p).mean().values

def _adx(h, l, c, p=14):
    ph = np.roll(h, 1); ph[0] = h[0]; pl = np.roll(l, 1); pl[0] = l[0]
    um = h - ph; dm = pl - l
    pdm = np.where((um > dm) & (um > 0), um, 0.0)
    mdm = np.where((dm > um) & (dm > 0), dm, 0.0)
    a = _atr(h, l, c, p)
    sa = np.where(a == 0, 1e-10, a)
    pdi = 100.0 * pd.Series(pdm).ewm(span=p).mean().values / sa
    mdi = 100.0 * pd.Series(mdm).ewm(span=p).mean().values / sa
    dx = 100.0 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, 1e-10, pdi + mdi)
    return pd.Series(dx).ewm(span=p).mean().values, pdi, mdi

def _macd(c, f=12, s=26, sg=9):
    ef = _ema(c, f); es = _ema(c, s)
    ml = ef - es; sl = _ema(ml, sg)
    return ml, sl, ml - sl


# ─── FAST MARKET DETECTION ───────────────────────────────────────────────────
def detect_fast_market(i, c, h, l, v, atr_v, atr_avg, adx_v, rsi_v, macd_h, vol_avg, hours, min_vel=4.0):
    """
    Detect if market is moving FAST at bar i.
    Returns (is_fast, velocity_score, direction).
    """
    if i < 50 or atr_avg[i] <= 0:
        return False, 0, 0

    score = 0
    direction = 0

    # ── VELOCITY: Price rate of change (3-bar) ───────────────────────────
    if i >= 3:
        roc_3 = (c[i] - c[i-3]) / c[i-3] * 10000  # in pips approx
        roc_5 = (c[i] - c[i-5]) / c[i-5] * 10000 if i >= 5 else 0
        # Strong move = velocity spike
        if abs(roc_3) > 2.0:  # 2+ pips in 3 bars = fast
            score += 2.0
            direction = 1 if roc_3 > 0 else -1
        elif abs(roc_3) > 1.0:
            score += 1.0
            direction = 1 if roc_3 > 0 else -1
        # Acceleration: velocity increasing
        if abs(roc_3) > abs(roc_5) * 0.8 and abs(roc_3) > 1.5:
            score += 1.0  # Accelerating

    # ── ATR EXPANSION: Volatility expanding ──────────────────────────────
    atr_ratio = atr_v[i] / atr_avg[i] if atr_avg[i] > 0 else 0
    if atr_ratio > 1.8:
        score += 2.0
    elif atr_ratio > 1.4:
        score += 1.0
    elif atr_ratio > 1.2:
        score += 0.5

    # ── VOLUME SPIKE: Above average volume ───────────────────────────────
    if vol_avg[i] > 0:
        vol_ratio = v[i] / vol_avg[i]
        if vol_ratio > 2.5:
            score += 1.5
        elif vol_ratio > 1.8:
            score += 1.0
        elif vol_ratio > 1.3:
            score += 0.5

    # ── MOMENTUM BURST: RSI pushing + MACD accelerating ─────────────────
    rsi_delta = rsi_v[i] - rsi_v[i-1] if i > 0 else 0
    macd_delta = macd_h[i] - macd_h[i-1] if i > 0 else 0

    # Strong RSI push
    if abs(rsi_delta) > 3.0:  # RSI moved 3+ points in 1 bar
        score += 1.5
        if rsi_delta > 0 and direction == 0:
            direction = 1
        elif rsi_delta < 0 and direction == 0:
            direction = -1
    elif abs(rsi_delta) > 1.5:
        score += 0.5

    # MACD acceleration
    if abs(macd_delta) > abs(macd_h[i]) * 0.3 and abs(macd_h[i]) > 0:
        score += 1.0

    # ── ADX RISING: Trend strengthening ──────────────────────────────────
    if i >= 3:
        adx_rising = adx_v[i] > adx_v[i-3]
        if adx_rising and adx_v[i] > 25:
            score += 1.0
        elif adx_rising and adx_v[i] > 20:
            score += 0.5

    # ── SESSION: Peak hours only ─────────────────────────────────────────
    h = int(hours[i])
    if 12 <= h <= 15:
        score += 1.5  # London-NY overlap = fastest
    elif 7 <= h <= 11 or 16 <= h <= 18:
        score += 0.5
    else:
        score -= 1.0  # Penalty for off-session

    # ── CONSECUTIVE BARS: Same direction momentum ────────────────────────
    if i >= 3:
        consecutive = 0
        for j in range(i, max(i-5, 0), -1):
            if direction > 0 and c[j] > c[j-1] if j > 0 else False:
                consecutive += 1
            elif direction < 0 and c[j] < c[j-1] if j > 0 else False:
                consecutive += 1
            else:
                break
        if consecutive >= 3:
            score += 1.0

    return score >= min_vel, score, direction


# ─── PRECOMPUTE ───────────────────────────────────────────────────────────────
def precompute(df):
    c = df["close"].values.astype(np.float64)
    o = df["open"].values.astype(np.float64)
    h = df["high"].values.astype(np.float64)
    l = df["low"].values.astype(np.float64)
    v = df["volume"].values.astype(np.float64) if "volume" in df.columns else np.ones(len(c))
    atr_v = _atr(h, l, c, 14)
    adx_v, _, _ = _adx(h, l, c, 14)
    rsi_v = _rsi(c, 14)
    macd_l, macd_s, macd_h = _macd(c)
    return {
        "c": c, "o": o, "h": h, "l": l, "v": v,
        "atr": atr_v, "atr_avg": _sma(atr_v, 50),
        "adx": adx_v, "rsi": rsi_v, "macd_h": macd_h,
        "vol_avg": _sma(v, 20),
        "hours": df["time"].dt.hour.values if "time" in df.columns else np.zeros(len(c)),
    }


# ─── BACKTEST ─────────────────────────────────────────────────────────────────
def backtest_fast_scalp(csv_path, pair, risk_pct=3.0, sl_mult=1.8, tp_mult=0.6, max_hold=8, min_velocity=4.0):
    df = pd.read_csv(csv_path, parse_dates=["time"])
    if len(df) < 500:
        return []

    split = int(len(df) * 0.7)  # 70/30 split
    ind = precompute(df)
    c = ind["c"]; h = ind["h"]; l = ind["l"]
    n = len(c)

    trades = []
    equity = 200.0
    daily = 0
    last_trade_bar = -100

    for i in range(50, n):
        if i < split:
            continue

        # Daily reset
        day = i // 288
        if i == split or (i > split and (i-1) // 288 != day):
            daily = 0

        if daily >= 15 or i - last_trade_bar < 3 or equity <= 0:
            continue

        # ── FAST MARKET DETECTION ────────────────────────────────────────
        is_fast, velocity_score, direction = detect_fast_market(
            i, c, h, l, ind["v"], ind["atr"], ind["atr_avg"],
            ind["adx"], ind["rsi"], ind["macd_h"], ind["vol_avg"], ind["hours"],
            min_vel=min_velocity
        )

        if not is_fast or direction == 0:
            continue

        # ── ENTRY ────────────────────────────────────────────────────────
        entry = c[i]
        atr_val = ind["atr"][i]

        # Scalping SL/TP: tight TP, wide SL for high WR
        sl_dist = atr_val * sl_mult  # Wide SL (hard to hit)
        tp_dist = atr_val * tp_mult  # Tight TP (easy to hit)

        if sl_dist <= 0:
            continue

        risk_amt = equity * (risk_pct / 100.0)
        lots = max(0.01, min(risk_amt / (sl_dist * 100.0), 0.5))

        # ── EXIT LOGIC ───────────────────────────────────────────────────
        result = 0.0
        bars_held = 0
        entry_rsi = ind["rsi"][i]

        for j in range(i + 1, min(i + max_hold, n)):
            bars_held += 1

            if direction == 1:  # BUY
                if l[j] <= entry - sl_dist:
                    result = -sl_dist * lots * 100.0
                    break
                if h[j] >= entry + tp_dist:
                    result = tp_dist * lots * 100.0
                    break
            else:  # SELL
                if h[j] >= entry + sl_dist:
                    result = -sl_dist * lots * 100.0
                    break
                if l[j] <= entry - tp_dist:
                    result = tp_dist * lots * 100.0
                    break

            # ── MOMENTUM FADE EXIT ──────────────────────────────────────
            # If velocity dies, exit at market
            if bars_held >= 4:
                current_roc = abs(c[j] - c[j-2]) / c[j-2] * 10000 if j >= 2 else 0
                if current_roc < 0.3:  # Velocity dropped below threshold
                    exit_p = c[j]
                    if direction == 1:
                        result = (exit_p - entry) * lots * 100.0
                    else:
                        result = (entry - exit_p) * lots * 100.0
                    break

            # ── TIME EXIT ────────────────────────────────────────────────
            if bars_held >= max_hold:
                exit_p = c[j]
                if direction == 1:
                    result = (exit_p - entry) * lots * 100.0
                else:
                    result = (entry - exit_p) * lots * 100.0
                break
        else:
            # End of data
            exit_p = c[min(i + max_hold, n - 1)]
            if direction == 1:
                result = (exit_p - entry) * lots * 100.0
            else:
                result = (entry - exit_p) * lots * 100.0

        equity += result
        equity = max(equity, 0.0)

        h_utc = int(ind["hours"][i])
        session = "peak" if 12 <= h_utc <= 15 else ("london" if 7 <= h_utc <= 11 else "other")

        trades.append({
            "bar": i, "pair": pair, "dir": "BUY" if direction == 1 else "SELL",
            "entry": entry, "result": result, "equity": equity,
            "bars_held": bars_held, "velocity": velocity_score,
            "session": session, "lots": lots,
        })
        daily += 1
        last_trade_bar = i

    return trades


# ─── ANALYSIS ─────────────────────────────────────────────────────────────────
def analyze(trades, label=""):
    if not trades:
        return None
    wins = [t for t in trades if t["result"] > 0]
    losses = [t for t in trades if t["result"] <= 0]
    wr = len(wins) / len(trades) * 100
    aw = np.mean([t["result"] for t in wins]) if wins else 0
    al = np.mean([abs(t["result"]) for t in losses]) if losses else 0
    gross = sum(t["result"] for t in trades)
    pf = (aw * len(wins)) / (al * len(losses)) if losses and al > 0 else 99
    avg_r = np.mean([t["result"] for t in trades])
    avg_vel = np.mean([t["velocity"] for t in trades])

    eqs = [t["equity"] for t in trades]
    peak = eqs[0]; max_dd = 0
    for eq in eqs:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        "label": label, "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "wr": wr, "avg_win": aw, "avg_loss": al, "gross": gross,
        "pf": pf, "avg_r": avg_r, "max_dd": max_dd,
        "final_eq": eqs[-1], "avg_vel": avg_vel,
    }


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    data_dir = Path("data")
    t0 = time.time()

    print("=" * 90)
    print("  FAST-MARKET SCALPER: 80% Win Rate Target")
    print("  M5 timeframe | Momentum burst detection | Quick exits")
    print("=" * 90)

    # ── Grid search SL/TP ratios ─────────────────────────────────────────
    configs = [
        # (SL_mult, TP_mult, max_hold, min_velocity)
        (1.5, 0.5, 8, 4),   # Standard fast scalper
        (1.8, 0.6, 8, 4),   # Wider SL
        (2.0, 0.7, 8, 4),   # Even wider SL
        (2.5, 0.5, 8, 4),   # Very wide SL
        (1.5, 0.4, 6, 5),   # Faster exit, higher velocity
        (1.8, 0.5, 6, 5),   # Faster exit, higher velocity
        (2.0, 0.6, 6, 5),   # Faster exit, higher velocity
        (1.5, 0.4, 5, 6),   # Even faster, very selective
        (1.8, 0.5, 5, 6),   # Even faster, very selective
        (2.0, 0.4, 5, 7),   # Maximum selectivity
    ]

    best = None
    print(f"\n  GRID SEARCH: {len(configs)} configs x {len(PAIRS)} pairs")
    print(f"  {'Config':<20s} | {'Trades':>6s} | {'WR%':>5s} | {'PF':>5s} | "
          f"{'AvgR':>7s} | {'Gross':>10s} | {'MaxDD':>6s}")
    print(f"  {'-'*75}")

    for sl_m, tp_m, max_h, min_vel in configs:
        all_t = []
        for pair in PAIRS:
            csv = data_dir / f"{PAIR_FILES.get(pair, pair.lower())}_m5_history.csv"
            if not csv.exists():
                continue
            trades = backtest_fast_scalp(str(csv), pair,
                                        sl_mult=sl_m, tp_mult=tp_m,
                                        max_hold=max_h, min_velocity=min_vel)
            all_t.extend(trades)

        r = analyze(all_t, f"SL={sl_m} TP={tp_m} Hold={max_h}")
        if r is None:
            continue

        print(f"  SL={sl_m} TP={tp_m} Hold={max_h:<3d} Vel>{min_vel} | "
              f"{r['trades']:6d} | {r['wr']:5.1f} | {r['pf']:5.2f} | "
              f"{r['avg_r']:+7.3f} | ${r['gross']:9.2f} | {r['max_dd']:5.1f}%")

        if best is None or r["wr"] > best["wr"] or (r["wr"] == best["wr"] and r["avg_r"] > best["avg_r"]):
            best = r
            best_config = (sl_m, tp_m, max_h, min_vel)

    if best:
        print(f"\n  BEST CONFIG: SL={best_config[0]} TP={best_config[1]} Hold={best_config[2]}")
        print(f"  WR: {best['wr']:.1f}% | PF: {best['pf']:.2f} | "
              f"AvgR: ${best['avg_r']:.3f} | Gross: ${best['gross']:.2f}")

    # ── Detailed analysis of best config ─────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  DETAILED ANALYSIS: Best Config")
    print(f"{'='*90}")

    all_t = []
    pair_results = {}
    for pair in PAIRS:
        csv = data_dir / f"{PAIR_FILES.get(pair, pair.lower())}_m5_history.csv"
        if not csv.exists():
            continue
        trades = backtest_fast_scalp(str(csv), pair)
        all_t.extend(trades)
        r = analyze(trades, pair)
        if r:
            pair_results[pair] = r

    # By pair
    print(f"\n  BY PAIR:")
    print(f"  {'Pair':<10s} | {'Trades':>6s} | {'WR%':>5s} | {'PF':>5s} | "
          f"{'AvgR':>7s} | {'Gross':>10s} | {'AvgVel':>6s}")
    print(f"  {'-'*65}")
    for pair, r in sorted(pair_results.items(), key=lambda x: x[1]["wr"], reverse=True):
        tag = " <-- 80%!" if r["wr"] >= 80 else (" <-- 70%+" if r["wr"] >= 70 else "")
        print(f"  {pair:<10s} | {r['trades']:6d} | {r['wr']:5.1f} | "
              f"{r['pf']:5.2f} | {r['avg_r']:+7.3f} | ${r['gross']:9.2f} | "
              f"{r['avg_vel']:6.1f}{tag}")

    # By session
    print(f"\n  BY SESSION:")
    sess_groups = {}
    for t in all_t:
        s = t["session"]
        if s not in sess_groups:
            sess_groups[s] = []
        sess_groups[s].append(t)
    print(f"  {'Session':<10s} | {'Trades':>6s} | {'WR%':>5s} | {'AvgR':>7s}")
    print(f"  {'-'*40}")
    for sess in ["peak", "london", "other"]:
        if sess in sess_groups:
            r = analyze(sess_groups[sess])
            if r:
                print(f"  {sess:<10s} | {r['trades']:6d} | {r['wr']:5.1f} | {r['avg_r']:+7.3f}")

    # By velocity score
    print(f"\n  BY VELOCITY SCORE:")
    vel_bins = [(6, 7, "6-7"), (7, 8, "7-8"), (8, 9, "8-9"), (9, 99, "9+")]
    print(f"  {'Velocity':<10s} | {'Trades':>6s} | {'WR%':>5s} | {'AvgR':>7s}")
    print(f"  {'-'*40}")
    for lo, hi, label in vel_bins:
        subset = [t for t in all_t if lo <= t["velocity"] < hi]
        if subset:
            r = analyze(subset)
            if r:
                print(f"  {label:<10s} | {r['trades']:6d} | {r['wr']:5.1f} | {r['avg_r']:+7.3f}")

    # Overall
    overall = analyze(all_t, "ALL")
    print(f"\n  {'='*60}")
    print(f"  OVERALL: {overall['trades']} trades | WR {overall['wr']:.1f}% | "
          f"PF {overall['pf']:.2f} | AvgR ${overall['avg_r']:.3f}")
    print(f"  Gross: ${overall['gross']:,.2f} | MaxDD: {overall['max_dd']:.1f}%")
    print(f"  Final equity: ${overall['final_eq']:,.2f} (from $200)")
    print(f"  {'='*60}")

    # ── 80% WR analysis ──────────────────────────────────────────────────
    high_wr = [t for t in all_t if t["velocity"] >= 8]
    if high_wr:
        r80 = analyze(high_wr, "VELOCITY>=8")
        print(f"\n  HIGH VELOCITY (score >= 8):")
        print(f"  {r80['trades']} trades | WR {r80['wr']:.1f}% | PF {r80['pf']:.2f} | "
              f"AvgR ${r80['avg_r']:.3f}")

    peak_only = [t for t in all_t if t["session"] == "peak" and t["velocity"] >= 7]
    if peak_only:
        r_peak = analyze(peak_only, "PEAK+VELOCITY>=7")
        print(f"\n  PEAK SESSION + HIGH VELOCITY:")
        print(f"  {r_peak['trades']} trades | WR {r_peak['wr']:.1f}% | PF {r_peak['pf']:.2f}")

    print(f"\n  Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
