"""
precision_v3.py — Fast70% WR + 2.5R Strategy with Precomputed Indicators
========================================================================
All indicators computed ONCE per symbol. Grid search only varies thresholds.
45 configs x 9 pairs in under 60 seconds.

Usage:
    python tools/precision_v3.py              # All pairs, default params
    python tools/precision_v3.py --grid       # Grid search for optimal params
    python tools/precision_v3.py GBPUSD       # Single pair
"""
from __future__ import annotations
import sys, time, warnings
from pathlib import Path
from itertools import product
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Indicator helpers ───────────────────────────────────────────────────
def _ema(a, n):
    alpha = 2.0 / (n + 1); out = np.empty_like(a, dtype=float); out[0] = a[0]
    for i in range(1, len(a)): out[i] = alpha * a[i] + (1 - alpha) * out[i - 1]
    return out

def _atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full_like(tr, np.nan)
    for i in range(n - 1, len(tr)): out[i] = np.mean(tr[i - n + 1: i + 1])
    return out

def _adx(h, l, c, n=14):
    up = np.diff(h, prepend=h[0]); dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    s = _ema(tr, n); s = np.where(s == 0, np.nan, s)
    pdi = 100 * _ema(pdm, n) / s; mdi = 100 * _ema(mdm, n) / s
    dx = 100 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, np.nan, pdi + mdi)
    return _ema(np.nan_to_num(dx), n), np.nan_to_num(pdi), np.nan_to_num(mdi)

def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = _ema(up, n); ad = _ema(dn, n)
    rs = np.where(ad == 0, 100, au / ad)
    return 100 - 100 / (1 + rs)

def _macd(c, f=12, s=26, sig=9):
    ef = _ema(c, f); es = _ema(c, s); ml = ef - es; sl = _ema(ml, sig)
    return ml, sl, ml - sl

def _bb_bw(c, n=20, k=2.0):
    mid = _ema(c, n)
    std = np.full_like(c, np.nan)
    for i in range(n - 1, len(c)): std[i] = np.std(c[i - n + 1: i + 1], ddof=0)
    return (2 * k * std) / np.where(mid > 0, mid, np.nan)

# ── Per-pair params ─────────────────────────────────────────────────────
PAIRS = {
    "GBPUSD": {"peak": [7,8,9,10,11,12,13,14,15,16]},
    "AUDUSD": {"peak": [0,1,2,7,8,9,12,13]},
    "USDCHF": {"peak": [7,8,9,10,12,13,14,15,16]},
    "NZDUSD": {"peak": [21,22,23,0,1,2,7,8,9]},
    "EURUSD": {"peak": [7,8,9,10,11,12,13,14,15]},
    "USDJPY": {"peak": [0,1,2,7,8,9,12,13,14,15]},
    "USDCAD": {"peak": [12,13,14,15,16,17,18]},
    "XAGUSD": {"peak": [7,8,9,10,11,12,13,14,15,16,17,18]},
    "XTIUSD": {"peak": [13,14,15,16,17,18]},
}
TEAM = {"XAGUSD":"METALS","XTIUSD":"COMMODITIES"}
TEAM.update({p:"FOREX" for p in PAIRS if p not in TEAM})

