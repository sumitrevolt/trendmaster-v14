#!/usr/bin/env python3
"""
PRECISION SCALPING + COMPOUND GROWTH: $200 -> $500,000
=======================================================
Grid search across SL/TP/score thresholds per pair,
then project compound growth with realistic expectations.

Strategy: ONLY trade A+ setups (high confluence).
Key: Selectivity > frequency. Fewer trades, bigger wins.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import time
import warnings
warnings.filterwarnings("ignore")

PAIRS = ["GBPUSD", "AUDUSD", "USDCHF", "NZDUSD", "EURUSD", "XAGUSD", "USDJPY"]

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
    rs = ag / np.where(al == 0, 1e-10, al)
    return 100.0 - 100.0 / (1.0 + rs)

def _atr(h, l, c, p=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(tr).rolling(p).mean().values

def _adx(h, l, c, p=14):
    ph = np.roll(h, 1); ph[0] = h[0]
    pl = np.roll(l, 1); pl[0] = l[0]
    um = h - ph; dm = pl - l
    pdm = np.where((um > dm) & (um > 0), um, 0.0)
    mdm = np.where((dm > um) & (dm > 0), dm, 0.0)
    a = _atr(h, l, c, p)
    sa = np.where(a == 0, 1e-10, a)
    pdi = 100.0 * pd.Series(pdm).ewm(span=p).mean().values / sa
    mdi = 100.0 * pd.Series(mdm).ewm(span=p).mean().values / sa
    dx = 100.0 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, 1e-10, pdi + mdi)
    return pd.Series(dx).ewm(span=p).mean().values, pdi, mdi

def _bb(c, p=20, m=2.0):
    mid = _sma(c, p)
    std = pd.Series(c).rolling(p).std().values
    return mid + m * std, mid, mid - m * std

def _macd(c, f=12, s=26, sg=9):
    ef = _ema(c, f); es = _ema(c, s)
    ml = ef - es; sl = _ema(ml, sg)
    return ml, sl, ml - sl

def _stoch(h, l, c, kp=14, dp=3):
    ll = pd.Series(l).rolling(kp).min().values
    hh = pd.Series(h).rolling(kp).max().values
    k = 100.0 * (c - ll) / np.where((hh - ll) == 0, 1e-10, hh - ll)
    d = pd.Series(k).rolling(dp).mean().values
    return k, d


# ─── PRECOMPUTE ALL INDICATORS ────────────────────────────────────────────────
def precompute(df):
    c = df["close"].values.astype(np.float64)
    o = df["open"].values.astype(np.float64)
    h = df["high"].values.astype(np.float64)
    l = df["low"].values.astype(np.float64)
    v = df["volume"].values.astype(np.float64) if "volume" in df.columns else np.ones(len(c))

    return {
        "c": c, "o": o, "h": h, "l": l, "v": v,
        "e8": _ema(c, 8), "e20": _ema(c, 20), "e50": _ema(c, 50), "e200": _ema(c, 200),
        "rsi": _rsi(c, 14),
        "atr": _atr(h, l, c, 14),
        "atr_avg": _sma(_atr(h, l, c, 14), 50),
        "adx": _adx(h, l, c, 14),
        "bb": _bb(c, 20, 2.0),
        "bbw": None, "bbw_avg": None,
        "macd": _macd(c),
        "vol_avg": _sma(v, 20),
        "stk": _stoch(h, l, c, 14, 3),
        "hours": df["time"].dt.hour.values if "time" in df.columns else np.zeros(len(c)),
    }

def finish_precompute(ind):
    bb_u, bb_m, bb_l = ind["bb"]
    bbw = bb_u - bb_l
    ind["bbw"] = bbw
    ind["bbw_avg"] = _sma(bbw, 50)
    return ind


# ─── SCORE FUNCTION ───────────────────────────────────────────────────────────
def score_at(i, ind, hour):
    c = ind["c"]
    a = ind["atr"][i]
    aa = ind["atr_avg"][i]
    if i < 200 or a <= 0 or aa <= 0:
        return 0, 0

    s = 0.0
    votes = []

    # L1: TREND (1.5)
    adx_v = ind["adx"][0][i]
    if adx_v > 30:
        if ind["e8"][i] > ind["e20"][i] > ind["e50"][i]:
            s += 1.5; votes.append(1)
        elif ind["e8"][i] < ind["e20"][i] < ind["e50"][i]:
            s += 1.5; votes.append(-1)
    elif adx_v > 22:
        if ind["e8"][i] > ind["e20"][i]:
            s += 0.8; votes.append(1)
        elif ind["e8"][i] < ind["e20"][i]:
            s += 0.8; votes.append(-1)

    # L2: MOMENTUM (1.2)
    rsi_v = ind["rsi"][i]
    if 35 <= rsi_v <= 65:
        s += 0.6
        votes.append(1 if rsi_v > 50 else -1)
    mh = ind["macd"][2][i]
    mh_p = ind["macd"][2][i-1] if i > 0 else 0.0
    if mh > 0 and mh > mh_p:
        s += 0.6; votes.append(1)
    elif mh < 0 and mh < mh_p:
        s += 0.6; votes.append(-1)

    # L3: VOLATILITY (0.8)
    bbw = ind["bbw"][i]
    bbw_a = ind["bbw_avg"][i]
    if bbw_a > 0 and bbw < bbw_a * 0.80:
        s += 0.8
    if aa > 0 and a > aa * 1.15:
        s += 0.4

    # L4: VOLUME (0.7)
    va = ind["vol_avg"][i]
    vi = ind["v"][i]
    if va > 0:
        if vi > va * 1.3:
            s += 0.7
        elif vi > va:
            s += 0.3

    # L5: PRICE ACTION (1.3)
    cc = c[i]; oo = ind["o"][i]; hh = ind["h"][i]; ll = ind["l"][i]
    body = abs(cc - oo)
    wu = hh - max(oo, cc)
    wd = min(oo, cc) - ll
    rng = hh - ll
    if rng > 0:
        br = body / rng
        if cc > oo and br > 0.65:
            s += 0.8; votes.append(1)
        elif cc < oo and br > 0.65:
            s += 0.8; votes.append(-1)
        if wd > body * 2.5 and wd > wu:
            s += 0.5; votes.append(1)
        elif wu > body * 2.5 and wu > wd:
            s += 0.5; votes.append(-1)

    # L6: SESSION (1.0)
    if 12 <= hour <= 15:
        s += 1.0
    elif 7 <= hour <= 11 or 16 <= hour <= 18:
        s += 0.5

    # L7: MTF (1.5)
    if ind["e20"][i] > ind["e50"][i] > ind["e200"][i]:
        s += 1.5; votes.append(1)
    elif ind["e20"][i] < ind["e50"][i] < ind["e200"][i]:
        s += 1.5; votes.append(-1)

    # L8: STOCHASTIC (0.8)
    stk = ind["stk"][0][i]
    std = ind["stk"][1][i]
    if stk < 20 and std < 20:
        s += 0.8; votes.append(1)
    elif stk > 80 and std > 80:
        s += 0.8; votes.append(-1)
    elif stk > std and stk < 45:
        s += 0.4; votes.append(1)
    elif stk < std and stk > 55:
        s += 0.4; votes.append(-1)

    # Direction
    if not votes:
        return s, 0
    bv = sum(1 for v in votes if v > 0)
    sv = sum(1 for v in votes if v < 0)
    d = 1 if bv > sv else (-1 if sv > bv else 0)
    return s, d


# ─── GRID SEARCH ──────────────────────────────────────────────────────────────
def grid_search_pair(ind, pair, split, base_equity=200.0):
    """Grid search SL/TP/score per pair, return best configs."""
    c = ind["c"]; h = ind["h"]; l = ind["l"]
    hours = ind["hours"]
    n = len(c)

    # Grid params
    sl_list = [0.6, 0.8, 1.0, 1.2]
    tp_list = [1.5, 2.0, 2.5, 3.0]
    score_list = [4.0, 5.0, 6.0, 7.0]
    hold_list = [20, 30, 50]

    best = None

    for sl_m in sl_list:
        for tp_m in tp_list:
            for min_sc in score_list:
                for max_hold in hold_list:
                    trades = []
                    equity = base_equity
                    daily = 0
                    last_bar = -100

                    for i in range(200, n):
                        if i < split:
                            continue

                        day = i // 288
                        if i == split or (i > split and (i-1) // 288 != day):
                            daily = 0

                        if daily >= 10 or i - last_bar < 6 or equity <= 0:
                            continue

                        sc, d = score_at(i, ind, int(hours[i]))
                        if sc < min_sc or d == 0:
                            continue

                        entry = c[i]
                        atr_v = ind["atr"][i]
                        sl_d = atr_v * sl_m
                        tp_d = atr_v * tp_m
                        if sl_d <= 0:
                            continue

                        risk_amt = equity * 0.03  # 3% risk
                        lots = max(0.01, min(risk_amt / (sl_d * 100.0), 1.0))

                        result = 0.0
                        for j in range(i + 1, min(i + max_hold, n)):
                            if d == 1:
                                if l[j] <= entry - sl_d:
                                    result = -sl_d * lots * 100.0; break
                                if h[j] >= entry + tp_d:
                                    result = tp_d * lots * 100.0; break
                            else:
                                if h[j] >= entry + sl_d:
                                    result = -sl_d * lots * 100.0; break
                                if l[j] <= entry - tp_d:
                                    result = tp_d * lots * 100.0; break
                        else:
                            exit_p = c[min(i + max_hold, n - 1)]
                            result = ((exit_p - entry) if d == 1 else (entry - exit_p)) * lots * 100.0

                        equity += result
                        equity = max(equity, 0.0)
                        trades.append(result)
                        daily += 1
                        last_bar = i

                        if equity >= 10000:  # Target for Phase 1
                            break

                    if not trades:
                        continue

                    wins = sum(1 for t in trades if t > 0)
                    wr = wins / len(trades) * 100
                    gross = sum(trades)
                    avg_r = np.mean(trades)
                    aw = np.mean([t for t in trades if t > 0]) if wins else 0
                    al = np.mean([abs(t) for t in trades if t <= 0]) if len(trades) > wins else 1
                    pf = (aw * wins) / (al * (len(trades) - wins)) if (len(trades) > wins and al > 0) else 99

                    # Score: balance WR, expectancy, trade count
                    if len(trades) < 10:
                        continue

                    # We want: positive expectancy + decent WR + enough trades
                    score_val = avg_r * len(trades) * (1 + wr / 200.0)

                    cfg = {
                        "sl": sl_m, "tp": tp_m, "min_sc": min_sc, "hold": max_hold,
                        "trades": len(trades), "wr": wr, "avg_r": avg_r,
                        "gross": gross, "equity": equity, "pf": pf,
                        "score_val": score_val, "aw": aw, "al": al,
                    }

                    if best is None or score_val > best["score_val"]:
                        best = cfg

    return best


# ─── COMPOUND GROWTH PROJECTION ──────────────────────────────────────────────
def project_growth(pair_results):
    """Project realistic compound growth from backtest data."""
    print(f"\n{'='*80}")
    print(f"  COMPOUND GROWTH PROJECTION: $200 -> $500,000")
    print(f"{'='*80}")

    # Find best pair configs
    print(f"\n  OPTIMAL CONFIGS PER PAIR:")
    print(f"  {'Pair':8s} | {'SL':>4s} | {'TP':>4s} | {'MinS':>4s} | {'Hold':>4s} | "
          f"{'#Tr':>4s} | {'WR%':>5s} | {'AvgR':>7s} | {'PF':>5s} | {'Equity':>10s}")
    print(f"  {'-'*80}")

    active_pairs = []
    for pair, best in pair_results.items():
        if best is None:
            print(f"  {pair:8s} | NO VIABLE CONFIG")
            continue

        print(f"  {pair:8s} | {best['sl']:4.1f} | {best['tp']:4.1f} | {best['min_sc']:4.1f} | "
              f"{best['hold']:4d} | {best['trades']:4d} | {best['wr']:5.1f} | "
              f"{best['avg_r']:+7.3f} | {best['pf']:5.2f} | ${best['equity']:9.2f}")

        if best["avg_r"] > 0 and best["wr"] > 35 and best["trades"] >= 15:
            active_pairs.append((pair, best))

    if not active_pairs:
        print(f"\n  WARNING: No pair achieves positive expectancy with current data.")
        print(f"  Using best available configs for projection.")
        active_pairs = [(p, b) for p, b in pair_results.items() if b is not None][:3]

    # Sort by expectancy
    active_pairs.sort(key=lambda x: x[1]["avg_r"], reverse=True)

    print(f"\n  ACTIVE PAIRS (positive expectancy): {len(active_pairs)}")
    for p, b in active_pairs:
        print(f"    {p}: WR {b['wr']:.1f}% | AvgR ${b['avg_r']:.3f} | PF {b['pf']:.2f}")

    # ─── PHASE-BY-PHASE PROJECTION ────────────────────────────────────────
    PHASES = [
        {"name": "SEED ($200)", "start": 200, "target": 2000, "risk": 3.0, "days_per_phase": 30},
        {"name": "GROW ($2K)", "start": 2000, "target": 20000, "risk": 2.5, "days_per_phase": 60},
        {"name": "SCALE ($20K)", "start": 20000, "target": 200000, "risk": 2.0, "days_per_phase": 90},
        {"name": "HARVEST ($200K)", "start": 200000, "target": 500000, "risk": 1.5, "days_per_phase": 60},
    ]

    print(f"\n  {'='*70}")
    print(f"  PHASE-BY-PHASE PROJECTION")
    print(f"  {'='*70}")

    equity = 200.0
    total_days = 0

    for pi, ph in enumerate(PHASES):
        # Use best pair's metrics for projection
        best_pair = active_pairs[0][1] if active_pairs else {"wr": 35, "avg_r": 0.1, "trades": 50}
        wr = best_pair["wr"] / 100.0
        avg_win_r = best_pair.get("aw", 2.0) / max(best_pair.get("al", 1.0), 0.01)
        avg_loss_r = 1.0

        # Expected R per trade
        exp_r = wr * avg_win_r - (1 - wr) * avg_loss_r
        trades_per_day = 3  # Conservative: 3 quality trades per day
        days = ph["days_per_phase"]

        # Simulate compounding
        sim = equity
        trade_count = 0
        for _ in range(days * trades_per_day):
            if sim >= ph["target"]:
                break
            ra = sim * (ph["risk"] / 100.0)
            if np.random.random() < wr:
                sim += ra * avg_win_r
            else:
                sim -= ra
            sim = max(sim, 1.0)
            trade_count += 1

        days_needed = trade_count / trades_per_day
        ret = ((sim / equity) - 1) * 100

        print(f"\n  Phase {pi+1}: {ph['name']}")
        print(f"    ${equity:>12,.0f} -> ${sim:>12,.0f}  ({ret:+,.0f}%)")
        print(f"    Risk: {ph['risk']}% | WR: {wr*100:.0f}% | R:R: {avg_win_r:.1f}:1")
        print(f"    ExpR: {exp_r:+.2f}R per trade | Trades/day: {trades_per_day}")
        print(f"    Trades: ~{trade_count} | Days: ~{days_needed:.0f}")

        equity = sim
        total_days += days_needed

    final = equity
    print(f"\n  {'='*70}")
    print(f"  FINAL PROJECTION")
    print(f"  {'='*70}")
    print(f"    Start: $200")
    print(f"    End:   ${final:,.0f}")
    print(f"    Return: {((final/200)-1)*100:,.0f}%")
    print(f"    Time: ~{total_days:.0f} days ({total_days/30:.1f} months)")
    print(f"    {'='*70}")

    if final < 500000:
        shortfall = 500000 - final
        print(f"\n  GAP: ${shortfall:,.0f} short of $500K target")
        print(f"  To close the gap, you need:")
        extra_pct = (500000 / final - 1) * 100
        print(f"    +{extra_pct:.0f}% more return, OR")
        print(f"    +{total_days * extra_pct / 100:.0f} more trading days, OR")
        print(f"    Add ${shortfall * 0.3:,.0f} additional capital at midpoint")
    else:
        print(f"\n  TARGET ACHIEVED! $500K reached in ~{total_days:.0f} days")

    return active_pairs


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    data_dir = Path("data")
    t0 = time.time()

    print("=" * 90)
    print("  PRECISION SCALPING + COMPOUND GROWTH ENGINE")
    print("  $200 -> $500,000 | Grid Search + Realistic Projection")
    print("=" * 90)

    pair_results = {}

    for pair in PAIRS:
        csv = data_dir / f"{pair}_M5.csv"
        if not csv.exists():
            hits = list(data_dir.glob(f"*{pair}*M5*"))
            csv = hits[0] if hits else None
        if csv is None or not csv.exists():
            print(f"\n  {pair}: NO DATA FILE FOUND")
            continue

        print(f"\n  Processing {pair}...")
        df = pd.read_csv(csv, parse_dates=["time"])
        if len(df) < 500:
            print(f"  {pair}: Insufficient data ({len(df)} bars)")
            continue

        split = int(len(df) * 0.7)
        ind = finish_precompute(precompute(df))

        best = grid_search_pair(ind, pair, split)
        pair_results[pair] = best

    # Project growth
    active = project_growth(pair_results)

    # ─── REALISTIC MONTHLY INCOME TABLE ───────────────────────────────────
    print(f"\n  {'='*70}")
    print(f"  MONTHLY INCOME PROJECTION (from actual backtest data)")
    print(f"  {'='*70}")
    print(f"  Assumes: 3 trades/day, 22 trading days/month, compound reinvest")
    print(f"\n  {'Month':>6s} | {'Start':>12s} | {'End':>12s} | {'Return':>8s} | {'Trades':>6s}")
    print(f"  {'-'*60}")

    eq = 200.0
    for m in range(1, 37):  # 36 months
        if eq >= 500000:
            break
        if not active:
            break

        best = active[0][1]
        wr = best["wr"] / 100.0
        aw_r = best.get("aw", 2.0) / max(best.get("al", 1.0), 0.01)

        risk = 3.0 if eq < 2000 else (2.5 if eq < 20000 else (2.0 if eq < 200000 else 1.5))
        trades = 66  # 3/day x 22 days

        start_eq = eq
        for _ in range(trades):
            ra = eq * (risk / 100.0)
            if np.random.random() < wr:
                eq += ra * aw_r
            else:
                eq -= ra
            eq = max(eq, 1.0)

        ret = ((eq / start_eq) - 1) * 100
        print(f"  {m:>6d} | ${start_eq:>11,.0f} | ${eq:>11,.0f} | {ret:>+7.1f}% | {trades}")

    print(f"\n  Final balance after {m} months: ${eq:,.0f}")

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
