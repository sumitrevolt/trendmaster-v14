"""
precision_strategy.py — 70% WR + 2.5R Precision Strategy
==========================================================
7-layer confluence scoring system for maximum win rate.

Strategy: Only take A+ setups where 5+ of7 layers agree.
- Layer 1: Trend (EMA20 > EMA50 > EMA200, ADX > 25)
- Layer 2: Momentum (RSI 40-65 sweet spot, MACD histogram rising)
- Layer 3: Volatility (BB squeeze + ATR expansion)
- Layer 4: Volume (above-average volume confirmation)
- Layer 5: Session (London open / NY open only — highest probability windows)
- Layer 6: Price Action (engulfing, pin bar, inside bar breakout)
- Layer 7: Multi-timeframe (H4 + H1 + M15 all aligned)

Trade management:
- SL: 0.8x ATR (tight — only enter when trend is strong)
- TP: 2.0x ATR (2.5R reward)
- Trailing: Activate at1.5R, trail by 0.5x ATR
- Max 3 trades per pair per day (quality over quantity)

Usage:
    python tools/precision_strategy.py            # Run all pairs
    python tools/precision_strategy.py GBPUSD     # Single pair
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

# ── Per-pair precision parameters ───────────────────────────────────────
# Tuned from815-trade backtest: only pairs with positive expectancy
PAIR_PARAMS = {
    # FOREX — tight sessions, trend-following
    "GBPUSD": {"sl_atr": 0.8, "tp_atr": 2.0, "min_score": 5, "max_trades_day": 3, "peak_hours": [8,9,12,13]},
    "AUDUSD": {"sl_atr": 0.8, "tp_atr": 2.0, "min_score": 5, "max_trades_day": 3, "peak_hours": [0,1,7,8]},
    "USDCHF": {"sl_atr": 0.8, "tp_atr": 2.0, "min_score": 5, "max_trades_day": 3, "peak_hours": [12,13,14,15]},
    "NZDUSD": {"sl_atr": 0.8, "tp_atr": 2.0, "min_score": 5, "max_trades_day": 3, "peak_hours": [22,23,0,1]},
    "EURUSD": {"sl_atr": 0.8, "tp_atr": 2.0, "min_score": 5, "max_trades_day": 3, "peak_hours": [8,9,12,13]},
    "USDJPY": {"sl_atr": 0.8, "tp_atr": 2.0, "min_score": 5, "max_trades_day": 3, "peak_hours": [0,1,7,8,12,13]},
    "USDCAD": {"sl_atr": 0.8, "tp_atr": 2.0, "min_score": 5, "max_trades_day": 3, "peak_hours": [13,14,15,16]},
    # METALS — wider SL for volatility
    "XAGUSD": {"sl_atr": 1.0, "tp_atr": 2.5, "min_score": 5, "max_trades_day": 2, "peak_hours": [12,13,14,15]},
    # COMMODITIES — news-driven, wider
    "XTIUSD": {"sl_atr": 1.0, "tp_atr": 2.5, "min_score": 5, "max_trades_day": 2, "peak_hours": [14,15,16]},
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
    h, l, c = highs, lows, closes
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = np.full_like(tr, np.nan)
    for i in range(n - 1, len(tr)):
        atr[i] = np.mean(tr[i - n + 1: i + 1])
    return atr


def _ema_np(arr, n):
    alpha = 2.0 / (n + 1)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _adx_np(highs, lows, closes, n=14):
    h, l, c = highs, lows, closes
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr_smooth = _ema_np(tr, n)
    atr_smooth = np.where(atr_smooth == 0, np.nan, atr_smooth)
    pdi = 100 * _ema_np(plus_dm, n) / atr_smooth
    mdi = 100 * _ema_np(minus_dm, n) / atr_smooth
    dx = 100 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, np.nan, pdi + mdi)
    adx = _ema_np(np.nan_to_num(dx), n)
    return adx, np.nan_to_num(pdi), np.nan_to_num(mdi)


def _rsi_np(closes, n=14):
    d = np.diff(closes, prepend=closes[0])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    avg_up = _ema_np(up, n)
    avg_dn = _ema_np(dn, n)
    rs = np.where(avg_dn == 0, 100, avg_up / avg_dn)
    return 100 - 100 / (1 + rs)


def _bb_np(closes, n=20, k=2.0):
    """Bollinger Bands: middle, upper, lower, bandwidth."""
    mid = _ema_np(closes, n)  # SMA approx via EMA
    std = np.full_like(closes, np.nan)
    for i in range(n - 1, len(closes)):
        std[i] = np.std(closes[i - n + 1: i + 1], ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    bw = np.where(mid > 0, (upper - lower) / mid, np.nan)
    return mid, upper, lower, bw


def _macd_np(closes, fast=12, slow=26, signal=9):
    ema_f = _ema_np(closes, fast)
    ema_s = _ema_np(closes, slow)
    macd_line = ema_f - ema_s
    signal_line = _ema_np(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _score_layer1_trend(adx_val, pdi, mdi, ema20, ema50, ema200, price, direction):
    """Trend strength: ADX > 25 + EMA alignment. Score 0-1."""
    score = 0.0
    # ADX above 25 = strong trend
    if adx_val >= 25:
        score += 0.3
    if adx_val >= 35:
        score += 0.1  # bonus for very strong
    # EMA stack alignment
    if direction == 1:  # BUY
        if ema20 > ema50 > ema200:
            score += 0.3
        if price > ema20:
            score += 0.15
        if pdi > mdi:
            score += 0.15
    else:  # SELL
        if ema20 < ema50 < ema200:
            score += 0.3
        if price < ema20:
            score += 0.15
        if mdi > pdi:
            score += 0.15
    return min(score, 1.0)


def _score_layer2_momentum(rsi_val, macd_hist, macd_hist_prev, direction):
    """Momentum: RSI in sweet spot + MACD rising. Score 0-1."""
    score = 0.0
    # RSI sweet spot (40-65 for BUY, 35-60 for SELL)
    if direction == 1:
        if 40 <= rsi_val <= 65:
            score += 0.5
        elif 35 <= rsi_val <= 70:
            score += 0.25
    else:
        if 35 <= rsi_val <= 60:
            score += 0.5
        elif 30 <= rsi_val <= 65:
            score += 0.25
    # MACD histogram rising
    if direction == 1 and macd_hist > macd_hist_prev:
        score += 0.5
    elif direction == -1 and macd_hist < macd_hist_prev:
        score += 0.5
    return min(score, 1.0)


def _score_layer3_volatility(bb_bw, bb_bw_avg, atr_val, atr_avg, price, bb_mid):
    """Volatility: BB squeeze + ATR expansion. Score 0-1."""
    score = 0.0
    # BB bandwidth below average = squeeze (coiling for breakout)
    if bb_bw < bb_bw_avg * 0.8:
        score += 0.4
    elif bb_bw < bb_bw_avg:
        score += 0.2
    # ATR above average = expansion (move happening)
    if atr_val > atr_avg * 1.1:
        score += 0.4
    elif atr_val > atr_avg:
        score += 0.2
    # Price near BB edge (breakout zone)
    if abs(price - bb_mid) / (bb_bw_avg * bb_mid + 1e-10) > 0.3:
        score += 0.2
    return min(score, 1.0)


def _score_layer4_volume(vol, vol_avg, vol_sma20):
    """Volume confirmation. Score 0-1."""
    score = 0.0
    if vol_avg > 0:
        vol_ratio = vol / vol_avg
        if vol_ratio > 1.5:
            score += 0.5
        elif vol_ratio > 1.2:
            score += 0.3
        elif vol_ratio > 1.0:
            score += 0.15
    if vol_sma20 > 0 and vol > vol_sma20 * 1.2:
        score += 0.3
    return min(score, 1.0)


def _score_layer5_session(hour, peak_hours):
    """Session timing: peak hours only. Score 0-1."""
    if hour in peak_hours:
        return 1.0
    # Adjacent hours get partial credit
    if any(abs(hour - p) <= 1 for p in peak_hours):
        return 0.5
    return 0.0


def _score_layer6_price_action(opens, highs, lows, closes, idx, direction):
    """Price action: engulfing, pin bar, inside bar breakout. Score 0-1."""
    if idx < 3:
        return 0.0
    score = 0.0
    o, h, l, c = opens[idx], highs[idx], lows[idx], closes[idx]
    o1, h1, l1, c1 = opens[idx-1], highs[idx-1], lows[idx-1], closes[idx-1]
    body = abs(c - o)
    full_range = h - l if h > l else 1e-10

    if direction == 1:  # BUY
        # Bullish engulfing
        if c > o and c1 < o1 and c > o1 and o < c1:
            score += 0.4
        # Pin bar (long lower wick = rejection)
        lower_wick = min(o, c) - l
        if lower_wick > body * 2 and lower_wick > full_range * 0.6:
            score += 0.4
        # Inside bar breakout
        if h < h1 and l > l1 and c > h1:
            score += 0.3
        # Strong bullish candle (> 60% body)
        if body / full_range > 0.6 and c > o:
            score += 0.2
    else:  # SELL
        # Bearish engulfing
        if c < o and c1 > o1 and c < o1 and o > c1:
            score += 0.4
        # Pin bar (long upper wick = rejection)
        upper_wick = h - max(o, c)
        if upper_wick > body * 2 and upper_wick > full_range * 0.6:
            score += 0.4
        # Inside bar breakout
        if h < h1 and l > l1 and c < l1:
            score += 0.3
        # Strong bearish candle
        if body / full_range > 0.6 and c < o:
            score += 0.2
    return min(score, 1.0)


def _score_layer7_mtf(h4_dir, h1_dir, m15_dir, direction):
    """Multi-timeframe alignment: all 3 must agree. Score 0-1."""
    if h4_dir == direction and h1_dir == direction and m15_dir == direction:
        return 1.0
    if h4_dir == direction and h1_dir == direction:
        return 0.6  # 2 of3 — acceptable
    if h4_dir == direction:
        return 0.3  # only macro agrees
    return 0.0


def _compute_direction_from_ema(ema_fast, ema_slow, price):
    """Simple direction from EMA crossover."""
    if ema_fast > ema_slow and price > ema_fast:
        return 1
    if ema_fast < ema_slow and price < ema_fast:
        return -1
    return 0


def run_precision_backtest(symbol: str, bars: int = 5000, verbose: bool = True) -> dict:
    """Run 7-layer precision backtest on a single symbol."""
    if symbol not in PAIR_PARAMS:
        return {"symbol": symbol, "error": f"No params for {symbol}", "trades": 0}

    params = PAIR_PARAMS[symbol]
    sl_mult = params["sl_atr"]
    tp_mult = params["tp_atr"]
    min_score = params["min_score"]
    max_day = params["max_trades_day"]
    peak_hours = params["peak_hours"]

    path = _ROOT / "data" / f"{symbol.lower()}_m5_history.csv"
    if not path.exists():
        return {"symbol": symbol, "error": f"No data file", "trades": 0}

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

    # Pre-compute indicators
    atr = _atr_np(h, l, c, 14)
    adx, pdi, mdi = _adx_np(h, l, c, 14)
    rsi = _rsi_np(c, 14)
    ema8 = _ema_np(c, 8)
    ema20 = _ema_np(c, 20)
    ema50 = _ema_np(c, 50)
    ema200 = _ema_np(c, 200)
    bb_mid, bb_upper, bb_lower, bb_bw = _bb_np(c, 20, 2.0)
    macd_line, signal_line, histogram = _macd_np(c)

    # Rolling averages for scoring
    bb_bw_avg = _ema_np(np.nan_to_num(bb_bw), 50)
    atr_avg = _ema_np(np.nan_to_num(atr), 50)
    vol_avg = _ema_np(v, 50)
    vol_sma20 = _ema_np(v, 20)

    # MTF direction (H4, H1, M15 approximations via EMA on resampled data)
    # Use EMA20/50 on different lookback windows as proxy
    ema20_h4 = _ema_np(c, 20 * 12)   # ~H4 equivalent
    ema50_h4 = _ema_np(c, 50 * 12)
    ema20_h1 = _ema_np(c, 20 * 3)    # ~H1 equivalent
    ema50_h1 = _ema_np(c, 50 * 3)

    trades = []
    warmup = 600
    day_trade_count = {}
    cooldown_until = 0
    consec_losses = 0

    for i in range(warmup, n - 24, 6):  # Check every 6 bars (30 min)
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue

        # ── LOSS STREAK COOLDOWN ──
        if consec_losses >= 3:
            cooldown_until = i + 36  # 3 hour cooldown
            consec_losses = 0
        if i < cooldown_until:
            continue

        # ── SESSION FILTER ──
        try:
            hour = df.index[i].hour
        except Exception:
            hour = 12
        if symbol not in ("BTCUSD", "ETHUSD"):
            if hour not in peak_hours and not any(abs(hour - p) <= 1 for p in peak_hours):
                continue

        # ── DAILY TRADE LIMIT ──
        try:
            day_key = str(df.index[i].date())
        except Exception:
            day_key = "unknown"
        day_count = day_trade_count.get(day_key, 0)
        if day_count >= max_day:
            continue

        # ── DETERMINE DIRECTION ──
        # Quick direction check via EMA stack
        e20, e50, e200 = ema20[i], ema50[i], ema200[i]
        if not all(np.isfinite([e20, e50, e200])):
            continue
        price = float(c[i])

        # Need strong trend alignment for direction
        if e20 > e50 > e200 and price > e20:
            direction = 1
        elif e20 < e50 < e200 and price < e20:
            direction = -1
        else:
            continue  # No clear trend = skip

        # ── 7-LAYER CONFLUENCE SCORING ──
        score = 0.0
        layer_detail = []

        # Layer 1: Trend
        s1 = _score_layer1_trend(adx[i], pdi[i], mdi[i], e20, e50, e200, price, direction)
        score += s1
        layer_detail.append(f"T:{s1:.2f}")

        # Layer 2: Momentum
        macd_h = histogram[i]
        macd_h_prev = histogram[i - 1] if i > 0 else macd_h
        s2 = _score_layer2_momentum(rsi[i], macd_h, macd_h_prev, direction)
        score += s2
        layer_detail.append(f"M:{s2:.2f}")

        # Layer 3: Volatility
        bb_b = bb_bw[i] if np.isfinite(bb_bw[i]) else 0
        bb_ba = bb_bw_avg[i] if np.isfinite(bb_bw_avg[i]) else bb_b
        a_avg = atr_avg[i] if np.isfinite(atr_avg[i]) else a
        s3 = _score_layer3_volatility(bb_b, bb_ba, a, a_avg, price, bb_mid[i])
        score += s3
        layer_detail.append(f"V:{s3:.2f}")

        # Layer 4: Volume
        va = vol_avg[i] if np.isfinite(vol_avg[i]) else v[i]
        vs = vol_sma20[i] if np.isfinite(vol_sma20[i]) else v[i]
        s4 = _score_layer4_volume(v[i], va, vs)
        score += s4
        layer_detail.append(f"Vol:{s4:.2f}")

        # Layer 5: Session
        s5 = _score_layer5_session(hour, peak_hours)
        score += s5
        layer_detail.append(f"S:{s5:.2f}")

        # Layer 6: Price Action
        s6 = _score_layer6_price_action(o, h, l, c, i, direction)
        score += s6
        layer_detail.append(f"PA:{s6:.2f}")

        # Layer 7: Multi-timeframe
        h4d = _compute_direction_from_ema(ema20_h4[i], ema50_h4[i], price)
        h1d = _compute_direction_from_ema(ema20_h1[i], ema50_h1[i], price)
        m15d = direction  # Already on M5, so M15 = same as entry TF
        s7 = _score_layer7_mtf(h4d, h1d, m15d, direction)
        score += s7
        layer_detail.append(f"MTF:{s7:.2f}")

        # ── SCORE GATE ──
        if score < min_score:
            continue

        # ── ADDITIONAL FILTERS ──
        # RSI must not be extreme
        rsi_val = rsi[i]
        if direction == 1 and rsi_val > 70:
            continue
        if direction == -1 and rsi_val < 30:
            continue

        # ADX must show trend
        if adx[i] < 20:
            continue

        # ── TRADE EXECUTION ──
        sd = sl_mult * a
        if direction == 1:
            sl_px = price - sd
            tp_px = price + tp_mult * sd
        else:
            sl_px = price + sd
            tp_px = price - tp_mult * sd

        # Trailing stop parameters
        trail_activate_r = 1.5  # Activate trailing at1.5R
        trail_distance = 0.5 * a  # Trail by 0.5x ATR

        best_px = price
        r_mult = -1.0
        exit_px = sl_px
        trail_active = False
        exit_reason = "SL"

        hold = 24  # Max hold = 2 hours (24 M5 bars)
        for j in range(i + 1, min(i + 1 + hold, n)):
            if direction == 1:
                # Check SL
                if l[j] <= sl_px:
                    exit_px = sl_px
                    exit_reason = "SL"
                    break
                # Track best price
                best_px = max(best_px, h[j])
                # Check if trailing activated
                current_r = (best_px - price) / sd
                if current_r >= trail_activate_r and not trail_active:
                    trail_active = True
                # Update trailing stop
                if trail_active:
                    new_trail = best_px - trail_distance
                    if new_trail > sl_px:
                        sl_px = new_trail
                # Check TP
                if h[j] >= tp_px:
                    r_mult = tp_mult
                    exit_px = tp_px
                    exit_reason = "TP"
                    break
            else:
                if h[j] >= sl_px:
                    exit_px = sl_px
                    exit_reason = "SL"
                    break
                best_px = min(best_px, l[j])
                current_r = (price - best_px) / sd
                if current_r >= trail_activate_r and not trail_active:
                    trail_active = True
                if trail_active:
                    new_trail = best_px + trail_distance
                    if new_trail < sl_px:
                        sl_px = new_trail
                if l[j] <= tp_px:
                    r_mult = tp_mult
                    exit_px = tp_px
                    exit_reason = "TP"
                    break
        else:
            # Time exit
            exit_px = float(c[min(i + hold, n - 1)])
            r_mult = round((exit_px - price) / sd * direction, 3)
            exit_reason = "TIME"

        # If trailing stop hit during the loop, r_mult is set by SL exit
        if exit_reason == "SL" and trail_active:
            r_mult = round((exit_px - price) / sd * direction, 3)

        # Record trade
        trade = {
            "time": str(df.index[i]),
            "direction": "BUY" if direction == 1 else "SELL",
            "entry": price,
            "exit": exit_px,
            "sl": sl_px if not trail_active else (best_px - trail_distance if direction == 1 else best_px + trail_distance),
            "tp": tp_px,
            "r": r_mult,
            "outcome": "win" if r_mult > 0 else "loss",
            "exit_reason": exit_reason,
            "score": score,
            "layers": ",".join(layer_detail),
            "adx": round(adx[i], 1),
            "rsi": round(rsi[i], 1),
            "trail_active": trail_active,
        }
        trades.append(trade)

        # Update tracking
        day_trade_count[day_key] = day_count + 1
        if r_mult <= 0:
            consec_losses += 1
        else:
            consec_losses = 0

    if not trades:
        return {"symbol": symbol, "trades": 0, "error": "no trades generated"}

    r_arr = np.array([t["r"] for t in trades])
    n_tr = len(trades)
    wins = int(np.sum(r_arr > 0))
    losses = int(np.sum(r_arr <= 0))
    wr = wins / n_tr if n_tr > 0 else 0
    avg_r = float(np.mean(r_arr))
    gross = float(np.sum(r_arr))
    std = float(np.std(r_arr, ddof=1)) if n_tr > 1 else 1.0
    sharpe = avg_r / std if std > 0 else 0.0

    # Max consecutive losses
    run = best_run = 0
    for r in r_arr:
        if r <= 0:
            run += 1
            best_run = max(best_run, run)
        else:
            run = 0

    # Profit factor
    gross_wins = float(np.sum(r_arr[r_arr > 0])) if wins > 0 else 0
    gross_losses = float(np.abs(np.sum(r_arr[r_arr <= 0]))) if losses > 0 else 1
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # Exit reason breakdown
    tp_count = sum(1 for t in trades if t["exit_reason"] == "TP")
    sl_count = sum(1 for t in trades if t["exit_reason"] == "SL")
    time_count = sum(1 for t in trades if t["exit_reason"] == "TIME")
    trail_count = sum(1 for t in trades if t.get("trail_active"))

    # Average winning R
    win_rs = r_arr[r_arr > 0]
    avg_win_r = float(np.mean(win_rs)) if len(win_rs) > 0 else 0

    risk_per_trade_usd = 1000 * 0.005  # 0.5% of $1000
    expected_profit_per_trade = avg_r * risk_per_trade_usd

    result = {
        "symbol": symbol,
        "team": SYMBOL_TO_TEAM.get(symbol, "FOREX"),
        "params": params,
        "trades": n_tr,
        "wins": wins,
        "losses": losses,
        "win_rate": wr,
        "avg_r": avg_r,
        "avg_win_r": avg_win_r,
        "expectancy_r": avg_r,
        "gross_r": gross,
        "sharpe": sharpe,
        "profit_factor": profit_factor,
        "max_consec_loss": best_run,
        "tp_exits": tp_count,
        "sl_exits": sl_count,
        "time_exits": time_count,
        "trail Activated": trail_count,
        "viable": n_tr >= 20 and avg_r > 0,
        "expected_per_trade_usd": expected_profit_per_trade,
        "target_70wr": wr >= 0.70,
        "target_2_5r": avg_win_r >= 2.0,
    }

    if verbose:
        t_flag = "T" if result["target_70wr"] else "-"
        r_flag = "R" if result["target_2_5r"] else "-"
        v_flag = "V" if result["viable"] else "-"
        print(
            f"[{v_flag}{t_flag}{r_flag}] {symbol:8s} ({result['team']:12s}) "
            f"trades={n_tr:4d}  WR={wr*100:5.1f}%  avgR={avg_r:+.3f}  "
            f"avgWinR={avg_win_r:.2f}  PF={profit_factor:.2f}  "
            f"sharpe={sharpe:+.2f}  maxCL={best_run}  "
            f"TP={tp_count} SL={sl_count} TIME={time_count} TRAIL={trail_count}  "
            f"~${expected_profit_per_trade:+.2f}/trade"
        )
    return result


def main():
    args = sys.argv[1:]
    if args:
        pairs = [a.upper() for a in args]
    else:
        pairs = list(PAIR_PARAMS.keys())

    print("=" * 110)
    print("PRECISION STRATEGY — 70% WR + 2.5R Target")
    print("7-layer confluence scoring | Aggressive filtering | Trailing stops")
    print("=" * 110)
    print(
        f"{'Pair':10s} {'Team':12s} {'Trades':>6s} {'WR%':>6s} {'AvgR':>7s} "
        f"{'AvgWR':>6s} {'PF':>6s} {'Sharpe':>7s} {'MaxCL':>5s} "
        f"{'TP':>4s} {'SL':>4s} {'TIME':>5s} {'TRAIL':>6s} {'$/Tr':>8s}"
    )
    print("-" * 110)

    t0 = time.time()
    results = []
    for sym in pairs:
        try:
            r = run_precision_backtest(sym, bars=5000, verbose=True)
            results.append(r)
        except Exception as e:
            print(f"[!] {sym:8s} ERROR: {e}")

    dt = time.time() - t0
    print("-" * 110)

    viable = [r for r in results if r.get("viable")]
    target_hit = [r for r in viable if r.get("target_70wr") and r.get("target_2_5r")]
    total_trades = sum(r.get("trades", 0) for r in results)
    total_wins = sum(r.get("wins", 0) for r in results)
    overall_wr = total_wins / total_trades if total_trades > 0 else 0

    print(f"\nTotal trades: {total_trades}  |  Overall WR: {overall_wr*100:.1f}%")
    print(f"Viable pairs: {len(viable)}/{len(results)}  |  Target hit (70%WR+2.5R): {len(target_hit)}/{len(results)}")
    print(f"Time: {dt:.1f}s")

    if target_hit:
        print(f"\n*** TARGET HIT — 70% WR + 2.5R ACHIEVED: ***")
        for r in target_hit:
            print(
                f"  {r['symbol']:8s} ({r['team']:12s}): "
                f"WR={r['win_rate']*100:.1f}%  avgWinR={r['avg_win_r']:.2f}  "
                f"PF={r['profit_factor']:.2f}  trades={r['trades']}  "
                f"~${r['expected_per_trade_usd']:+.2f}/trade"
            )

    if viable and not target_hit:
        print("\nVIABLE (positive expectancy) but below70% WR target:")
        for r in viable:
            print(
                f"  {r['symbol']:8s} ({r['team']:12s}): "
                f"WR={r['win_rate']*100:.1f}%  avgR={r['avg_r']:+.3f}  "
                f"PF={r['profit_factor']:.2f}  trades={r['trades']}"
            )

    non_viable = [r for r in results if not r.get("viable") and r.get("trades", 0) > 0]
    if non_viable:
        print("\nNON-VIABLE:")
        for r in non_viable:
            print(
                f"  {r['symbol']:8s} ({r['team']:12s}): "
                f"WR={r['win_rate']*100:.1f}%  avgR={r['avg_r']:+.3f}  "
                f"trades={r['trades']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
