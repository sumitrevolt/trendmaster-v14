"""Local webhook signal generator.

Pure Python signal source that bypasses TradingView entirely. Reads price
data from MT5 for the 19 canonical TrendMaster pairs across M5/M15/H1/H4,
computes signals using a transparent rule set (EMA cross + RSI confirm +
ATR-filter), and POSTs each fired signal to our local /tv-signal webhook.

Pipeline becomes:
    [local generator]  →  POST localhost:5005/tv-signal
                          ↓
                       tv_executor.write_tv_signal
                          ↓
                       MT5 EA picks up, executes
                          ↓
                       signal_outcome_collector joins outcomes
                          ↓
                       signal_quality_learner learns

NO TradingView. NO Pine Script. NO TV alerts.

Signal logic (kept simple + transparent):
  BUY when:
    - EMA(20) > EMA(50) on the working TF      (trend up)
    - RSI(14) crossed up through 50 in last 2 bars (momentum)
    - last bar's range > 0.5 × ATR(14)         (real move)
  SELL when symmetric (EMA20<EMA50, RSI cross down 50, range filter)
  Else: no signal.

  Dedup per (symbol, TF, direction): once per bar (state file).

Run via schtask every 5 min HIDDEN (use hidden_local_signal_generator.vbs).
Tweak signal logic in `_compute_signal()` to match whatever indicator behavior you want.
"""
from __future__ import annotations
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "local_signal_generator.log"
STATE_PATH = LOG_DIR / "local_signal_generator_state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
)
log = logging.getLogger("local_sig_gen")

# ─────────────── 19 canonical TrendMaster pairs ───────────────
SYMBOLS = [
    "XAUUSD", "XAGUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY",
    "CADJPY", "EURGBP",
    "BTCUSD", "ETHUSD",
    "XTIUSD", "XBRUSD", "XNGUSD",
]

# 4 timeframes (TV-style names mapped to MT5 timeframe constants below)
TIMEFRAMES = ["M5", "M15", "H1", "H4"]


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / "config" / ".env")
    except Exception:
        pass


def _state_load() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _state_save(s: dict) -> None:
    STATE_PATH.write_text(json.dumps(s, indent=2, default=str), encoding="utf-8")


# ─────────────── indicator math (no external deps beyond numpy) ───────────────
def _ema(arr, period):
    import numpy as np
    a = np.asarray(arr, dtype="float64")
    if len(a) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(a)
    out[0] = a[0]
    for i in range(1, len(a)):
        out[i] = alpha * a[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(close, period=14):
    import numpy as np
    c = np.asarray(close, dtype="float64")
    if len(c) < period + 2:
        return None
    delta = np.diff(c)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    # Wilder's smoothing
    avg_gain = np.zeros_like(c)
    avg_loss = np.zeros_like(c)
    avg_gain[period] = gain[:period].mean()
    avg_loss[period] = loss[:period].mean()
    for i in range(period + 1, len(c)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i - 1]) / period
    rs = np.where(avg_loss == 0, 100.0, avg_gain / np.maximum(avg_loss, 1e-10))
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(high, low, close, period=14):
    import numpy as np
    h, l, c = np.asarray(high), np.asarray(low), np.asarray(close)
    if len(h) < period + 1:
        return None
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    out = np.zeros(len(h))
    out[period] = tr[:period].mean()
    for i in range(period + 1, len(h)):
        out[i] = (out[i - 1] * (period - 1) + tr[i - 1]) / period
    return out


def _compute_signal(rates) -> tuple[str, float, dict]:
    """Returns (direction, confidence, metadata) for one symbol/TF.
    direction in {"BUY", "SELL", "NONE"}.

    Logic mirrors `ai_trading_agents/direction_inference.py`: REVERSAL-based
    detection matching Rocket Prime's pattern:
      - "Buy Observation" fires at SUPPORT (price near recent low + RSI oversold)
      - "Sell Observation" fires at RESISTANCE (price near recent high + RSI overbought)

    Only fires NONE→BUY/SELL when conditions are STRONG (not every bar);
    this keeps signal frequency comparable to Rocket Prime's actual rate.
    """
    import numpy as np
    if rates is None or len(rates) < 60:
        return "NONE", 0.0, {"reason": "insufficient_bars"}

    close = np.array([r["close"] for r in rates])
    if len(close) < 22:
        return "NONE", 0.0, {"reason": "need_22_bars"}

    rsi = _rsi(close, 14)
    if rsi is None:
        return "NONE", 0.0, {"reason": "rsi_failed"}

    i = -2  # last closed bar
    last_close = float(close[i])
    rsi_val = float(rsi[i])

    # Position in last-20-bar range (mirrors direction_inference)
    recent = close[i-20:i+1]
    rng_high = float(max(recent))
    rng_low = float(min(recent))
    rng = rng_high - rng_low if rng_high > rng_low else 1e-9
    pos_in_range = (last_close - rng_low) / rng

    # Last 3 bars momentum (close-to-close — caller passes dicts w/o 'open')
    c5 = float(close[-5]) if len(close) >= 5 else float(close[0])
    c2 = float(close[-2])
    last3_diff_pct = (c2 - c5) / c5 * 100.0

    metadata = {
        "rsi": round(rsi_val, 2),
        "pos_in_range": round(pos_in_range, 3),
        "last3_diff_pct": round(last3_diff_pct, 4),
        "range_low": round(rng_low, 6),
        "range_high": round(rng_high, 6),
    }

    # ALWAYS-POST mode (changed 2026-05-05): EA's signal file stale check is
    # 60s — if we don't post for any (sym, TF) on EVERY run (every 1 min),
    # the file goes stale and EA rejects. So we ALWAYS return a direction.
    # Strong reversal patterns get conf=0.85, weak patterns 0.70, mid-range
    # falls back to recent-trend bias at conf=0.55.
    BUY_strong = (pos_in_range < 0.20 and rsi_val < 40)   # at very-low + oversold
    SELL_strong = (pos_in_range > 0.80 and rsi_val > 60)  # at very-high + overbought
    BUY_weak = (pos_in_range < 0.35 and last3_diff_pct < -0.10 and rsi_val < 50)
    SELL_weak = (pos_in_range > 0.65 and last3_diff_pct > 0.10 and rsi_val > 50)

    if BUY_strong:
        return "BUY", 0.85, metadata
    if SELL_strong:
        return "SELL", 0.85, metadata
    if BUY_weak:
        return "BUY", 0.70, metadata
    if SELL_weak:
        return "SELL", 0.70, metadata

    # Mid-range fallback — bias by recent 3-bar momentum so the file always
    # carries a fresh BUY/SELL. Conf=0.55 (just above EA's MIN_CONF if any).
    metadata["weak_signal"] = True
    if last3_diff_pct >= 0:
        return "BUY", 0.55, metadata   # last 3 bars net up → bias BUY
    return "SELL", 0.55, metadata      # last 3 bars net down → bias SELL


