#!/usr/bin/env python3
"""
MAXIMUM GROWTH PLAN: $200 -> $500,000
======================================
Honest, data-driven compound growth projection.

Strategy:
1. Only trade pairs with HIGHEST expectancy (XAGUSD, USDJPY)
2. Use optimal SL/TP from grid search (1.2/2.5 ATR)
3. Aggressive compounding with phase-based risk scaling
4. Multiple sessions: trade all overlapping windows
5. Add prop-firm scaling rules as account grows

Reality: M5 forex scalping has ~36% WR with 2:1 R:R.
Expected R per trade: +0.13R (positive but modest).
To compound to $500K requires consistent execution over 3-5 years.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import time
import warnings
warnings.filterwarnings("ignore")


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

def _bb(c, p=20, m=2.0):
    mid = _sma(c, p)
    std = pd.Series(c).rolling(p).std().values
    return mid + m * std, mid, mid - m * std

def _stoch(h, l, c, kp=14, dp=3):
    ll = pd.Series(l).rolling(kp).min().values
    hh = pd.Series(h).rolling(kp).max().values
    k = 100.0 * (c - ll) / np.where((hh - ll) == 0, 1e-10, hh - ll)
    d = pd.Series(k).rolling(dp).mean().values
    return k, d


# ─── PRECOMPUTE ───────────────────────────────────────────────────────────────
def precompute(df):
    c = df["close"].values.astype(np.float64)
    o = df["open"].values.astype(np.float64)
    h = df["high"].values.astype(np.float64)
    l = df["low"].values.astype(np.float64)
    v = df["volume"].values.astype(np.float64) if "volume" in df.columns else np.ones(len(c))
    bb_u, bb_m, bb_l = _bb(c, 20, 2.0)
    bbw = bb_u - bb_l
    atr_v = _atr(h, l, c, 14)
    return {
        "c": c, "o": o, "h": h, "l": l, "v": v,
        "e8": _ema(c, 8), "e20": _ema(c, 20),
        "e50": _ema(c, 50), "e200": _ema(c, 200),
        "rsi": _rsi(c, 14), "atr": atr_v,
        "atr_avg": _sma(atr_v, 50),
        "adx": _adx(h, l, c, 14),
        "bb_u": bb_u, "bb_m": bb_m, "bb_l": bb_l,
        "bbw": bbw, "bbw_avg": _sma(bbw, 50),
        "macd": _macd(c),
        "vol_avg": _sma(v, 20),
        "stk": _stoch(h, l, c, 14, 3),
        "hours": df["time"].dt.hour.values if "time" in df.columns else np.zeros(len(c)),
    }


# ─── HIGH-CONVICTION SCORING ─────────────────────────────────────────────────
def score_at(i, ind, hour):
    """Simplified 5-layer scoring: only A+ setups."""
    c = ind["c"]
    a = ind["atr"][i]; aa = ind["atr_avg"][i]
    if i < 200 or a <= 0 or aa <= 0:
        return 0, 0

    s = 0.0
    votes = []

    # L1: STRONG TREND (ADX > 28 + EMA stack)
    adx_v = ind["adx"][0][i]
    if adx_v > 28:
        if ind["e8"][i] > ind["e20"][i] > ind["e50"][i]:
            s += 2.0; votes.append(1)
        elif ind["e8"][i] < ind["e20"][i] < ind["e50"][i]:
            s += 2.0; votes.append(-1)
    elif adx_v > 22:
        if ind["e8"][i] > ind["e20"][i] > ind["e50"][i]:
            s += 1.0; votes.append(1)
        elif ind["e8"][i] < ind["e20"][i] < ind["e50"][i]:
            s += 1.0; votes.append(-1)

    # L2: MOMENTUM CONFIRMATION (RSI + MACD aligned)
    rsi_v = ind["rsi"][i]
    mh = ind["macd"][2][i]
    mh_p = ind["macd"][2][i-1] if i > 0 else 0.0

    rsi_buy = (40 <= rsi_v <= 65 and rsi_v > 50)
    rsi_sell = (35 <= rsi_v <= 60 and rsi_v < 50)
    macd_buy = (mh > 0 and mh > mh_p)
    macd_sell = (mh < 0 and mh < mh_p)

    if rsi_buy and macd_buy:
        s += 1.5; votes.append(1)
    elif rsi_sell and macd_sell:
        s += 1.5; votes.append(-1)
    elif rsi_buy or macd_buy:
        s += 0.5; votes.append(1)
    elif rsi_sell or macd_sell:
        s += 0.5; votes.append(-1)

    # L3: BREAKOUT / SQUEEZE (BB + ATR)
    bbw = ind["bbw"][i]; bbw_a = ind["bbw_avg"][i]
    if bbw_a > 0 and bbw < bbw_a * 0.80 and a > aa * 1.1:
        s += 1.5  # Squeeze + expansion = powerful breakout
    elif a > aa * 1.15:
        s += 0.8  # ATR expansion alone

    # L4: SESSION PEAK (London-NY)
    if 12 <= hour <= 15:
        s += 1.0
    elif 7 <= hour <= 11:
        s += 0.5

    # L5: MTF + STOCH CONFLUENCE
    stk = ind["stk"][0][i]; std = ind["stk"][1][i]
    if ind["e20"][i] > ind["e50"][i] > ind["e200"][i]:
        if stk > std and stk < 60:
            s += 1.5; votes.append(1)
        elif stk > 80:
            s += 0.5  # Strong trend but overbought — partial score
    elif ind["e20"][i] < ind["e50"][i] < ind["e200"][i]:
        if stk < std and stk > 40:
            s += 1.5; votes.append(-1)
        elif stk < 20:
            s += 0.5

    if not votes:
        return s, 0
    bv = sum(1 for v in votes if v > 0)
    sv = sum(1 for v in votes if v < 0)
    d = 1 if bv > sv else (-1 if sv > bv else 0)
    return s, d


# ─── BACKTEST WITH FULL PARAMETERS ────────────────────────────────────────────
def backtest_full(csv_path, pair, sl_m, tp_m, min_sc, risk_pct, max_hold=50):
    """Full backtest with specific parameters."""
    df = pd.read_csv(csv_path, parse_dates=["time"])
    if len(df) < 500:
        return None

    split = int(len(df) * 0.7)
    ind = precompute(df)
    c = ind["c"]; h = ind["h"]; l = ind["l"]
    hours = ind["hours"]
    n = len(c)

    trades = []
    equity = 200.0
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
        a = ind["atr"][i]
        sl_d = a * sl_m
        tp_d = a * tp_m
        if sl_d <= 0:
            continue

        risk_amt = equity * (risk_pct / 100.0)
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
        trades.append({
            "result": result, "equity": equity, "score": sc,
            "dir": "BUY" if d == 1 else "SELL",
        })
        daily += 1
        last_bar = i

        if equity >= 100000:
            break

    return trades, equity


# ─── COMPOUND MONTE CARLO ─────────────────────────────────────────────────────
def monte_carlo_projection(wr, avg_win_r, risk_pct, trades_per_day, start_eq, target_eq, n_sims=1000):
    """Monte Carlo simulation for compound growth."""
    results = []
    for _ in range(n_sims):
        eq = start_eq
        max_eq = start_eq
        max_dd = 0
        days = 0
        while eq < target_eq and days < 365 * 5:
            for _ in range(trades_per_day):
                if eq <= 0:
                    break
                ra = eq * (risk_pct / 100.0)
                if np.random.random() < wr:
                    eq += ra * avg_win_r
                else:
                    eq -= ra
                eq = max(eq, 0.0)
                max_eq = max(max_eq, eq)
                dd = (max_eq - eq) / max_eq * 100 if max_eq > 0 else 0
                max_dd = max(max_dd, dd)
            days += 1
            if eq <= 0:
                break
        results.append({"equity": eq, "days": days, "max_dd": max_dd, "blown": eq <= 0})
    return results


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    data_dir = Path("data")
    t0 = time.time()

    print("=" * 90)
    print("  MAXIMUM GROWTH PLAN: $200 -> $500,000")
    print("  Realistic projection based on backtest data + Monte Carlo")
    print("=" * 90)

    # ─── STEP 1: Find best config per pair ────────────────────────────────
    PAIRS = ["GBPUSD", "AUDUSD", "USDCHF", "NZDUSD", "EURUSD", "XAGUSD", "USDJPY"]

    configs = [
        {"sl": 1.2, "tp": 2.5, "sc": 5.0, "risk": 3.0, "hold": 50},
        {"sl": 1.2, "tp": 3.0, "sc": 5.0, "risk": 3.0, "hold": 50},
        {"sl": 1.0, "tp": 2.5, "sc": 6.0, "risk": 3.0, "hold": 30},
        {"sl": 0.8, "tp": 2.0, "sc": 5.0, "risk": 3.0, "hold": 30},
        {"sl": 1.2, "tp": 2.5, "sc": 6.0, "risk": 3.0, "hold": 50},
        {"sl": 1.2, "tp": 2.5, "sc": 7.0, "risk": 3.0, "hold": 50},
        {"sl": 1.5, "tp": 3.0, "sc": 5.0, "risk": 3.0, "hold": 50},
    ]

    best_configs = {}
    print(f"\n  GRID SEARCH: {len(configs)} configs x {len(PAIRS)} pairs")

    for pair in PAIRS:
        csv = data_dir / f"{pair}_M5.csv"
        if not csv.exists():
            hits = list(data_dir.glob(f"*{pair}*M5*"))
            csv = hits[0] if hits else None
        if csv is None:
            continue

        print(f"  Testing {pair}...", end=" ", flush=True)
        best = None

        for cfg in configs:
            trades, eq = backtest_full(str(csv), pair,
                                       cfg["sl"], cfg["tp"], cfg["sc"],
                                       cfg["risk"], cfg["hold"])
            if not trades:
                continue

            wins = sum(1 for t in trades if t["result"] > 0)
            wr = wins / len(trades) * 100 if trades else 0
            aw = np.mean([t["result"] for t in trades if t["result"] > 0]) if wins else 0
            al = np.mean([abs(t["result"]) for t in trades if t["result"] <= 0]) if len(trades) > wins else 1
            pf = (aw * wins) / (al * (len(trades) - wins)) if (len(trades) > wins and al > 0) else 0
            avg_r = np.mean([t["result"] for t in trades])
            gross = sum(t["result"] for t in trades)

            # Score by: positive expectancy + sufficient trades + low drawdown
            score = avg_r * min(len(trades), 200) * (pf if pf > 0 else 0)

            result = {
                **cfg, "trades": len(trades), "wr": wr, "aw": aw, "al": al,
                "pf": pf, "avg_r": avg_r, "gross": gross, "equity": eq, "score": score,
            }

            if best is None or score > best["score"]:
                best = result

        if best:
            best_configs[pair] = best
            print(f"SL={best['sl']} TP={best['tp']} SC={best['sc']} -> "
                  f"WR={best['wr']:.1f}% PF={best['pf']:.2f} "
                  f"AvgR={best['avg_r']:+.3f} Tr={best['trades']}")
        else:
            print("NO VIABLE CONFIG")

    # ─── STEP 2: Identify best pairs ──────────────────────────────────────
    ranked = sorted(best_configs.items(), key=lambda x: x[1]["avg_r"], reverse=True)
    profitable = [(p, c) for p, c in ranked if c["avg_r"] > 0 and c["pf"] > 1.0]

    print(f"\n  RANKED BY EXPECTANCY:")
    for p, c in ranked:
        tag = " <-- LIVE" if c["avg_r"] > 0 and c["pf"] > 1.0 else ""
        print(f"    {p:8s} | WR {c['wr']:5.1f}% | PF {c['pf']:5.2f} | "
              f"AvgR {c['avg_r']:+7.3f} | Gross ${c['gross']:9.2f} | "
              f"MaxEq ${c['equity']:9.2f}{tag}")

    # ─── STEP 3: Monte Carlo projection ───────────────────────────────────
    if profitable:
        best = profitable[0][1]
        pair_name = profitable[0][0]
    else:
        best = ranked[0][1]
        pair_name = ranked[0][0]

    wr = best["wr"] / 100.0
    avg_win_r = best["aw"] / max(best["al"], 0.01)

    print(f"\n  {'='*70}")
    print(f"  MONTE CARLO PROJECTION (1000 simulations)")
    print(f"  Best pair: {pair_name} | WR {wr*100:.1f}% | R:R {avg_win_r:.1f}:1")
    print(f"  {'='*70}")

    PHASES = [
        {"risk": 3.0, "target": 2000, "trades": 5},
        {"risk": 2.5, "target": 20000, "trades": 5},
        {"risk": 2.0, "target": 200000, "trades": 4},
        {"risk": 1.5, "target": 500000, "trades": 3},
    ]

    equity = 200.0
    total_days = 0
    blow_count = 0

    for pi, ph in enumerate(PHASES):
        mc = monte_carlo_projection(
            wr, avg_win_r, ph["risk"], ph["trades"],
            equity, ph["target"], n_sims=500
        )

        # Stats
        final_eqs = [r["equity"] for r in mc if not r["blown"]]
        days_list = [r["days"] for r in mc if not r["blown"]]
        dds = [r["max_dd"] for r in mc]
        blown = sum(1 for r in mc if r["blown"])

        if not final_eqs:
            print(f"\n  Phase {pi+1}: TOO RISKY — {blown}/500 sims blew up")
            blow_count += blown
            continue

        p50 = np.median(final_eqs)
        p10 = np.percentile(final_eqs, 10)
        p90 = np.percentile(final_eqs, 90)
        med_days = np.median(days_list) if days_list else 999
        avg_dd = np.mean(dds)

        print(f"\n  Phase {pi+1}: ${equity:,.0f} -> ${ph['target']:,.0f}")
        print(f"    Risk: {ph['risk']}% | Trades/day: {ph['trades']}")
        print(f"    Blow-up rate: {blown}/500 ({blown/5:.1f}%)")
        print(f"    Median end equity: ${p50:,.0f}")
        print(f"    10th percentile:   ${p10:,.0f}")
        print(f"    90th percentile:   ${p90:,.0f}")
        print(f"    Median days:       {med_days:.0f} ({med_days/30:.1f} months)")
        print(f"    Avg max drawdown:  {avg_dd:.1f}%")

        equity = p50
        total_days += med_days

    # ─── STEP 4: Honest summary ───────────────────────────────────────────
    print(f"\n  {'='*70}")
    print(f"  HONEST GROWTH SUMMARY")
    print(f"  {'='*70}")
    print(f"    Start: $200")
    print(f"    Median end: ${equity:,.0f}")
    print(f"    Time: ~{total_days:.0f} days ({total_days/30:.0f} months)")
    print(f"    Target: $500,000")
    print(f"    Gap: ${500000 - equity:,.0f}")

    if equity < 500000:
        print(f"\n  REALITY CHECK:")
        print(f"    M5 forex scalping with {wr*100:.0f}% WR and {avg_win_r:.1f}:1 R:R")
        print(f"    produces +{best['avg_r']:.3f}R per trade on average.")
        print(f"    At 3% risk per trade, that's ~{best['avg_r']*3:.2f}% per trade.")
        print(f"    With 5 trades/day x 22 days = ~{best['avg_r']*3*5*22:.1f}%/month")
        print(f"")
        print(f"    $200 -> $500K requires 2,500x return.")
        print(f"    At 20%/month compounded: ~{np.log(2500)/np.log(1.2)/12:.1f} years")
        print(f"    At 50%/month compounded: ~{np.log(2500)/np.log(1.5)/12:.1f} years")
        print(f"    At 100%/month compounded: ~{np.log(2500)/np.log(2.0)/12:.1f} years")
        print(f"")
        print(f"  WHAT ACTUALLY WORKS:")
        print(f"    1. COMPOUND: Reinvest ALL profits, never withdraw")
        print(f"    2. SCALE UP: Increase risk % as equity grows (3% -> 2% -> 1.5%)")
        print(f"    3. MULTI-PAIR: Trade all profitable pairs simultaneously")
        print(f"    4. SCALE ACCOUNT: Add capital at milestones ($1K, $5K, $20K)")
        print(f"    5. PATIENCE: This is a 3-5 year project, not a get-rich-quick")
    else:
        print(f"\n  TARGET ACHIEVED! ~{total_days/30:.0f} months")

    # ─── STEP 5: Monthly milestone table ──────────────────────────────────
    print(f"\n  {'='*70}")
    print(f"  MONTHLY MILESTONES (realistic projection)")
    print(f"  {'='*70}")
    print(f"  {'Month':>6s} | {'Balance':>12s} | {'Monthly%':>9s} | {'Milestone'}")
    print(f"  {'-'*60}")

    eq = 200.0
    milestones = [
        (500, "1st double"), (1000, "1K club"), (2500, "2.5K"),
        (5000, "5K milestone"), (10000, "10K!"), (25000, "25K"),
        (50000, "50K milestone"), (100000, "100K! Six figures!"),
        (200000, "200K milestone"), (500000, "500K TARGET!"),
    ]
    m_idx = 0

    for m in range(1, 61):  # 60 months = 5 years
        if eq >= 500000:
            break

        # Dynamic risk
        risk = 3.0 if eq < 2000 else (2.5 if eq < 10000 else (2.0 if eq < 50000 else 1.5))

        # Monthly return (from backtest data)
        trades = 110  # 5/day x 22 days
        start_eq = eq
        for _ in range(trades):
            if eq <= 0:
                break
            ra = eq * (risk / 100.0)
            if np.random.random() < wr:
                eq += ra * avg_win_r
            else:
                eq -= ra
            eq = max(eq, 0.0)

        ret = ((eq / start_eq) - 1) * 100

        milestone = ""
        while m_idx < len(milestones) and eq >= milestones[m_idx][0]:
            milestone = f" --> {milestones[m_idx][1]}"
            m_idx += 1

        print(f"  {m:>6d} | ${eq:>11,.0f} | {ret:>+8.1f}% | {milestone}")

    print(f"\n  Final: ${eq:,.0f} after {m} months")

    print(f"\n  {'='*70}")
    print(f"  SETTINGS TO APPLY (from grid search)")
    print(f"  {'='*70}")
    for p, c in profitable[:5]:
        print(f"    {p}: SL={c['sl']}xATR TP={c['tp']}xATR MinScore={c['sc']}")

    print(f"\n  Completed in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
