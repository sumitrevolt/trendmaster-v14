"""
deep_strategy_research.py — Deep research to achieve 80% win rate.

Phase 1: Diagnose — what kills trades?
Phase 2: Build multi-confluence scoring system
Phase 3: Backtest optimized strategy
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
    adx_val = _ema(np.nan_to_num(dx), n)
    return adx_val, np.nan_to_num(pdi), np.nan_to_num(mdi)


def _bb(c, n=20, k=2.0):
    sma = np.array([np.mean(c[max(0, i-n+1):i+1]) for i in range(len(c))])
    std = np.array([np.std(c[max(0, i-n+1):i+1]) for i in range(len(c))])
    return sma, sma + k * std, sma - k * std, (2 * k * std) / np.where(sma == 0, 1, sma)


def _macd(c, fast=12, slow=26, sig=9):
    line = _ema(c, fast) - _ema(c, slow)
    signal = _ema(line, sig)
    hist = line - signal
    return line, signal, hist


def _stoch_rsi(c, rsi_n=14, stoch_n=14, k=3):
    r = _rsi(c, rsi_n)
    out_k = np.zeros_like(r)
    for i in range(stoch_n - 1, len(r)):
        window = r[i - stoch_n + 1: i + 1]
        mn, mx = np.min(window), np.max(window)
        out_k[i] = ((r[i] - mn) / (mx - mn) * 100) if mx != mn else 50
    out_d = _ema(out_k, k)
    return out_k, out_d


def _vwap(h, l, c, v):
    tp = (h + l + c) / 3
    cum_tp_vol = np.cumsum(tp * v)
    cum_vol = np.cumsum(v)
    return cum_tp_vol / np.where(cum_vol == 0, 1, cum_vol)


# ── Phase 1: Deep diagnosis ─────────────────────────────────────────────
def diagnose_pair(symbol, bars=5000):
    """Analyze every trade — what do winning trades look like vs losing?"""
    path = _ROOT / "data" / f"{symbol.lower()}_m5_history.csv"
    df = pd.read_csv(path, nrows=bars + 200)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].sort_index().tail(bars)

    h, l, c, v = (df["high"].values.astype(float), df["low"].values.astype(float),
                   df["close"].values.astype(float), df["volume"].values.astype(float))

    atr_v = _atr(h, l, c, 14)
    adx_v, pdi_v, mdi_v = _adx(h, l, c, 14)
    rsi_v = _rsi(c, 14)
    ema8 = _ema(c, 8)
    ema20 = _ema(c, 20)
    ema50 = _ema(c, 50)
    ema200 = _ema(c, 200)
    bb_mid, bb_up, bb_lo, bb_w = _bb(c, 20, 2.0)
    macd_l, macd_s, macd_h = _macd(c)
    stoch_k, stoch_d = _stoch_rsi(c)
    vwap_v = _vwap(h, l, c, v)

    n = len(df)
    wins, losses = [], []
    warmup = 600

    for i in range(warmup, n - 24, 12):
        a = atr_v[i]
        if not np.isfinite(a) or a <= 0: continue
        adx_val = adx_v[i]
        rsi_val = rsi_v[i]
        e8, e20, e50, e200 = ema8[i], ema20[i], ema50[i], ema200[i]
        if not all(np.isfinite(x) for x in [e8, e20, e50, e200]): continue

        # Agent vote
        win = df.iloc[:i+1]
        frames = {'M30': _resample(win, 30), 'H1': _resample(win, 60), 'H4': _resample(win, 240)}
        direction, _ = vote_all(frames, min_votes=2)
        if direction == 0: continue

        # Session filter
        try: hour = df.index[i].hour
        except: hour = 12
        if not (7 <= hour <= 20): continue

        px = float(c[i])
        sl_m = 1.0; rr = 2.5
        sd = sl_m * a
        if direction == 1:
            sl_px, tp_px = px - sd, px + rr * sd
        else:
            sl_px, tp_px = px + sd, px - rr * sd

        r_mult = -1.0
        hold = 18
        for j in range(i+1, min(i+1+hold, n)):
            if direction == 1:
                if l[j] <= sl_px: break
                if h[j] >= tp_px: r_mult = rr; break
            else:
                if h[j] >= sl_px: break
                if l[j] <= tp_px: r_mult = rr; break
        else:
            ep = float(c[min(i+hold, n-1)])
            r_mult = round((ep - px) / sd * (1 if direction == 1 else -1), 3)

        # Gather diagnostic features at entry
        feat = {
            "direction": direction,
            "r": r_mult,
            "adx": adx_val,
            "rsi": rsi_val,
            "ema_stack": 1 if (e8 > e20 > e50) else (-1 if (e8 < e20 < e50) else 0),
            "price_vs_ema200": 1 if px > e200 else -1,
            "bb_width": bb_w[i] if np.isfinite(bb_w[i]) else 0,
            "bb_pos": (px - bb_mid[i]) / (bb_up[i] - bb_mid[i] + 1e-9) if direction == 1 else (bb_mid[i] - px) / (bb_mid[i] - bb_lo[i] + 1e-9),
            "macd_hist": macd_h[i] if np.isfinite(macd_h[i]) else 0,
            "macd_rising": 1 if i > 0 and macd_h[i] > macd_h[i-1] else 0,
            "stoch_k": stoch_k[i],
            "stoch_d": stoch_d[i],
            "atr_ratio": a / (c[i] + 1e-9),
            "hour": hour,
            "is_peak": 1 if 12 <= hour <= 16 else 0,
            "vol_vs_avg": v[i] / (np.mean(v[max(0,i-50):i]) + 1),
        }

        if r_mult > 0:
            wins.append(feat)
        else:
            losses.append(feat)

    # Analyze patterns
    print(f"\n{'='*60}")
    print(f"DIAGNOSIS: {symbol} ({len(wins)} wins, {len(losses)} losses)")
    print(f"{'='*60}")

    if not wins or not losses: return wins, losses

    wf = pd.DataFrame(wins)
    lf = pd.DataFrame(losses)

    print(f"\nFeature          | Winner (mean) | Loser (mean) | Delta")
    print(f"{'-'*60}")
    for col in ["adx", "rsi", "bb_width", "bb_pos", "macd_hist", "stoch_k", "atr_ratio", "is_peak", "vol_vs_avg"]:
        if col in wf.columns and col in lf.columns:
            wm, lm = wf[col].mean(), lf[col].mean()
            delta = wm - lm
            print(f"{col:16s} | {wm:13.3f} | {lm:13.3f} | {delta:+.3f}")

    # Key insights
    print(f"\n--- KEY INSIGHTS ---")
    # ADX
    win_adx = wf["adx"].mean()
    lose_adx = lf["adx"].mean()
    if win_adx > lose_adx:
        print(f"Winners have HIGHER ADX ({win_adx:.1f} vs {lose_adx:.1f}) — filter out weak trends")
    # RSI
    win_rsi = wf["rsi"].mean()
    lose_rsi = lf["rsi"].mean()
    print(f"Winners RSI={win_rsi:.1f} vs Losers RSI={lose_rsi:.1f}")
    # BB width
    win_bw = wf["bb_width"].mean()
    lose_bw = lf["bb_width"].mean()
    print(f"Winners BB_width={win_bw:.4f} vs Losers BB_width={lose_bw:.4f}")
    # Volume
    win_vol = wf["vol_vs_avg"].mean()
    lose_vol = lf["vol_vs_avg"].mean()
    print(f"Winners Vol={win_vol:.2f}x avg vs Losers Vol={lose_vol:.2f}x avg")

    return wins, losses


# ── Phase 2: Multi-confluence scorer ────────────────────────────────────
def compute_confluence_score(direction, i, c, h, l, v, indicators):
    """
    Score 0-100 based on how many confirmations agree.
    Higher score = higher probability trade.
    """
    px = float(c[i])
    score = 0
    reasons = []

    adx_v, rsi_v, ema8, ema20, ema50, ema200 = (
        indicators["adx"], indicators["rsi"],
        indicators["ema8"], indicators["ema20"], indicators["ema50"], indicators["ema200"]
    )
    bb_mid, bb_up, bb_lo = indicators["bb_mid"], indicators["bb_up"], indicators["bb_lo"]
    macd_h, stoch_k, stoch_d = indicators["macd_h"], indicators["stoch_k"], indicators["stoch_d"]
    atr_v, vwap_v = indicators["atr"], indicators["vwap"]

    # 1. ADX strength (0-15 pts)
    adx_val = adx_v[i]
    if adx_val > 35:
        score += 15; reasons.append(f"strong_trend_adx={adx_val:.0f}")
    elif adx_val > 28:
        score += 10; reasons.append(f"trend_adx={adx_val:.0f}")
    elif adx_val > 22:
        score += 5; reasons.append(f"weak_trend_adx={adx_val:.0f}")

    # 2. EMA stack alignment (0-15 pts)
    e8, e20, e50, e200 = ema8[i], ema20[i], ema50[i], ema200[i]
    if direction == 1:
        if e8 > e20 > e50 > e200:
            score += 15; reasons.append("full_bull_stack")
        elif e8 > e20 > e50:
            score += 10; reasons.append("bull_stack_3")
        elif px > e20:
            score += 5; reasons.append("above_ema20")
    else:
        if e8 < e20 < e50 < e200:
            score += 15; reasons.append("full_bear_stack")
        elif e8 < e20 < e50:
            score += 10; reasons.append("bear_stack_3")
        elif px < e20:
            score += 5; reasons.append("below_ema20")

    # 3. RSI position (0-10 pts)
    rsi_val = rsi_v[i]
    if direction == 1:
        if 40 <= rsi_val <= 65:
            score += 10; reasons.append(f"rsi_sweet_bull={rsi_val:.0f}")
        elif 35 <= rsi_val <= 72:
            score += 5; reasons.append(f"rsi_ok_bull={rsi_val:.0f}")
    else:
        if 35 <= rsi_val <= 60:
            score += 10; reasons.append(f"rsi_sweet_bear={rsi_val:.0f}")
        elif 28 <= rsi_val <= 65:
            score += 5; reasons.append(f"rsi_ok_bear={rsi_val:.0f}")

    # 4. Bollinger Band position (0-10 pts)
    bb_m, bb_u, bb_l = bb_mid[i], bb_up[i], bb_lo[i]
    if bb_u > bb_l:
        if direction == 1:
            if bb_m < px < bb_u:
                score += 10; reasons.append("bb_bull_zone")
            elif px > bb_u:
                score += 3; reasons.append("bb_overbought_warning")
        else:
            if bb_l < px < bb_m:
                score += 10; reasons.append("bb_bear_zone")
            elif px < bb_l:
                score += 3; reasons.append("bb_oversold_warning")

    # 5. MACD momentum (0-10 pts)
    mh = macd_h[i]
    mh_prev = macd_h[i-1] if i > 0 else mh
    if direction == 1:
        if mh > 0 and mh > mh_prev:
            score += 10; reasons.append("macd_bull_rising")
        elif mh > mh_prev:
            score += 5; reasons.append("macd_rising")
    else:
        if mh < 0 and mh < mh_prev:
            score += 10; reasons.append("macd_bear_falling")
        elif mh < mh_prev:
            score += 5; reasons.append("macd_falling")

    # 6. Stochastic RSI (0-10 pts)
    sk = stoch_k[i]
    sd_v = stoch_d[i]
    if direction == 1:
        if 20 < sk < 70 and sk > sd_v:
            score += 10; reasons.append(f"stoch_bull_cross={sk:.0f}")
        elif 20 < sk < 80:
            score += 5; reasons.append(f"stoch_ok={sk:.0f}")
    else:
        if 30 < sk < 80 and sk < sd_v:
            score += 10; reasons.append(f"stoch_bear_cross={sk:.0f}")
        elif 20 < sk < 80:
            score += 5; reasons.append(f"stoch_ok={sk:.0f}")

    # 7. Price vs VWAP (0-10 pts)
    vw = vwap_v[i]
    if np.isfinite(vw):
        if direction == 1 and px > vw:
            score += 10; reasons.append("above_vwap")
        elif direction == -1 and px < vw:
            score += 10; reasons.append("below_vwap")
        elif (direction == 1 and px > vw * 0.999) or (direction == -1 and px < vw * 1.001):
            score += 5; reasons.append("near_vwap")

    # 8. Volume confirmation (0-10 pts)
    vol_ratio = v[i] / (np.mean(v[max(0, i-50):i]) + 1)
    if vol_ratio > 2.0:
        score += 10; reasons.append(f"high_vol={vol_ratio:.1f}x")
    elif vol_ratio > 1.3:
        score += 5; reasons.append(f"vol_ok={vol_ratio:.1f}x")

    # 9. Session quality (0-5 pts)
    try: hour = df.index[i].hour if hasattr(df, 'index') else 12
    except: hour = 12
    if 12 <= hour <= 16:
        score += 5; reasons.append("peak_london_ny")
    elif 8 <= hour <= 11 or 17 <= hour <= 19:
        score += 3; reasons.append("good_session")

    # 10. 3-bar continuation (0-5 pts)
    if i >= 3:
        if direction == 1 and c[i] > c[i-1] > c[i-2]:
            score += 5; reasons.append("3bar_bull")
        elif direction == -1 and c[i] < c[i-1] < c[i-2]:
            score += 5; reasons.append("3bar_bear")

    return score, reasons


# ── Phase 3: Optimized backtest with confluence scoring ──────────────────
def run_confluence_backtest(symbol, bars=5000, min_score=60, verbose=True):
    path = _ROOT / "data" / f"{symbol.lower()}_m5_history.csv"
    df = pd.read_csv(path, nrows=bars + 200)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].sort_index().tail(bars)

    h, l, c, v = (df["high"].values.astype(float), df["low"].values.astype(float),
                   df["close"].values.astype(float), df["volume"].values.astype(float))

    indicators = {
        "adx": _adx(h, l, c, 14)[0],
        "rsi": _rsi(c, 14),
        "ema8": _ema(c, 8),
        "ema20": _ema(c, 20),
        "ema50": _ema(c, 50),
        "ema200": _ema(c, 200),
        "bb_mid": _bb(c)[0], "bb_up": _bb(c)[1], "bb_lo": _bb(c)[2],
        "macd_h": _macd(c)[2],
        "stoch_k": _stoch_rsi(c)[0], "stoch_d": _stoch_rsi(c)[1],
        "atr": _atr(h, l, c, 14),
        "vwap": _vwap(h, l, c, v),
    }

    n = len(df)
    trades = []
    warmup = 600

    for i in range(warmup, n - 24, 12):
        a = indicators["atr"][i]
        if not np.isfinite(a) or a <= 0: continue

        # Session filter
        try: hour = df.index[i].hour
        except: hour = 12
        if not (7 <= hour <= 20): continue

        # Agent vote
        win_df = df.iloc[:i+1]
        frames = {'M30': _resample(win_df, 30), 'H1': _resample(win_df, 60), 'H4': _resample(win_df, 240)}
        direction, _ = vote_all(frames, min_votes=2)
        if direction == 0: continue

        # Confluence scoring
        score, reasons = compute_confluence_score(direction, i, c, h, l, v, indicators)
        if score < min_score: continue

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

        trades.append({"r": r_mult, "score": score, "outcome": "W" if r_mult > 0 else "L"})

    if not trades:
        return None

    r_arr = np.array([t["r"] for t in trades])
    n_tr = len(trades)
    wins = int(np.sum(r_arr > 0))
    wr = wins / n_tr
    avg_r = float(np.mean(r_arr))
    std = float(np.std(r_arr, ddof=1)) if n_tr > 1 else 1.0
    sharpe = avg_r / std if std > 0 else 0
    run = best = 0
    for r in r_arr:
        if r <= 0: run += 1; best = max(best, run)
        else: run = 0

    if verbose:
        tag = "V" if wr >= 0.70 else "-" if wr >= 0.50 else "X"
        print(f"[{tag}] {symbol:8s} min_score={min_score} trades={n_tr:4d} WR={wr*100:5.1f}% avgR={avg_r:+.3f} sharpe={sharpe:+.2f} maxCL={best}")

    return {"symbol": symbol, "trades": n_tr, "wins": wins, "win_rate": wr, "avg_r": avg_r, "sharpe": sharpe, "maxCL": best, "min_score": min_score}


def main():
    print("=" * 70)
    print("Phase 1: Diagnosing trade patterns")
    print("=" * 70)

    for sym in ["GBPUSD", "XAGUSD", "XTIUSD"]:
        diagnose_pair(sym, bars=5000)

    print("\n" + "=" * 70)
    print("Phase 3: Confluence-scored backtest — finding optimal min_score")
    print("=" * 70)
    print(f"\n{'Pair':10s} {'minSc':>5s} {'Trades':>6s} {'WR%':>6s} {'AvgR':>7s} {'Sharpe':>7s} {'MaxCL':>5s}")
    print("-" * 70)

    pairs = ["XAGUSD", "GBPUSD", "AUDUSD", "USDCHF", "NZDUSD", "EURUSD", "USDJPY", "USDCAD", "XTIUSD"]
    for min_score in [50, 55, 60, 65, 70, 75, 80]:
        print(f"\n--- min_score = {min_score} ---")
        for sym in pairs:
            run_confluence_backtest(sym, bars=5000, min_score=min_score)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