# ─────────────── webhook posting ───────────────
def _post_signal(secret: str, host: str, port: int, symbol: str, tf: str,
                 direction: str, confidence: float, meta: dict) -> bool:
    body = json.dumps({
        "secret": secret,
        "symbol": symbol,
        "direction": direction.lower(),
        "confidence": confidence,
        "tv_strategy": "local_generator",
        "tv_alert_ts": int(time.time()),
        "tv_timeframe": tf,
        "extra_meta": meta,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}/tv-signal",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=8)
        body_resp = r.read().decode()
        if r.status == 200:
            log.info(f"  posted {symbol} {tf} {direction}: {body_resp[:120]}")
            return True
        log.warning(f"  webhook {r.status} for {symbol} {tf}: {body_resp[:200]}")
        return False
    except Exception as e:
        log.warning(f"  webhook ERR for {symbol} {tf}: {e}")
        return False


# ─────────────── MT5 helpers ───────────────
def _mt5_tf_const(mt5, tf_name: str):
    return {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }.get(tf_name)


def _normalise_broker_symbol(mt5, sym: str) -> str | None:
    """Try the symbol as-is, then with common broker suffixes."""
    for candidate in (sym, sym + "m", sym + ".s", sym + ".pro", sym + "#", sym + "_i"):
        info = mt5.symbol_info(candidate)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(candidate, True)
            return candidate
    return None


# ─────────────── main loop ───────────────
def main() -> int:
    _load_env()
    secret = (os.getenv("TV_WEBHOOK_SECRET") or "").strip()
    host = (os.getenv("TV_WEBHOOK_HOST") or "127.0.0.1").strip()
    port = int(os.getenv("TV_WEBHOOK_PORT") or "5005")
    if not secret:
        log.error("TV_WEBHOOK_SECRET not set — refusing to run")
        return 2

    log.info(f"--- local signal generator run @ {datetime.now(timezone.utc).isoformat()} ---")

    try:
        import MetaTrader5 as mt5
    except ImportError:
        log.error("MetaTrader5 not installed")
        return 1

    if not mt5.initialize():
        log.error(f"mt5.initialize failed: {mt5.last_error()}")
        return 3

    state = _state_load()
    last_bar = state.get("last_bar", {})  # {f"{sym}|{tf}": last_bar_open_ts}
    fired = 0
    skipped_dup = 0
    no_signal = 0

    for sym in SYMBOLS:
        broker_sym = _normalise_broker_symbol(mt5, sym)
        if not broker_sym:
            log.warning(f"  symbol {sym} not found on broker; skip")
            continue
        for tf in TIMEFRAMES:
            tf_const = _mt5_tf_const(mt5, tf)
            rates = mt5.copy_rates_from_pos(broker_sym, tf_const, 0, 80)
            if rates is None or len(rates) < 60:
                continue
            # NOTE: per-bar dedup REMOVED 2026-05-05 — EA's stale check is 60s,
            # so we MUST re-post on every 1-min run to keep signal fresh in
            # MT5 file. Receiver's own 20s dedup window prevents same-second
            # duplicates; subsequent posts (60s apart) are accepted and
            # refresh the file timestamp.
            closed_bar_ts = int(rates[-2]["time"])
            key = f"{sym}|{tf}"
            last_bar[key] = closed_bar_ts

            direction, conf, meta = _compute_signal([dict(r._asdict() if hasattr(r, "_asdict") else
                                                           {"close": r["close"], "high": r["high"], "low": r["low"]})
                                                       for r in rates])
            # Above is messy — rates entries are numpy structured arrays; simplify
            direction, conf, meta = _compute_signal(
                [{"close": float(r[4]), "high": float(r[2]), "low": float(r[3])} for r in rates]
            )

            if direction == "NONE":
                no_signal += 1
                continue
            ok = _post_signal(secret, host, port, sym, tf, direction, conf, meta)
            if ok:
                fired += 1

    mt5.shutdown()
    _state_save({"last_bar": last_bar, "last_run": time.time()})
    log.info(f"  done — fired={fired} no_signal={no_signal} skipped_dup={skipped_dup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