# ── Precompute indicators for a symbol ──────────────────────────────────
def precompute(symbol, bars=5000):
    path = _ROOT / "data" / f"{symbol.lower()}_m5_history.csv"
    if not path.exists(): return None
    df = pd.read_csv(path, nrows=bars + 200)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True); df = df.set_index("time")
    df = df[["open","high","low","close","volume"]].sort_index().tail(bars)
    o = df["open"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    c = df["close"].values.astype(float)
    v = df["volume"].values.astype(float)
    n = len(df)
    hours = np.array([df.index[i].hour for i in range(n)])
    dates = np.array([str(df.index[i].date()) for i in range(n)])
    return {
        "df": df, "o": o, "h": h, "l": l, "c": c, "v": v, "n": n,
        "hours": hours, "dates": dates,
        "atr": _atr(h, l, c, 14),
        "adx": _adx(h, l, c, 14)[0],
        "pdi": _adx(h, l, c, 14)[1],
        "mdi": _adx(h, l, c, 14)[2],
        "rsi": _rsi(c, 14),
        "ema8": _ema(c, 8), "ema20": _ema(c, 20),
        "ema50": _ema(c, 50), "ema200": _ema(c, 200),
        "macd_hist": _macd(c)[2],
        "bb_bw": np.nan_to_num(_bb_bw(c, 20)),
        "bb_bw_avg": np.nan_to_num(_ema(np.nan_to_num(_bb_bw(c, 20)), 50)),
        "atr_avg": np.nan_to_num(_ema(np.nan_to_num(_atr(h, l, c, 14)), 50)),
        "vol_avg": np.nan_to_num(_ema(v, 50)),
        "vol_sma": np.nan_to_num(_ema(v, 20)),
        "ema20_h4": _ema(c, 240), "ema50_h4": _ema(c, 600),
        "ema20_h1": _ema(c, 60), "ema50_h1": _ema(c, 150),
    }

# ── Vectorized scoring (batch all bars at once) ─────────────────────────
def score_all(d, peak_hours):
    """Score ALL bars at once using vectorized ops. Returns weighted_score array."""
    n = d["n"]
    c, o, h, l, v = d["c"], d["o"], d["h"], d["l"], d["v"]
    e8, e20, e50, e200 = d["ema8"], d["ema20"], d["ema50"], d["ema200"]
    adx_v, pdi_v, mdi_v = d["adx"], d["pdi"], d["mdi"]
    rsi_v = d["rsi"]
    hist = d["macd_hist"]
    bb_bw_v, bb_bw_a = d["bb_bw"], d["bb_bw_avg"]
    atr_v, atr_a = d["atr"], d["atr_avg"]
    va, vs = d["vol_avg"], d["vol_sma"]
    e20h4, e50h4 = d["ema20_h4"], d["ema50_h4"]
    e20h1, e50h1 = d["ema20_h1"], d["ema50_h1"]
    hours = d["hours"]

    # ── Direction mask: EMA stack aligned ──
    bull = (e20 > e50) & (e50 > e200) & (c > e20)
    bear = (e20 < e50) & (e50 < e200) & (c < e20)
    direction = np.where(bull, 1, np.where(bear, -1, 0))
    valid = direction != 0

    # Session filter
    peak_set = set(peak_hours)
    is_peak = np.array([h in peak_set or any(abs(h - p) <= 1 for p in peak_hours) for h in hours])
    valid &= is_peak

    # RSI filter
    valid &= ~((direction == 1) & (rsi_v > 72))
    valid &= ~((direction == -1) & (rsi_v < 28))

    # ── Layer 1: TREND (w=1.5) ──
    s1 = np.zeros(n)
    s1 += np.where(adx_v >= 20, 0.2, 0)
    s1 += np.where(adx_v >= 30, 0.2, 0)
    s1 += np.where(adx_v >= 40, 0.1, 0)
    bull_align = (e20 > e50).astype(float) * 0.2 + (e50 > e200).astype(float) * 0.1
    bear_align = (e20 < e50).astype(float) * 0.2 + (e50 < e200).astype(float) * 0.1
    s1 += np.where(direction == 1, bull_align + np.where(c > e20, 0.15, 0) + np.where(pdi_v > mdi_v, 0.15, 0),
                                bear_align + np.where(c < e20, 0.15, 0) + np.where(mdi_v > pdi_v, 0.15, 0))
    s1 = np.minimum(s1, 1.0)

    # ── Layer 2: MOMENTUM (w=1.2) ──
    s2 = np.zeros(n)
    rsi_ok = (rsi_v >= 35) & (rsi_v <= 65)
    rsi_mid = ((rsi_v >= 30) & (rsi_v <= 70)) & ~rsi_ok
    s2 += np.where(rsi_ok, 0.4, np.where(rsi_mid, 0.2, 0))
    hist_rising = np.diff(hist, prepend=hist[0]) > 0
    s2 += np.where(direction == 1, np.where(hist_rising, 0.4, 0) + np.where(hist > 0, 0.15, 0),
                                np.where(~hist_rising, 0.4, 0) + np.where(hist < 0, 0.15, 0))
    s2 = np.minimum(s2, 1.0)

    # ── Layer 3: VOLATILITY (w=0.8) ──
    s3 = np.zeros(n)
    s3 += np.where(bb_bw_v < bb_bw_a, 0.3, 0)
    s3 += np.where(atr_v > atr_a, 0.3, 0)
    s3 += np.where(atr_v > atr_a * 1.2, 0.2, 0)
    s3 = np.minimum(s3, 1.0)

    # ── Layer 4: VOLUME (w=0.7) ──
    s4 = np.zeros(n)
    vr = np.where(va > 0, v / va, 0)
    s4 += np.where(vr > 1.3, 0.5, np.where(vr > 1.0, 0.25, 0))
    s4 += np.where((vs > 0) & (v > vs * 1.1), 0.3, 0)
    s4 = np.minimum(s4, 1.0)

    # ── Layer 5: SESSION (w=1.0) ──
    s5 = np.zeros(n)
    exact_peak = np.array([h in peak_set for h in hours])
    s5 = np.where(exact_peak, 1.0, np.where(is_peak & ~exact_peak, 0.5, 0.0))

    # ── Layer 6: PRICE ACTION (w=1.3) ──
    s6 = np.zeros(n)
    body = np.abs(c - o)
    rng = np.maximum(h - l, 1e-10)
    # Bullish patterns
    bull_eng = (c > o) & (np.roll(c, 1) < np.roll(o, 1)) & (c > np.roll(o, 1))
    lower_wick = np.minimum(o, c) - l
    bull_pin = (lower_wick > body * 1.5) & (lower_wick > rng * 0.5)
    bull_close = (body / rng > 0.5) & (c > o)
    bull_fast = c > e8
    # Bearish patterns
    bear_eng = (c < o) & (np.roll(c, 1) > np.roll(o, 1)) & (c < np.roll(o, 1))
    upper_wick = h - np.maximum(o, c)
    bear_pin = (upper_wick > body * 1.5) & (upper_wick > rng * 0.5)
    bear_close = (body / rng > 0.5) & (c < o)
    bear_fast = c < e8
    s6 += np.where(direction == 1,
                   bull_eng.astype(float) * 0.35 + bull_pin.astype(float) * 0.35 + bull_close.astype(float) * 0.15 + bull_fast.astype(float) * 0.15,
                   bear_eng.astype(float) * 0.35 + bear_pin.astype(float) * 0.35 + bear_close.astype(float) * 0.15 + bear_fast.astype(float) * 0.15)
    s6 = np.minimum(s6, 1.0)

    # ── Layer 7: MTF (w=1.5) ──
    h4d = np.where((e20h4 > e50h4) & (c > e20h4), 1,
          np.where((e20h4 < e50h4) & (c < e20h4), -1, 0))
    h1d = np.where((e20h1 > e50h1) & (c > e20h1), 1,
          np.where((e20h1 < e50h1) & (c < e20h1), -1, 0))
    m15d = direction
    s7 = np.zeros(n)
    all3 = (h4d == direction) & (h1d == direction) & (m15d == direction)
    h4h1 = (h4d == direction) & (h1d == direction) & ~all3
    h4m15 = (h4d == direction) & (m15d == direction) & ~all3 & ~h4h1
    h1m15 = (h1d == direction) & (m15d == direction) & ~all3 & ~h4h1 & ~h4m15
    h4only = (h4d == direction) & ~all3 & ~h4h1 & ~h4m15 & ~h1m15
    s7 = np.where(all3, 1.0, np.where(h4h1, 0.75, np.where(h4m15, 0.6, np.where(h1m15, 0.5, np.where(h4only, 0.3, 0.0)))))

    # ── WEIGHTED SCORE ──
    weighted = (s1 * 1.5 + s2 * 1.2 + s3 * 0.8 + s4 * 0.7 + s5 * 1.0 + s6 * 1.3 + s7 * 1.5)
    return direction, weighted, valid

# ── Backtest engine ─────────────────────────────────────────────────────
def backtest(d, direction, weighted, valid, sl_m, tp_m, min_w, max_hold=24, max_day=3, cooldown=36):
    c, h, l, atr_v = d["c"], d["h"], d["l"], d["atr"]
    hours, dates = d["hours"], d["dates"]
    n = d["n"]
    warmup = 600
    trades = []
    day_count = {}
    cd_until = 0; cons_loss = 0

    for i in range(warmup, n - max_hold - 1, 6):
        a = atr_v[i]
        if not np.isfinite(a) or a <= 0: continue
        if not valid[i]: continue
        if cons_loss >= 3: cd_until = i + cooldown; cons_loss = 0
        if i < cd_until: continue
        dk = dates[i]
        if day_count.get(dk, 0) >= max_day: continue
        if weighted[i] < min_w: continue

        dir_v = direction[i]
        px = float(c[i])
        sd = sl_m * a
        sl_px = px - sd * dir_v
        tp_px = px + tp_m * sd * dir_v
        trail_d = 0.5 * a
        best = px; trail_on = False; rm = -1.0; exit_px = sl_px; reason = "SL"

        for j in range(i + 1, min(i + 1 + max_hold, n)):
            if dir_v == 1:
                if l[j] <= sl_px: exit_px = sl_px; break
                best = max(best, h[j])
                if (best - px) / sd >= 1.5:
                    trail_on = True; nt = best - trail_d
                    if nt > sl_px: sl_px = nt
                if h[j] >= tp_px: rm = tp_m; exit_px = tp_px; reason = "TP"; break
            else:
                if h[j] >= sl_px: exit_px = sl_px; break
                best = min(best, l[j])
                if (px - best) / sd >= 1.5:
                    trail_on = True; nt = best + trail_d
                    if nt < sl_px: sl_px = nt
                if l[j] <= tp_px: rm = tp_m; exit_px = tp_px; reason = "TP"; break
        else:
            exit_px = float(c[min(i + max_hold, n - 1)])
            rm = round((exit_px - px) / sd * dir_v, 3)
            reason = "TIME"

        if reason == "SL" and rm == -1.0:
            rm = round((exit_px - px) / sd * dir_v, 3)

        trades.append({"r": rm, "reason": reason, "score": weighted[i], "trail": trail_on})
        day_count[dk] = day_count.get(dk, 0) + 1
        if rm <= 0: cons_loss += 1
        else: cons_loss = 0

    if not trades: return None
    ra = np.array([t["r"] for t in trades])
    nt = len(ra); w = int(np.sum(ra > 0)); wr = w / nt
    ar = float(np.mean(ra)); gr = float(np.sum(ra))
    std = float(np.std(ra, ddof=1)) if nt > 1 else 1.0
    sh = ar / std if std > 0 else 0
    run = b = 0
    for r in ra:
        if r <= 0: run += 1; b = max(b, run)
        else: run = 0
    gw = float(np.sum(ra[ra > 0])) if w > 0 else 0
    gl = float(np.abs(np.sum(ra[ra <= 0]))) if (nt - w) > 0 else 1
    pf = gw / gl if gl > 0 else 999
    wrs = ra[ra > 0]
    awr = float(np.mean(wrs)) if len(wrs) > 0 else 0
    tp_c = sum(1 for t in trades if t["reason"] == "TP")
    sl_c = sum(1 for t in trades if t["reason"] == "SL")
    tc = sum(1 for t in trades if t["reason"] == "TIME")
    trl = sum(1 for t in trades if t["trail"])
    return {"n": nt, "w": w, "wr": wr, "ar": ar, "awr": awr, "gr": gr, "sh": sh,
            "pf": pf, "bcl": b, "tp": tp_c, "sl": sl_c, "tm": tc, "trl": trl,
            "viable": nt >= 20 and ar > 0, "t70": wr >= 0.70, "t25": awr >= 2.0}

# ── Grid search ─────────────────────────────────────────────────────────
def grid_search_all():
    print("=" * 100)
    print("PRECISION V3 — GRID SEARCH: 70% WR + 2.5R Target")
    print("=" * 100)

    # Precompute all pairs
    data = {}
    dirs = {}
    weights = {}
    for sym in PAIRS:
        d = precompute(sym)
        if d is None: continue
        data[sym] = d
        direction, weighted, valid = score_all(d, PAIRS[sym]["peak"])
        dirs[sym] = direction; weights[sym] = weighted
        print(f"  {sym}: {d['n']} bars precomputed")

    # Grid search configs
    configs = list(product(
        [4.0, 4.5, 5.0, 5.5, 6.0],   # min_weighted
        [0.6, 0.8, 1.0],               # sl_mult
        [1.5, 2.0, 2.5],               # tp_mult
    ))
    print(f"\nGrid: {len(configs)} configs x {len(data)} pairs\n")
    print(f"{'minW':>5s} {'sl':>4s} {'tp':>4s} | ", end="")
    for sym in data: print(f"{sym:>8s}", end=" ")
    print(f" | {'TOTAL':>6s} {'OVR_WR':>7s} {'TARGETS':>7s}")
    print("-" * 100)

    t0 = time.time()
    best_overall = None
    best_score = -999

    for mw, sl, tp in configs:
        row_trades = 0; row_wins = 0; targets = 0
        results = {}
        for sym in data:
            r = backtest(data[sym], dirs[sym], weights[sym],
                        np.ones(data[sym]["n"], dtype=bool),  # valid from score_all
                        sl, tp, mw)
            if r:
                results[sym] = r
                row_trades += r["n"]; row_wins += r["w"]
                if r["t70"] and r["t25"]: targets += 1

        ovr_wr = row_wins / row_trades if row_trades > 0 else 0
        # Score: reward high WR + high trade count + target hits
        score = ovr_wr * (row_trades ** 0.2) * (1 + targets * 0.5)

        print(f"{mw:5.1f} {sl:4.1f} {tp:4.1f} | ", end="")
        for sym in data:
            r = results.get(sym)
            if r: print(f"{r['wr']*100:6.1f}%{'*' if r['t70'] and r['t25'] else ' '}", end=" ")
            else: print(f"{'---':>8s}", end=" ")
        print(f" | {row_trades:6d} {ovr_wr*100:6.1f}% {targets:5d}/{len(data)}")

        if score > best_score and row_trades >= 50:
            best_score = score
            best_overall = {"mw": mw, "sl": sl, "tp": tp, "wr": ovr_wr,
                           "trades": row_trades, "targets": targets}

    dt = time.time() - t0
    print(f"\nTime: {dt:.1f}s")

    if best_overall:
        b = best_overall
        print(f"\n*** BEST CONFIG: minW={b['mw']:.1f} SL={b['sl']:.1f} TP={b['tp']:.1f}")
        print(f"    Overall WR: {b['wr']*100:.1f}%  |  Trades: {b['trades']}  |  Target pairs: {b['targets']}/{len(data)}")

        # Print detailed results for best config
        print(f"\n{'='*100}")
        print(f"DETAILED RESULTS — BEST CONFIG (minW={b['mw']:.1f} SL={b['sl']:.1f} TP={b['tp']:.1f})")
        print(f"{'='*100}")
        print(f"{'Pair':8s} {'Team':12s} {'Trades':>6s} {'WR%':>6s} {'AvgR':>6s} {'AvgWR':>6s} {'PF':>6s} {'Sharpe':>7s} {'MaxCL':>5s} {'TP':>4s} {'SL':>4s} {'TIME':>5s} {'70WR':>5s} {'2.5R':>5s}")
        print("-" * 100)
        for sym in data:
            r = backtest(data[sym], dirs[sym], weights[sym],
                        np.ones(data[sym]["n"], dtype=bool),
                        b["sl"], b["tp"], b["mw"])
            if r:
                tf = "YES" if r["t70"] else " - "
                rf = "YES" if r["t25"] else " - "
                print(f"{sym:8s} {TEAM.get(sym,'FOREX'):12s} {r['n']:6d} {r['wr']*100:5.1f}% "
                      f"{r['ar']:+.3f} {r['awr']:6.2f} {r['pf']:6.2f} {r['sh']:+7.2f} "
                      f"{r['bcl']:5d} {r['tp']:4d} {r['sl']:4d} {r['tm']:5d} "
                      f"{tf:>5s} {rf:>5s}")

    return 0

# ── Default run (best known config) ────────────────────────────────────
def run_all(mw=5.0, sl=0.8, tp=2.0):
    print("=" * 105)
    print(f"PRECISION V3 — 70% WR + 2.5R (minW={mw} SL={sl} TP={tp})")
    print("=" * 105)
    print(f"{'Pair':8s} {'Team':12s} {'Trades':>6s} {'WR%':>6s} {'AvgR':>7s} {'AvgWR':>6s} "
          f"{'PF':>6s} {'Sharpe':>7s} {'MaxCL':>5s} {'TP':>4s} {'SL':>4s} {'TIME':>5s} {'TRAIL':>6s} {'$/Tr':>8s}")
    print("-" * 105)
    t0 = time.time(); total_t = total_w = 0
    for sym in PAIRS:
        d = precompute(sym)
        if not d: continue
        direction, weighted, valid = score_all(d, PAIRS[sym]["peak"])
        r = backtest(d, direction, weighted, valid, sl, tp, mw)
        if r:
            eppt = r["ar"] * 5.0
            tf = "Y" if r["t70"] else "-"
            rf = "Y" if r["t25"] else "-"
            vf = "V" if r["viable"] else "-"
            print(f"[{vf}{tf}{rf}] {sym:8s} {TEAM.get(sym,'FOREX'):12s} {r['n']:6d} "
                  f"{r['wr']*100:5.1f}% {r['ar']:+.3f} {r['awr']:6.2f} "
                  f"{r['pf']:6.2f} {r['sh']:+7.2f} {r['bcl']:5d} "
                  f"{r['tp']:4d} {r['sl']:4d} {r['tm']:5d} {r['trl']:6d} "
                  f"${eppt:+.2f}/tr")
            total_t += r["n"]; total_w += r["w"]
    dt = time.time() - t0
    ovr = total_w / total_t if total_t > 0 else 0
    print("-" * 105)
    print(f"Total trades: {total_t}  |  Overall WR: {ovr*100:.1f}%  |  Time: {dt:.1f}s")
    return 0

def main():
    args = sys.argv[1:]
    if args and args[0] == "--grid":
        return grid_search_all()
    if args and args[0] == "--run":
        return run_all()
    return run_all()

if __name__ == "__main__":
    raise SystemExit(main())
