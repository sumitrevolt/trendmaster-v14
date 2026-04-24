"""
ML BACKTEST TRAINER - Generate training data from free historical market data
==============================================================================
Uses yfinance (free) to fetch 6 months of H1 + H4 data for all 14 symbols,
applies technical analysis, simulates trade signals, and determines outcomes.
Produces training trades in the exact format TrainingEngine expects.
"""

import json
import os
import sys
import io

# Fix Windows encoding issue (cp1252 can't handle unicode)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import math
import random
from datetime import datetime, timedelta
from collections import defaultdict

try:
    import yfinance as yf
    import numpy as np
except ImportError:
    print("ERROR: Install yfinance and numpy first: pip install yfinance numpy")
    sys.exit(1)

# ── Symbol Mapping: MT5 → Yahoo Finance ──────────────────────────────
SYMBOL_MAP = {
    # Metals
    "XAUUSD": "GC=F",      # Gold Futures
    "XAGUSD": "SI=F",      # Silver Futures
    # Forex
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X",
    "GBPJPY": "GBPJPY=X",
    "EURJPY": "EURJPY=X",
    "EURGBP": "EURGBP=X",
    "USDCHF": "USDCHF=X",
    # Crypto
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
}

# Pip values for PnL calculation (approximate)
PIP_VALUES = {
    "XAUUSD": 10.0, "XAGUSD": 50.0,
    "EURUSD": 10.0, "GBPUSD": 10.0, "USDJPY": 7.5,
    "AUDUSD": 10.0, "USDCAD": 7.5, "NZDUSD": 10.0,
    "GBPJPY": 7.5, "EURJPY": 7.5, "EURGBP": 12.0, "USDCHF": 10.0,
    "BTCUSD": 1.0, "ETHUSD": 1.0,
}

# ── Technical Analysis Functions ─────────────────────────────────────
def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_sma(series, period):
    return series.rolling(window=period).mean()

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))

def calc_adx(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    atr = tr.rolling(window=period).mean()

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_di = 100 * (calc_sma(pd_series(plus_dm, close.index), period) / atr.replace(0, 1e-10))
    minus_di = 100 * (calc_sma(pd_series(minus_dm, close.index), period) / atr.replace(0, 1e-10))

    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-10))
    adx = dx.rolling(window=period).mean()
    return adx

def pd_series(arr, index):
    import pandas as pd
    return pd.Series(arr, index=index)

def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calc_bollinger(close, period=20, std_dev=2):
    sma = calc_sma(close, period)
    std = close.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower

def determine_trend(close, ema20, ema50):
    """Determine trend from EMA alignment."""
    if close.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]:
        return "BULLISH"
    elif close.iloc[-1] < ema20.iloc[-1] < ema50.iloc[-1]:
        return "BEARISH"
    return "SIDEWAYS"

def determine_bb_state(close_val, upper_val, lower_val, sma_val):
    if close_val >= upper_val:
        return "ABOVE_UPPER"
    elif close_val <= lower_val:
        return "BELOW_LOWER"
    elif close_val > sma_val:
        return "UPPER_HALF"
    else:
        return "LOWER_HALF"

def determine_macd_label(hist_val, hist_prev):
    if hist_val > 0 and hist_val > hist_prev:
        return "BULLISH_STRONG"
    elif hist_val > 0:
        return "BULLISH_WEAK"
    elif hist_val < 0 and hist_val < hist_prev:
        return "BEARISH_STRONG"
    else:
        return "BEARISH_WEAK"

def get_killzone(hour):
    """Determine trading killzone from hour."""
    if 2 <= hour <= 5:
        return "ASIAN"
    elif 7 <= hour <= 10:
        return "LONDON"
    elif 13 <= hour <= 16:
        return "NEW_YORK"
    elif 10 <= hour <= 13:
        return "LONDON_NY_OVERLAP"
    return "NONE"

def get_amd_phase(rsi_val, adx_val, bb_state):
    """Simplified AMD phase detection."""
    if adx_val < 20 and bb_state in ("UPPER_HALF", "LOWER_HALF"):
        return "ACCUMULATION"
    elif adx_val > 25 and bb_state in ("ABOVE_UPPER", "BELOW_LOWER"):
        return "MANIPULATION"
    elif adx_val > 30:
        return "DISTRIBUTION"
    return "NONE"


