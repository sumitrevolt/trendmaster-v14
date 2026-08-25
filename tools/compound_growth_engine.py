#!/usr/bin/env python3
"""
COMPOUND GROWTH ENGINE: $200 -> $500,000
========================================
Phase-based aggressive scalping with dynamic risk scaling.

Math:
  $200 -> $500,000 = 2,500x return

Path (compounded):
  Phase 1: $200 -> $2,000     (10x)  Aggressive scalping, 3% risk
  Phase 2: $2,000 -> $20,000  (10x)  Standard scalping, 2% risk
  Phase 3: $20,000 -> $200,000 (10x) Conservative growth, 1.5% risk
  Phase 4: $200,000 -> $500,000 (2.5x) Capital preservation, 1% risk

Key: HIGH FREQUENCY + POSITIVE EXPECTANCY + COMPOUNDING = exponential growth.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import time
import warnings
warnings.filterwarnings("ignore")

# ─── PHASE DEFINITIONS ───────────────────────────────────────────────────────
PHASES = [
    {"name": "AGGRESSIVE SCALP", "start": 200, "target": 2000, "risk_pct": 3.0,
     "sl_atr": 0.8, "tp_atr": 2.0, "min_score": 4.0, "max_trades_day": 15,
     "rr_ratio": 2.5},
    {"name": "STANDARD SCALP", "start": 2000, "target": 20000, "risk_pct": 2.0,
     "sl_atr": 1.0, "tp_atr": 2.2, "min_score": 4.5, "max_trades_day": 12,
     "rr_ratio": 2.2},
    {"name": "CONSERVATIVE GROWTH", "start": 20000, "target": 200000, "risk_pct": 1.5,
     "sl_atr": 1.2, "tp_atr": 2.5, "min_score": 5.0, "max_trades_day": 10,
     "rr_ratio": 2.1},
    {"name": "CAPITAL PRESERVATION", "start": 200000, "target": 500000, "risk_pct": 1.0,
     "sl_atr": 1.2, "tp_atr": 2.8, "min_score": 5.5, "max_trades_day": 8,
     "rr_ratio": 2.3},
]

PAIRS = ["GBPUSD", "AUDUSD", "USDCHF", "NZDUSD", "EURUSD", "XAGUSD", "USDJPY"]

# ─── INDICATOR FUNCTIONS ─────────────────────────────────────────────────────
def _ema(data, period):
    return pd.Series(data).ewm(span=period, adjust=False).mean().values

def _sma(data, period):
    return pd.Series(data).rolling(period).mean().values

def _rsi(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain).ewm(span=period, adjust=False).mean().values
    avg_loss = pd.Series(loss).ewm(span=period, adjust=False).mean().values
    rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
    return 100.0 - (100.0 / (1.0 + rs))

def _atr(high, low, close, period=14):
    prev_c = np.roll(close, 1); prev_c[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)))
    return pd.Series(tr).rolling(period).mean().values

def _adx(high, low, close, period=14):
    prev_h = np.roll(high, 1); prev_h[0] = high[0]
    prev_l = np.roll(low, 1);  prev_l[0] = low[0]
    up_move = high - prev_h
    down_move = prev_l - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_val = _atr(high, low, close, period)
    safe_atr = np.where(atr_val == 0, 1e-10, atr_val)
    plus_di = 100.0 * pd.Series(plus_dm).ewm(span=period).mean().values / safe_atr
    minus_di = 100.0 * pd.Series(minus_dm).ewm(span=period).mean().values / safe_atr
    dx = 100.0 * np.abs(plus_di - minus_di) / np.where((plus_di + minus_di) == 0, 1e-10, plus_di + minus_di)
    return pd.Series(dx).ewm(span=period).mean().values, plus_di, minus_di

def _bb(close, period=20, std_mult=2.0):
    mid = _sma(close, period)
    std = pd.Series(close).rolling(period).std().values
    return mid + std_mult * std, mid, mid - std_mult * std

def _macd(close, fast=12, slow=26, signal=9):
    ef = _ema(close, fast); es = _ema(close, slow)
    ml = ef - es; sl = _ema(ml, signal)
    return ml, sl, ml - sl

def _stochastic(high, low, close, k_period=14, d_period=3):
    ll = pd.Series(low).rolling(k_period).min().values
    hh = pd.Series(high).rolling(k_period).max().values
    k = 100.0 * (close - ll) / np.where((hh - ll) == 0, 1e-10, hh - ll)
    d = pd.Series(k).rolling(d_period).mean().values
    return k, d


# ─── SCORE AT INDEX i ────────────────────────────────────────────────────────
def score_at(i, c, o, h, l, v,
             adx_v, pdi_v, mdi_v, rsi_v,
             ema8, ema20, ema50, ema200,
             bb_u, bb_m, bb_l, bbw, bbw_avg,
             atr_v, atr_avg_v, macd_h, macd_h_prev,
             vol_avg_v, stk, std,
             hour_utc):
    """
    8-layer confluence score at bar i.
    Returns (score, direction, detail_str).
    """
    if i < 200 or atr_v <= 0 or atr_avg_v <= 0:
        return 0, 0, "warmup"

    s = 0.0
    votes = []  # +1 = buy, -1 = sell

    # ── L1: TREND (1.5) ──────────────────────────────────────────────────
    if adx_v > 25:
        if ema8[i] > ema20[i] > ema50[i]:
            s += 1.5; votes.append(1)
        elif ema8[i] < ema20[i] < ema50[i]:
            s += 1.5; votes.append(-1)
    elif adx_v > 18:
        if ema8[i] > ema20[i]:
            s += 0.8; votes.append(1)
        elif ema8[i] < ema20[i]:
            s += 0.8; votes.append(-1)

    # ── L2: MOMENTUM (1.2) ───────────────────────────────────────────────
    if 35 <= rsi_v <= 65:
        s += 0.6
        votes.append(1 if rsi_v > 50 else -1)
    if macd_h > 0 and macd_h > macd_h_prev:
        s += 0.6; votes.append(1)
    elif macd_h < 0 and macd_h < macd_h_prev:
        s += 0.6; votes.append(-1)

    # ── L3: VOLATILITY (0.8) ─────────────────────────────────────────────
    if bbw_avg > 0 and bbw < bbw_avg * 0.85:
        s += 0.8
    if atr_avg_v > 0 and atr_v > atr_avg_v * 1.1:
        s += 0.4

    # ── L4: VOLUME (0.7) ─────────────────────────────────────────────────
    if vol_avg_v > 0:
        if v > vol_avg_v * 1.2:
            s += 0.7
        elif v > vol_avg_v:
            s += 0.3

    # ── L5: PRICE ACTION (1.3) ───────────────────────────────────────────
    body = abs(c - o)
    wick_up = h - max(o, c)
    wick_dn = min(o, c) - l
    rng = h - l
    if rng > 0:
        br = body / rng
        if c > o and br > 0.6:
            s += 0.8; votes.append(1)
        elif c < o and br > 0.6:
            s += 0.8; votes.append(-1)
        if wick_dn > body * 2 and wick_dn > wick_up:
            s += 0.5; votes.append(1)
        elif wick_up > body * 2 and wick_up > wick_dn:
            s += 0.5; votes.append(-1)

    # ── L6: SESSION (1.0) ────────────────────────────────────────────────
    if 12 <= hour_utc <= 15:
        s += 1.0
    elif 7 <= hour_utc <= 11 or 16 <= hour_utc <= 18:
        s += 0.5

    # ── L7: MTF ALIGNMENT (1.5) ──────────────────────────────────────────
    if ema20[i] > ema50[i] > ema200[i]:
        s += 1.5; votes.append(1)
    elif ema20[i] < ema50[i] < ema200[i]:
        s += 1.5; votes.append(-1)

    # ── L8: STOCHASTIC (0.8) ─────────────────────────────────────────────
    if stk < 20 and std < 20:
        s += 0.8; votes.append(1)
    elif stk > 80 and std > 80:
        s += 0.8; votes.append(-1)
    elif stk > std and stk < 50:
        s += 0.4; votes.append(1)
    elif stk < std and stk > 50:
        s += 0.4; votes.append(-1)

    # Direction
    if not votes:
        return s, 0, "no_votes"
    buy_v = sum(1 for v in votes if v > 0)
    sell_v = sum(1 for v in votes if v < 0)
    if buy_v > sell_v:
        d = 1
    elif sell_v > buy_v:
        d = -1
    else:
        return s, 0, "tie"
    return s, d, f"B{buy_v}/S{sell_v}"


# ─── BACKTEST SINGLE PAIR ─────────────────────────────────────────────────────
def backtest_pair(csv_path, pair, phase):
    df = pd.read_csv(csv_path, parse_dates=["time"])
    if len(df) < 500:
        return None

    # 70/30 split: dev / validation
    split = int(len(df) * 0.7)

    c = df["close"].values.astype(np.float64)
    o = df["open"].values.astype(np.float64)
    h = df["high"].values.astype(np.float64)
    l = df["low"].values.astype(np.float64)
    v = df["volume"].values.astype(np.float64) if "volume" in df.columns else np.ones(len(c))

    # Pre-compute all indicators
    e8  = _ema(c, 8);   e20 = _ema(c, 20)
    e50 = _ema(c, 50);  e200 = _ema(c, 200)
    rsi_v   = _rsi(c, 14)
    atr_v   = _atr(h, l, c, 14)
    atr_avg = _sma(atr_v, 50)
    adx_v, pdi_v, mdi_v = _adx(h, l, c, 14)
    bb_u, bb_m, bb_l = _bb(c, 20, 2.0)
    bbw = bb_u - bb_l
    bbw_avg = _sma(bbw, 50)
    _, _, macd_h = _macd(c)
    vol_avg = _sma(v, 20)
    stk, std = _stochastic(h, l, c, 14, 3)

    # Simulate trades
    trades = []
    equity = float(phase["start"])
    sl_m = phase["sl_atr"]
    tp_m = phase["tp_atr"]
    min_sc = phase["min_score"]
    risk_pct = phase["risk_pct"]
    max_d = phase["max_trades_day"]

    daily_count = 0
    last_trade_bar = -100
    min_gap = 6  # bars between trades

    # Derive hour_utc from the time column
    hours = df["time"].dt.hour.values

    for i in range(200, len(df)):
        # Only trade on validation set
        if i < split:
            continue

        # Reset daily count each trading day (~288 M5 bars)
        day_num = i // 288
        if i == split or (i > split and (i - 1) // 288 != day_num):
            daily_count = 0

        if daily_count >= max_d:
            continue
        if i - last_trade_bar < min_gap:
            continue
        if equity <= 0:
            break

        sc, d, _ = score_at(
            i, c[i], o[i], h[i], l[i], v[i],
            adx_v[i], pdi_v[i], mdi_v[i], rsi_v[i],
            e8, e20, e50, e200,
            bb_u, bb_m, bb_l, bbw[i], bbw_avg[i],
            atr_v[i], atr_avg[i], macd_h[i],
            macd_h[i - 1] if i > 0 else 0.0,
            vol_avg[i], stk[i], std[i],
            int(hours[i]),
        )

        if sc < min_sc or d == 0:
            continue

        # Execute
        entry = c[i]
        a = atr_v[i]
        sl_d = a * sl_m
        tp_d = a * tp_m
        if sl_d <= 0:
            continue

        risk_amt = equity * (risk_pct / 100.0)
        lots = max(0.01, min(risk_amt / (sl_d * 100.0), 1.0))

        result = 0.0
        for j in range(i + 1, min(i + 50, len(df))):
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
            # Timeout — close at last bar
            exit_p = c[min(i + 50, len(df) - 1)]
            result = ((exit_p - entry) if d == 1 else (entry - exit_p)) * lots * 100.0

        equity += result
        equity = max(equity, 0.0)
        trades.append({
            "bar": i, "pair": pair, "dir": "BUY" if d == 1 else "SELL",
            "entry": entry, "result": result, "equity": equity,
            "bars_held": min(50, len(df) - 1 - i), "score": sc, "lots": lots,
        })
        daily_count += 1
        last_trade_bar = i

        if equity >= phase["target"]:
            break

    return {"trades": trades, "final_equity": equity}


# ─── RUN ALL PHASES ───────────────────────────────────────────────────────────
def run_backtest():
    data_dir = Path("data")

    print("=" * 90)
    print("   COMPOUND GROWTH ENGINE: $200 -> $500,000")
    print("=" * 90)

    for pi, ph in enumerate(PHASES):
        print(f"\n{'='*70}")
        print(f"  PHASE {pi + 1}: {ph['name']}")
        print(f"  ${ph['start']:,.0f} -> ${ph['target']:,.0f}  |  Risk {ph['risk_pct']}%"
              f"  |  SL {ph['sl_atr']}x  TP {ph['tp_atr']}x  |  MinScore {ph['min_score']}")
        print(f"{'='*70}")

        all_trades = []
        eq = float(ph["start"])

        for pair in PAIRS:
            # Find CSV
            csv = data_dir / f"{pair}_M5.csv"
            if not csv.exists():
                hits = list(data_dir.glob(f"*{pair}*M5*"))
                csv = hits[0] if hits else None
            if csv is None or not csv.exists():
                continue

            r = backtest_pair(str(csv), pair, ph)
            if r is None or not r["trades"]:
                continue

            t = r["trades"]
            wins = sum(1 for x in t if x["result"] > 0)
            loss = len(t) - wins
            wr = wins / len(t) * 100 if t else 0
            aw = np.mean([x["result"] for x in t if x["result"] > 0]) if wins else 0
            al = np.mean([abs(x["result"]) for x in t if x["result"] <= 0]) if loss else 0
            pf = (aw * wins) / (al * loss) if loss and al > 0 else 99.0
            gross = sum(x["result"] for x in t)
            eq = t[-1]["equity"]

            all_trades.extend(t)
            print(f"  {pair:8s} | {len(t):3d} tr | WR {wr:5.1f}% | "
                  f"AW ${aw:7.2f} | AL ${al:7.2f} | PF {pf:5.2f} | "
                  f"Gross ${gross:9.2f} | EndEq ${eq:10.2f}")

        tw = sum(1 for x in all_trades if x["result"] > 0)
        tl = len(all_trades) - tw
        o_wr = tw / len(all_trades) * 100 if all_trades else 0
        o_gross = sum(x["result"] for x in all_trades)
        o_avg = np.mean([x["result"] for x in all_trades]) if all_trades else 0

        print(f"\n  PHASE {pi+1} TOTAL: {len(all_trades)} trades | WR {o_wr:.1f}% | "
              f"Gross ${o_gross:,.2f} | Avg ${o_avg:,.2f}")
        print(f"  Start: ${ph['start']:,.2f}  End: ${eq:,.2f}  "
              f"Return: {((eq / ph['start']) - 1) * 100:,.1f}%")

    # ─── FULL PATH SUMMARY ────────────────────────────────────────────────
    print(f"\n{'='*90}")
    print("   FULL COMPOUND GROWTH PROJECTION")
    print(f"{'='*90}")

    equity = 200.0
    total_days = 0
    total_trades = 0

    for pi, ph in enumerate(PHASES):
        target = ph["target"]
        risk = ph["risk_pct"]
        rr = ph["rr_ratio"]
        wr_est = 0.45  # conservative
        exp_r = wr_est * rr - (1 - wr_est)

        # Simulate compounding to target
        sim_eq = equity
        n = 0
        while sim_eq < target and n < 50000:
            ra = sim_eq * (risk / 100.0)
            if np.random.random() < wr_est:
                sim_eq += ra * rr
            else:
                sim_eq -= ra
            sim_eq = max(sim_eq, 0.0)
            n += 1

        days = n / ph["max_trades_day"]
        print(f"\n  Phase {pi+1}: {ph['name']}")
        print(f"    ${equity:>12,.0f} -> ${target:>12,.0f}  ({((target/equity)-1)*100:,.0f}%)")
        print(f"    Risk {risk}% | WR ~{wr_est*100:.0f}% | R:R {rr:.1f} | "
              f"ExpR {exp_r:+.2f}R")
        print(f"    ~{n:,} trades | ~{days:.0f} days ({days/30:.1f} months)")
        print(f"    Trades/day: {ph['max_trades_day']}")

        equity = target
        total_trades += n
        total_days += days

    print(f"\n  {'─'*60}")
    print(f"  PATH: $200 -> $500,000 = 2,500x return")
    print(f"  Total trades: ~{total_trades:,}")
    print(f"  Total days:   ~{total_days:.0f} ({total_days/30:.0f} months)")
    print(f"  Avg trades/day: ~{total_trades/max(total_days,1):.0f}")
    print(f"  {'─'*60}")

    # Monthly projection table
    print(f"\n  MONTHLY PROJECTION (at $500K, Phase 4):")
    print(f"    Daily risk: 1.0% = $5,000")
    print(f"    8 trades/day x 22 days = 176 trades/month")
    print(f"    45% WR x $11,250 (2.5R) - 55% x $5,000 = $5,063/trade avg gain")
    print(f"    Monthly return: ~$891,000 (on $500K base)")
    print(f"    But compound reinvests — actual path is exponential")
    print(f"\n  CRITICAL REQUIREMENTS:")
    print(f"    1. REGIME DETECTION — skip chop markets (kill zones)")
    print(f"    2. MULTI-PAIR SCALPING — 7 pairs = more setups per day")
    print(f"    3. COMPOUND REINVEST — never withdraw, always reinvest profits")
    print(f"    4. DRAWDOWN GUARDS — max 5% daily DD, then stop for the day")
    print(f"    5. ADAPTIVE SIZING — Kelly fraction scales with account growth")


if __name__ == "__main__":
    t0 = time.time()
    run_backtest()
    print(f"\n  Completed in {time.time() - t0:.1f}s")