# ── Main Training Data Generator ─────────────────────────────────────
def generate_training_data(symbol, yf_ticker, lookback_days=180):
    """
    Fetch historical data and generate simulated training trades.
    Uses H1 data to simulate signal generation and forward-looking outcome.
    """
    import pandas as pd

    print(f"  [FETCH] {symbol} ({yf_ticker})...", end=" ", flush=True)

    try:
        # Fetch H1 data (1h interval, max ~730 days for yfinance)
        ticker = yf.Ticker(yf_ticker)
        df_h1 = ticker.history(period=f"{lookback_days}d", interval="1h")

        if df_h1 is None or len(df_h1) < 100:
            print(f"[FAIL] Only {len(df_h1) if df_h1 is not None else 0} bars — skipping")
            return []

        # Also fetch H4 (approximate from daily for trend)
        df_daily = ticker.history(period=f"{lookback_days}d", interval="1d")

        print(f"[OK] {len(df_h1)} H1 bars, {len(df_daily)} daily bars")
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return []

    # ── Calculate indicators on H1 ──
    close = df_h1["Close"]
    high = df_h1["High"]
    low = df_h1["Low"]

    ema20 = calc_ema(close, 20)
    ema50 = calc_ema(close, 50)
    rsi = calc_rsi(close, 14)
    adx = calc_adx(high, low, close, 14)
    macd_line, signal_line, macd_hist = calc_macd(close)
    bb_upper, bb_mid, bb_lower = calc_bollinger(close)

    # H4 trend from daily
    if df_daily is not None and len(df_daily) >= 50:
        d_ema20 = calc_ema(df_daily["Close"], 20)
        d_ema50 = calc_ema(df_daily["Close"], 50)
    else:
        d_ema20 = ema20
        d_ema50 = ema50

    # Fill NaN in indicators to avoid filtering everything out
    adx = adx.fillna(20.0)
    rsi = rsi.fillna(50.0)
    macd_hist = macd_hist.fillna(0.0)
    bb_upper = bb_upper.fillna(close + close.std())
    bb_lower = bb_lower.fillna(close - close.std())
    bb_mid = bb_mid.fillna(close)
    ema20 = ema20.fillna(close)
    ema50 = ema50.fillna(close)

    # ── Generate signals every ~4 hours (skip first 60 bars for indicator warmup) ──
    trades = []
    step = 4  # Check every 4 hours
    forward_bars = 12  # Look 12 H1 bars ahead for outcome (12 hours)
    _dbg_nan = 0
    _dbg_nodir = 0
    _dbg_lowscore = 0

    for i in range(60, len(df_h1) - forward_bars, step):
        try:
            c = float(close.iloc[i])
            r = float(rsi.iloc[i])
            a = float(adx.iloc[i])
            mh = float(macd_hist.iloc[i])
            mh_prev = float(macd_hist.iloc[i - 1])
            bb_u = float(bb_upper.iloc[i])
            bb_l = float(bb_lower.iloc[i])
            bb_m = float(bb_mid.iloc[i])
            e20 = float(ema20.iloc[i])
            e50 = float(ema50.iloc[i])

            # Skip if any NaN
            if any(math.isnan(x) for x in [c, r, a, mh, mh_prev, bb_u, bb_l, bb_m, e20, e50]):
                _dbg_nan += 1
                continue

            # ── Determine Signal ──
            h1_trend = determine_trend(close.iloc[:i+1], ema20.iloc[:i+1], ema50.iloc[:i+1])
            bb_state = determine_bb_state(c, bb_u, bb_l, bb_m)
            macd_label = determine_macd_label(mh, mh_prev)

            # H4 trend (use daily as proxy)
            dt = df_h1.index[i]
            try:
                # Handle timezone-aware/naive index mismatch
                dt_naive = dt.tz_localize(None) if hasattr(dt, 'tz_localize') and dt.tzinfo else dt
                daily_idx_naive = df_daily.index.tz_localize(None) if hasattr(df_daily.index, 'tz_localize') and df_daily.index.tzinfo else df_daily.index
                d_idx = daily_idx_naive.searchsorted(dt_naive)
                d_idx = min(d_idx, len(df_daily) - 1)
            except Exception:
                d_idx = len(df_daily) - 1
            if d_idx >= 20:
                h4_trend = determine_trend(
                    df_daily["Close"].iloc[:d_idx+1],
                    d_ema20.iloc[:d_idx+1],
                    d_ema50.iloc[:d_idx+1]
                )
            else:
                h4_trend = h1_trend  # Fallback to H1 trend instead of SIDEWAYS

            # Hour and killzone
            hour = dt.hour if hasattr(dt, 'hour') else 12
            killzone = get_killzone(hour)
            amd_phase = get_amd_phase(r, a, bb_state)

            # ── Signal Scoring (mimics SignalEngine) ──
            score = 0
            confidence = 50

            # Trend alignment
            if h1_trend == h4_trend and h1_trend != "SIDEWAYS":
                score += 4
                confidence += 15
            elif h1_trend != "SIDEWAYS":
                score += 2
                confidence += 5

            # RSI signals
            if r < 30:
                score += 2  # Oversold → BUY potential
                confidence += 5
            elif r > 70:
                score += 2  # Overbought → SELL potential
                confidence += 5
            elif 45 < r < 55:
                score -= 1  # Neutral zone

            # ADX strength
            if a > 30:
                score += 2
                confidence += 10
            elif a > 25:
                score += 1
                confidence += 5
            elif a < 15:
                score -= 2
                confidence -= 10

            # MACD
            if "STRONG" in macd_label:
                score += 2
                confidence += 5
            elif "WEAK" in macd_label:
                score += 1

            # Bollinger
            if bb_state == "BELOW_LOWER":
                score += 1  # Potential bounce BUY
            elif bb_state == "ABOVE_UPPER":
                score += 1  # Potential reversal SELL

            # Killzone bonus
            if killzone != "NONE":
                score += 1
                confidence += 5

            # ── Determine direction ──
            if h1_trend == "BULLISH" or (h1_trend == "SIDEWAYS" and r < 45):
                direction = "BUY"
            elif h1_trend == "BEARISH" or (h1_trend == "SIDEWAYS" and r > 55):
                direction = "SELL"
            else:
                _dbg_nodir += 1
                continue

            # Minimum score threshold (relaxed for training data diversity)
            if score < 2:
                _dbg_lowscore += 1
                continue  # Too weak

            # Clamp confidence
            confidence = max(20, min(95, confidence))

            # ── Determine Outcome (forward looking) ──
            future_close = close.iloc[i + forward_bars]
            entry_price = c

            if direction == "BUY":
                # Check if price moved up enough
                max_price = high.iloc[i+1:i+forward_bars+1].max()
                min_price = low.iloc[i+1:i+forward_bars+1].min()
                move_pct = (future_close - entry_price) / entry_price * 100
                max_move = (max_price - entry_price) / entry_price * 100
                min_move = (entry_price - min_price) / entry_price * 100
            else:  # SELL
                max_price = high.iloc[i+1:i+forward_bars+1].max()
                min_price = low.iloc[i+1:i+forward_bars+1].min()
                move_pct = (entry_price - future_close) / entry_price * 100
                max_move = (entry_price - min_price) / entry_price * 100
                min_move = (max_price - entry_price) / entry_price * 100

            # Win if price moved favorably by 0.05%+ AND didn't hit stop first
            # Use 2:1 RR approximation
            tp_threshold = 0.08  # 0.08% for TP
            sl_threshold = 0.15  # 0.15% for SL

            if symbol in ("BTCUSD", "ETHUSD"):
                tp_threshold = 0.5   # Crypto more volatile
                sl_threshold = 1.0
            elif symbol in ("XAUUSD", "XAGUSD"):
                tp_threshold = 0.15
                sl_threshold = 0.30

            if max_move >= tp_threshold and min_move < sl_threshold:
                outcome = "WIN"
                pnl = round(random.uniform(5, 50) * (1 + score / 10), 2)
            elif min_move >= sl_threshold:
                outcome = "LOSS"
                pnl = round(-random.uniform(10, 40), 2)
            elif move_pct > 0:
                outcome = "WIN"
                pnl = round(random.uniform(2, 20), 2)
            else:
                outcome = "LOSS"
                pnl = round(-random.uniform(5, 25), 2)

            # ── Simulated institutional/news signals ──
            inst_dir = direction if random.random() > 0.4 else ("SELL" if direction == "BUY" else "BUY")
            inst_conf = random.randint(40, 80)
            news = random.choice(["BULLISH", "BEARISH", "NEUTRAL", "NEUTRAL"])
            vol_signal = random.choice(["NORMAL", "NORMAL", "NORMAL", "HIGH_INSTITUTIONAL", "MASSIVE_INSTITUTIONAL"])

            # ── Build trade snapshot ──
            trade = {
                "symbol": symbol,
                "direction": direction,
                "score": score,
                "confidence": confidence,
                "h1_trend": h1_trend,
                "h4_trend": h4_trend,
                "h4_h1_aligned": h4_trend == h1_trend and h4_trend != "SIDEWAYS",
                "rsi": round(float(r), 1),
                "adx": round(float(a), 1),
                "macd": macd_label,
                "bb_state": bb_state,
                "amd_phase": amd_phase,
                "news": news,
                "hour_utc": hour,
                "institutional_dir": inst_dir,
                "institutional_conf": inst_conf,
                "killzone": killzone,
                "volume_signal": vol_signal,
                "agents": [f"{symbol}_analyst", "signal_engine", "risk_manager"],
                "entry_time": dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "outcome": outcome,
                "pnl": pnl,
                "close_time": df_h1.index[i + forward_bars].strftime("%Y-%m-%dT%H:%M:%S"),
                "trade_id": f"{symbol}_{dt.strftime('%Y%m%d%H%M')}",
            }
            trades.append(trade)

        except Exception as e:
            continue

    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    total = len(trades)
    wr = round(wins / total * 100, 1) if total > 0 else 0
    total_iters = max(1, (len(df_h1) - forward_bars - 60) // step)
    print(f"    -> Generated {total} trades | WR: {wr}% | [NaN:{_dbg_nan} NoDir:{_dbg_nodir} LowScore:{_dbg_lowscore} / {total_iters} iters]")
    return trades


def main():
    print("=" * 70)
    print("[ML BACKTEST TRAINER] Free Historical Data -> Training Trades")
    print("=" * 70)
    print(f"[DATE] Using ~6 months of historical data from Yahoo Finance (FREE)")
    print(f"[SYMBOLS] {len(SYMBOL_MAP)} ({', '.join(SYMBOL_MAP.keys())})")
    print()

    all_trades = []

    for mt5_sym, yf_sym in SYMBOL_MAP.items():
        trades = generate_training_data(mt5_sym, yf_sym, lookback_days=180)
        all_trades.extend(trades)

    print()
    print("=" * 70)
    print(f"[STATS] TOTAL GENERATED: {len(all_trades)} training trades")

    if len(all_trades) == 0:
        print("[FAIL] No trades generated. Check internet connection.")
        return

    # ── Stats ──
    wins = sum(1 for t in all_trades if t["outcome"] == "WIN")
    losses = len(all_trades) - wins
    total_pnl = sum(t["pnl"] for t in all_trades)
    print(f"   Wins: {wins} | Losses: {losses} | WR: {round(wins/len(all_trades)*100, 1)}%")
    print(f"   Total P&L: ${total_pnl:.2f}")

    # ── Per symbol breakdown ──
    sym_stats = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0})
    for t in all_trades:
        s = sym_stats[t["symbol"]]
        s["w" if t["outcome"] == "WIN" else "l"] += 1
        s["pnl"] += t["pnl"]

    print(f"\n   Per-Symbol Breakdown:")
    for sym in sorted(sym_stats.keys()):
        s = sym_stats[sym]
        total = s["w"] + s["l"]
        wr = round(s["w"] / total * 100, 1) if total > 0 else 0
        print(f"    {sym:10s} → {total:4d} trades | WR: {wr:5.1f}% | P&L: ${s['pnl']:8.2f}")

    # ── Load existing training data and merge ──
    training_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_training_data.json")

    existing_data = {
        "trades": [],
        "patterns": {},
        "agent_accuracy": {},
        "symbol_stats": {},
        "session_stats": {},
        "combo_stats": {},
        "regime_stats": {},
        "adaptive_thresholds": {},
        "blacklisted_symbols": [],
        "blacklisted_hours": {},
        "ml_model_accuracy": 0,
        "last_trained": None,
        "total_pnl": 0,
    }

    if os.path.exists(training_file):
        try:
            with open(training_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if "trades" in loaded:
                    existing_data = loaded
                    print(f"\n[FILE] Existing training data: {len(existing_data['trades'])} trades")
        except Exception as e:
            print(f"[WARN] Error reading existing data: {e}")

    # ── Merge: add new trades, avoid duplicates by trade_id ──
    existing_ids = set(t.get("trade_id", "") for t in existing_data["trades"])
    new_trades = [t for t in all_trades if t["trade_id"] not in existing_ids]

    print(f"   New unique trades to add: {len(new_trades)}")

    existing_data["trades"].extend(new_trades)

    # Keep last 5000 trades (more data = better ML)
    if len(existing_data["trades"]) > 5000:
        existing_data["trades"] = existing_data["trades"][-5000:]

    # Update total PnL
    existing_data["total_pnl"] = sum(t.get("pnl", 0) for t in existing_data["trades"] if t.get("outcome"))

    # ── Save ──
    import tempfile
    dir_path = os.path.dirname(training_file)
    with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                      suffix='.tmp', encoding='utf-8') as tmp:
        json.dump(existing_data, tmp, indent=2, default=str)
        tmp.flush()
        os.fsync(tmp.fileno())
    os.replace(tmp.name, training_file)

    total_trades = len(existing_data["trades"])
    resolved = sum(1 for t in existing_data["trades"] if t.get("outcome"))
    print(f"\n[OK] SAVED: {total_trades} total trades ({resolved} resolved)")
    print(f"   File: {training_file}")

    # ── Now run ML training ──
    print(f"\n[ML] Running ML Training on {resolved} resolved trades...")
    try:
        from sklearn.tree import DecisionTreeClassifier
        import numpy as np

        resolved_trades = [t for t in existing_data["trades"] if t.get("outcome")]

        features = []
        labels = []
        for t in resolved_trades:
            f = [
                t.get("score", 0),
                t.get("confidence", 50),
                t.get("rsi", 50),
                t.get("adx", 20),
                t.get("hour_utc", 12),
                t.get("institutional_conf", 50),
                1 if t.get("h4_h1_aligned") else 0,
                1 if t.get("killzone", "NONE") != "NONE" else 0,
                1 if t.get("institutional_dir") == t.get("direction") else 0,
                1 if t.get("amd_phase") == "DISTRIBUTION" else 0,
                1 if t.get("volume_signal", "NORMAL") != "NORMAL" else 0,
                1 if t.get("news") == t.get("direction", "").replace("BUY", "BULLISH").replace("SELL", "BEARISH") else 0,
                1 if t.get("direction") == "BUY" else 0,
            ]
            features.append(f)
            labels.append(1 if t["outcome"] == "WIN" else 0)

        X = np.array(features)
        y = np.array(labels)

        model = DecisionTreeClassifier(
            max_depth=6,
            min_samples_leaf=5,
            min_samples_split=10,
            random_state=42,
        )
        model.fit(X, y)

        predictions = model.predict(X)
        accuracy = round(np.mean(predictions == y) * 100, 1)

        # Feature importances
        feature_names = [
            "score", "confidence", "rsi", "adx", "hour", "inst_conf",
            "h4_aligned", "killzone", "inst_confirm", "amd_dist",
            "vol_spike", "news_confirm", "is_buy",
        ]
        importances = model.feature_importances_
        top_features = sorted(
            zip(feature_names, importances),
            key=lambda x: x[1], reverse=True
        )[:5]

        # Update training data with ML results
        existing_data["ml_model_accuracy"] = accuracy
        existing_data["last_trained"] = datetime.utcnow().isoformat()
        existing_data["ml_top_features"] = [
            {"name": n, "importance": round(imp * 100, 1)}
            for n, imp in top_features
        ]

        # Save again with ML results
        with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                          suffix='.tmp', encoding='utf-8') as tmp:
            json.dump(existing_data, tmp, indent=2, default=str)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp.name, training_file)

        print(f"\n[TARGET] ML MODEL TRAINED SUCCESSFULLY!")
        print(f"   Accuracy: {accuracy}%")
        print(f"   Training samples: {len(resolved_trades)}")
        print(f"   Top features:")
        for name, imp in top_features:
            print(f"     {name:15s} → {imp*100:5.1f}%")

    except ImportError:
        print("[WARN] scikit-learn not installed — statistical learning only")
    except Exception as e:
        print(f"[FAIL] ML Training error: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n{'=' * 70}")
    print(f"[OK] ML BACKTEST TRAINING COMPLETE!")
    print(f"   Total trades in training DB: {len(existing_data['trades'])}")
    print(f"   ML Model: ACTIVE @ {existing_data.get('ml_model_accuracy', 0)}% accuracy")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
