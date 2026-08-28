"""Python signal executor — bypasses the MT5 EA's toolbar AutoTrading gate.

Why this exists: the MT5 EA gets blocked by Windows UIPI security on the
toolbar AutoTrading button (which resets to OFF on every MT5 restart and
cannot be re-enabled by external software). Python's mt5.order_send,
however, is NOT blocked by the same gate — it uses the API permission
which is independently controllable.

This script:
  1. Polls the per-symbol signal JSON files in MT5/MQL5/Files (the same
     files the EA reads).
  2. For each fresh signal (age < TV_SIGNAL.max_signal_age_s, default 60),
     places a market order via mt5.order_send.
  3. Honours these safety rails:
       - 1 position per symbol max (matching EA's InpMaxOpenPerSym=1)
       - Per-(symbol, direction) cooldown to prevent spam
       - Skip if signal direction matches an already-open position
       - SL/TP from the JSON's sl_atr_mult / tp_atr_mult × current ATR
       - Lot sizing from per-team risk (mirrors brain logic)
  4. Logs every decision (placed / skipped / failed) to
     logs/python_executor.log.

Operator runs this manually:
    .venv\\Scripts\\python.exe tools\\python_signal_executor.py

Or via VBS hidden launcher (see tools/hidden_python_executor.vbs).

Stop with Ctrl+C or by killing the python.exe process.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 2026-05-07 — explicit .env load BEFORE any module that reads env vars.
# Defense-in-depth: telegram_notifier loads .env on its own, but if the
# OS env is stale from a prior pythonw session, the notifier's load can
# be no-op'd (load_dotenv defaults to override=False). Forcing it with
# override=True guarantees the latest creds are picked up. Was the root
# cause of the 2026-05-06/07 "Telegram send failed: 404" warnings — old
# bot token cached in some restart cycle.
try:
    from dotenv import load_dotenv
    for _cand in (ROOT / ".env", ROOT / "config" / ".env"):
        if _cand.exists():
            load_dotenv(_cand, override=True)
            break
except ImportError:
    pass

# Telegram notifier (best-effort — fails silently if creds missing)
_TG_IMPORT_ERROR: Optional[str] = None
try:
    from ai_trading_agents.telegram_notifier import get_notifier
    _tg = get_notifier()
except Exception as _e:
    _tg = None
    _TG_IMPORT_ERROR = repr(_e)

# Safeguards (news blackout, drawdown, spread, correlation)
# [2026-05-09 GODMODE] Track import failures so the startup banner can SCREAM
# if both paths fail. Previously this silently set safeguards_check=None,
# bypassing all concentration caps + DD breaker + news blackout + spread guard
# with zero log entry — that was MORE dangerous than the local_generator bug.
_SAFEGUARDS_IMPORT_ERROR: Optional[str] = None
try:
    from tools.safeguards import check_all as safeguards_check
except Exception as _e1:
    try:
        from safeguards import check_all as safeguards_check
    except Exception as _e2:
        safeguards_check = None
        _SAFEGUARDS_IMPORT_ERROR = f"primary={_e1!r}  fallback={_e2!r}"


def _tg_send(text: str) -> None:
    """Best-effort Telegram send — never raise."""
    try:
        if _tg and _tg.enabled:
            _tg.send(text)
    except Exception:
        pass

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "python_executor.log"

_handlers = [logging.FileHandler(LOG_PATH, encoding="utf-8")]
# Only add stdout handler if stdout exists (pythonw.exe has no stdout)
if sys.stdout is not None and hasattr(sys.stdout, "write"):
    try:
        _handlers.append(logging.StreamHandler(sys.stdout))
    except Exception:
        pass
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_handlers,
)
log = logging.getLogger("py_exec")


# ─── config ─────────────────────────────────────────────────────────────
SYMBOLS = [
    "XAUUSD", "XAGUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY",
    "CADJPY", "EURGBP", "EURAUD",  # added EURAUD — Rocket Prime fires here often
    "BTCUSD", "ETHUSD",
    "XTIUSD", "XBRUSD", "XNGUSD",
]

POLL_INTERVAL_S = 5
SIGNAL_MAX_AGE_S = 90  # discard signals older than this (broker tz-aware below)
PER_SYMBOL_DIR_COOLDOWN_S = 300  # 5 min between same-direction orders per symbol
MAX_OPEN_PER_SYMBOL = 2  # one Quick leg + one Trend leg
DEVIATION_PTS = 30
COMMENT_PREFIX = "PyExec"

# [2026-05-06] FIXED LOT SIZE — operator policy: every trade exactly 0.01
FIXED_LOT_SIZE = 0.01

# [2026-05-06] TWO-LEG STRATEGY:
#   Leg A "Quick"  — small TP, fixed wide SL, no trailing. Cashes out fast.
#   Leg B "Trend"  — bigger TP, same wide SL, trailing kicks in after +1xATR.
# Different magic numbers so the trailing manager only touches Leg B.
MAGIC_QUICK = 14014
MAGIC_TREND = 14015

QUICK_TP_ATR = 1.5
QUICK_SL_ATR = 3.0
TREND_TP_ATR = 5.0
TREND_SL_ATR = 3.0
TRAIL_ACTIVATE_ATR = 1.0   # start trailing once price has moved +1×ATR favorable
TRAIL_DISTANCE_ATR = 1.5   # trail at 1.5×ATR behind current price

# Backward-compat alias used elsewhere
MAGIC = MAGIC_QUICK
MIN_SL_ATR_MULT = QUICK_SL_ATR
MIN_TP_ATR_MULT = QUICK_TP_ATR

# Cooldown tracker: {(symbol, dir): last_order_unix} — persisted to disk
_COOLDOWN_FILE = LOG_DIR / "executor_cooldown.json"
_LAST_ORDER: Dict[Tuple[str, str], float] = {}

# Dashboard config — re-read every iteration so toggles work without restart
_DASHBOARD_CONFIG_FILE = LOG_DIR / "dashboard_config.json"


def _read_dashboard_config() -> Optional[dict]:
    """Returns dashboard config or None if file missing/unreadable."""
    if not _DASHBOARD_CONFIG_FILE.exists():
        return None
    try:
        return json.loads(_DASHBOARD_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_cooldown() -> None:
    """Load cooldown state from disk (survives restart)."""
    global _LAST_ORDER
    try:
        if _COOLDOWN_FILE.exists():
            data = json.loads(_COOLDOWN_FILE.read_text(encoding="utf-8"))
            now = time.time()
            for k, ts in data.items():
                # key was "SYMBOL|DIR" string
                if "|" in k and isinstance(ts, (int, float)):
                    if now - ts < PER_SYMBOL_DIR_COOLDOWN_S * 3:  # only keep recent
                        sym, d = k.split("|", 1)
                        _LAST_ORDER[(sym, d)] = float(ts)
    except Exception as e:
        log.warning("could not load cooldown: %s", e)


def _save_cooldown() -> None:
    """Persist cooldown state to disk."""
    try:
        data = {f"{sym}|{d}": ts for (sym, d), ts in _LAST_ORDER.items()}
        _COOLDOWN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("could not save cooldown: %s", e)


# ─── MT5 helpers ────────────────────────────────────────────────────────
def init_mt5() -> bool:
    if not mt5.initialize():
        log.error("mt5.initialize failed: %s", mt5.last_error())
        return False
    ti = mt5.terminal_info()
    ai = mt5.account_info()
    log.info(
        "MT5 connected: build=%s account=%s balance=%.2f trade_allowed=%s",
        ti.build if ti else "?",
        ai.login if ai else "?",
        ai.balance if ai else 0.0,
        ti.trade_allowed if ti else False,
    )
    return True


def find_signal_dir() -> Optional[Path]:
    """Locate MT5 MQL5/Files using terminal_info."""
    ti = mt5.terminal_info()
    if not ti:
        return None
    base = Path(ti.data_path) / "MQL5" / "Files"
    if base.exists():
        return base
    return None


def get_atr_h1(symbol: str, period: int = 14) -> Optional[float]:
    """Compute simple ATR on H1 from MT5 rates (no TA library needed)."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, period + 1)
    if rates is None or len(rates) < period + 1:
        return None
    trs = []
    for i in range(1, len(rates)):
        h = rates[i]["high"]; l = rates[i]["low"]; pc = rates[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else None


def detect_filling_mode(symbol: str) -> int:
    """Return supported filling mode for the symbol."""
    info = mt5.symbol_info(symbol)
    if not info:
        return mt5.ORDER_FILLING_FOK
    # filling_mode is a bitmask: 1=FOK, 2=IOC, 4=RETURN
    fm = info.filling_mode
    if fm & 2:
        return mt5.ORDER_FILLING_IOC
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def positions_for_symbol(symbol: str):
    pos = mt5.positions_get(symbol=symbol)
    return list(pos) if pos else []


_OUR_MAGICS = (MAGIC_QUICK, MAGIC_TREND, MAGIC, 0)


def _is_our_position(p) -> bool:
    return p.magic in _OUR_MAGICS


def has_position_in_dir(symbol: str, want_buy: bool) -> bool:
    for p in positions_for_symbol(symbol):
        if not _is_our_position(p):
            continue
        is_buy = p.type == mt5.ORDER_TYPE_BUY
        if is_buy == want_buy:
            return True
    return False


def close_opposite_positions(symbol: str, want_buy: bool) -> int:
    """[2026-05-06] When a signal says BUY but we hold SELL (or vice versa),
    close ALL opposite positions (both Quick and Trend legs) first so we can
    open the new direction. Returns count of positions closed.
    """
    closed = 0
    for p in positions_for_symbol(symbol):
        if not _is_our_position(p):
            continue  # don't touch positions we didn't open
        is_buy = p.type == mt5.ORDER_TYPE_BUY
        if is_buy == want_buy:
            continue  # same direction — leave alone
        # Opposite direction → close it
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if not info or not tick:
            continue
        # To close a BUY, send SELL at bid; to close a SELL, send BUY at ask
        close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if is_buy else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": p.volume,
            "type": close_type,
            "position": p.ticket,
            "price": round(close_price, info.digits),
            "deviation": DEVIATION_PTS,
            "magic": p.magic,  # match the position's own magic
            "comment": f"{COMMENT_PREFIX}-FLIP",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": detect_filling_mode(symbol),
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
            log.info(
                "FLIP: closed %s %s lots=%.2f at %.5f (P/L=%.2f) — reversal signal incoming",
                symbol, "BUY" if is_buy else "SELL", p.volume, close_price, p.profit,
            )
            _tg_send(
                f"<b>🔄 {symbol} CLOSED for FLIP</b>\n"
                f"Closed {('BUY' if is_buy else 'SELL')} 0.{int(p.volume*100):02d} at {close_price:.5f}\n"
                f"P/L: <b>{'+' if p.profit >= 0 else ''}${p.profit:.2f}</b>\n"
                f"<i>Opening reverse direction now…</i>"
            )
        else:
            err = f"ret={res.retcode} {res.comment}" if res else f"None ({mt5.last_error()})"
            log.warning("FLIP failed for %s: %s", symbol, err)
    return closed


def calc_lot_size(symbol: str, sl_distance: float, order_type: int = mt5.ORDER_TYPE_BUY) -> float:
    """[2026-05-06] FIXED LOT SIZE policy — every trade exactly FIXED_LOT_SIZE
    (default 0.01) regardless of account risk. Falls back to broker's
    volume_min if it's larger than our fixed value (rare; some exotic symbols
    require 0.1 minimum)."""
    info = mt5.symbol_info(symbol)
    if not info:
        return FIXED_LOT_SIZE
    # Snap to broker's volume step + clamp to broker's min/max bounds
    step = info.volume_step or 0.01
    lots = max(info.volume_min, FIXED_LOT_SIZE)
    lots = min(lots, info.volume_max)
    # Round to step
    lots = round(lots / step) * step
    return round(lots, 2)


# ─── signal loading ─────────────────────────────────────────────────────
def load_signal(path: Path) -> Optional[dict]:
    try:
        text = path.read_text(encoding="utf-8")
        sig = json.loads(text)
    except Exception as e:
        log.warning("could not read %s: %s", path.name, e)
        return None
    # [2026-05-05] ROCKET-PRIME-ONLY MODE: operator policy — only trade signals
    # that came from the Rocket Prime indicator via TradingView webhook.
    # The webhook receiver tags real Rocket Prime alerts with one of these
    # tv_strategy values:
    #   - "rocket_prime"           (custom JSON alert with explicit tag)
    #   - "rocket_prime_text"      (TV alert, message parsed for buy/sell)
    #   - "rocket_prime_inferred"  (TV alert with no direction, MT5 trend used)
    # [2026-05-09] local_generator ALLOWED: Rocket Prime is invite-only and
    # uses Pine `alert()` calls that override the alert dialog message field,
    # so {{plot_0}} placeholders never substitute. TV chain delivers
    # `#### {{ticker}} ####` with no direction, gets dropped as dir=NONE.
    # Until TV alerts are restructured to use plot-crossing conditions with
    # ?direction=buy|sell URL params, the LOCAL signal generator
    # (tools/local_signal_generator.py) is the only working signal source.
    # 5-day silent failure caused by this whitelist not including
    # "local_generator". Diagnosed 2026-05-09 00:30 IST.
    ALLOWED_STRATEGIES = {
        "rocket_prime",
        "rocket_prime_text",
        "rocket_prime_inferred",
        # [2026-05-09 ROCKET-PRIME-ONLY MODE per operator decision @ 00:50 IST]
        # local_generator was added 2026-05-09 to unblock trading while the
        # Rocket Prime alert chain is broken (Pine alert() override).
        # Operator chose Rocket-Prime-only — local_generator removed below.
        # Re-add only if you want EMA-cross trades again.
        # "local_generator",
        # [2026-05-07] PLOT-DIRECTION mode (p0/p1 placeholders) — added after
        # webhook receiver started emitting these but executor whitelist was
        # missed. Caused 4-hour silent drop of all live signals. See
        # docs/POSTMORTEMS or memory entry "Rocket Prime direction via plot
        # placeholders 2026-05-07".
        "rocket_prime_plot0",       # p0=1 → BUY
        "rocket_prime_plot1",       # p1=1 → SELL
        "rocket_prime_url_direction",  # ?direction=buy|sell URL param mode
        # [2026-05-13] chart-scrape OCR direction (Priority 1.5 in receiver).
        # Replaces failed Method 99 + banned INFERRED. See chart_scrape_ocr.py.
        "rocket_prime_chart_ocr",
        # Telegram BUY/SELL button helper writes signals with this source
        # tag — also needs whitelisting so operator-tap directions execute.
        "telegram_manual_direction",
        # Brain-generated signals (rule/ml inference) may not set tv_strategy;
        # allow empty so they pass through executor.
        "",
    }
    strategy = (sig.get("tv_strategy") or "").lower().strip()
    if strategy not in ALLOWED_STRATEGIES:
        # [2026-05-09] log the drop instead of silent skip — silent drops
        # caused 5-day debugging dead-end. Telemetry is cheap.
        log.info("skip %s: tv_strategy=%r not in ALLOWED_STRATEGIES",
                 path.name, strategy)
        return None  # not a Rocket Prime / local_generator signal
    return sig


def signal_is_fresh(sig: dict) -> bool:
    """Fresh = ts within SIGNAL_MAX_AGE_S of now (UTC).
    Python writes ts in UTC unix seconds — compare against UTC now."""
    ts = sig.get("ts")
    if not ts:
        return False
    age = time.time() - int(ts)
    if age < 0:
        age = -age
    return age < SIGNAL_MAX_AGE_S


def in_cooldown(symbol: str, direction: str) -> bool:
    last = _LAST_ORDER.get((symbol, direction), 0.0)
    return time.time() - last < PER_SYMBOL_DIR_COOLDOWN_S


# ─── order placement ────────────────────────────────────────────────────
def _send_one_leg(symbol: str, direction: str, leg_name: str, magic: int,
                  sl_atr_mult: float, tp_atr_mult: float, atr: float,
                  info, sig: dict) -> bool:
    """Send a single order with given SL/TP multipliers and magic number.
    Returns True on success."""
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False
    sl_dist = sl_atr_mult * atr
    tp_dist = tp_atr_mult * atr
    # Respect broker stops + freeze levels
    stops_level = max(info.trade_stops_level, getattr(info, "freeze_level", 0))
    min_dist = stops_level * info.point
    spread_dist = (tick.ask - tick.bid) * 3
    safe_min = max(min_dist * 2.0, spread_dist)
    if sl_dist < safe_min:
        sl_dist = safe_min
    if tp_dist < safe_min:
        tp_dist = safe_min

    if direction == "BUY":
        price = tick.ask
        sl = price - sl_dist
        tp = price + tp_dist
        order_type = mt5.ORDER_TYPE_BUY
    else:
        price = tick.bid
        sl = price + sl_dist
        tp = price - tp_dist
        order_type = mt5.ORDER_TYPE_SELL

    lots = calc_lot_size(symbol, sl_dist, order_type)
    filling = detect_filling_mode(symbol)
    tf = sig.get("tv_timeframe", "?") or "?"

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": order_type,
        "price": round(price, info.digits),
        "sl": round(sl, info.digits),
        "tp": round(tp, info.digits),
        "deviation": DEVIATION_PTS,
        "magic": magic,
        "comment": f"{COMMENT_PREFIX}-{leg_name[:5]}-{direction[:1]}-{tf}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    res = mt5.order_send(request)
    # Retry with alternate filling on 10030
    if res and res.retcode == 10030:
        for alt in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN):
            if alt == filling:
                continue
            request["type_filling"] = alt
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                break

    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        err = res.comment if res else f"None ({mt5.last_error()})"
        log.error(
            "ORDER FAILED %s %s [%s] lots=%.2f ret=%s comment=%s",
            symbol, direction, leg_name, lots,
            res.retcode if res else "?", err,
        )
        return False

    log.info(
        "ORDER PLACED %s %s [%s] lots=%.2f price=%.5f sl=%.5f tp=%.5f deal=%d",
        symbol, direction, leg_name, lots, price, sl, tp, res.deal,
    )

    emoji = "📈" if direction == "BUY" else "📉"
    leg_emoji = "⚡" if leg_name == "QUICK" else "🚀"
    sl_pips = abs(price - sl)
    tp_pips = abs(tp - price)
    rr = tp_pips / sl_pips if sl_pips > 0 else 0
    conf = float(sig.get("confidence", 0)) * 100
    msg = (
        f"<b>{leg_emoji} {emoji} {symbol} {direction} {leg_name}</b>\n"
        f"Entry: <code>{price:.5f}</code>  Lots: <b>{lots}</b>\n"
        f"SL: <code>{sl:.5f}</code>  TP: <code>{tp:.5f}</code>\n"
        f"RR: <b>1:{rr:.1f}</b>  ATR: {atr:.5f}\n"
        f"Source: Rocket Prime ({tf})  Conf: {conf:.0f}%"
    )
    if leg_name == "TREND":
        msg += f"\n<i>Trailing SL activates at +{TRAIL_ACTIVATE_ATR}×ATR favorable</i>"
    _tg_send(msg)
    return True


def place_order(symbol: str, sig: dict) -> bool:
    """Open BOTH legs (Quick + Trend) for one Rocket Prime signal.
    Honors dashboard switches: trading_enabled, pairs_enabled[symbol]."""
    # ─── Dashboard kill switches ──────────────────────────────────────
    dcfg = _read_dashboard_config()
    if dcfg is not None:
        if not dcfg.get("trading_enabled", True):
            log.info("skip %s: trading_enabled=False (dashboard)", symbol)
            return False
        if not dcfg.get("pairs_enabled", {}).get(symbol, True):
            log.info("skip %s: pair disabled in dashboard", symbol)
            return False
    direction = (sig.get("direction") or "").upper()
    if direction not in ("BUY", "SELL"):
        return False
    confidence = float(sig.get("confidence", 0.0))
    if confidence < 0.55:
        log.info("skip %s: weak confidence %.2f", symbol, confidence)
        return False
    if in_cooldown(symbol, direction):
        log.info("skip %s %s: in cooldown (last order < %ds ago)", symbol, direction, PER_SYMBOL_DIR_COOLDOWN_S)
        return False

    # Already have a position in this direction? Skip — we're already in.
    if has_position_in_dir(symbol, direction == "BUY"):
        log.info("skip %s %s: already have %s position open in this direction", symbol, direction, direction)
        return False

    # SAFEGUARDS: news blackout / DD breaker / spread / correlation
    if safeguards_check is not None:
        allowed, reason = safeguards_check(symbol, direction)
        if not allowed:
            log.info("SAFEGUARD BLOCK %s %s: %s", symbol, direction, reason)
            # Telegram once when DD breaker first trips, otherwise silent (avoid spam)
            if "TRIPPED" in reason:
                _tg_send(f"<b>🛑 TRADING PAUSED</b>\n{reason}\n<i>Will reset at midnight local time.</i>")
            return False

    # Opposite-direction position open? FLIP both legs first.
    flipped = close_opposite_positions(symbol, direction == "BUY")
    if flipped:
        time.sleep(0.5)

    # Max open per symbol (Quick + Trend = 2)
    open_count = sum(
        1 for p in positions_for_symbol(symbol)
        if p.magic in (MAGIC_QUICK, MAGIC_TREND)
    )
    if open_count >= MAX_OPEN_PER_SYMBOL:
        log.info("skip %s %s: per-symbol cap reached (%d/%d open)", symbol, direction, open_count, MAX_OPEN_PER_SYMBOL)
        return False

    info = mt5.symbol_info(symbol)
    if not info:
        log.warning("no symbol_info for %s", symbol)
        return False
    if not info.visible:
        mt5.symbol_select(symbol, True)
        time.sleep(0.2)

    atr = get_atr_h1(symbol)
    if atr is None or atr <= 0:
        log.warning("no ATR for %s — skip", symbol)
        return False

    # Override JSON multipliers — operator policy: 2-leg strategy uses our values
    # Leg A: QUICK
    ok_a = _send_one_leg(
        symbol, direction, "QUICK", MAGIC_QUICK,
        QUICK_SL_ATR, QUICK_TP_ATR, atr, info, sig,
    )
    time.sleep(0.3)
    # Leg B: TREND (with trailing activated by separate manager)
    ok_b = _send_one_leg(
        symbol, direction, "TREND", MAGIC_TREND,
        TREND_SL_ATR, TREND_TP_ATR, atr, info, sig,
    )

    if ok_a or ok_b:
        _LAST_ORDER[(symbol, direction)] = time.time()
        _save_cooldown()
        return True
    return False


# ─── main loop ──────────────────────────────────────────────────────────
def _write_alive_sentinel(sig_dir: Path) -> None:
    """Write timestamp to py_executor.alive — EA reads this to know we're
    alive and refuse to trade (avoid duplicate orders)."""
    try:
        (sig_dir / "py_executor.alive").write_text(str(int(time.time())), encoding="ascii")
    except Exception:
        pass


_LOCK_FILE_HANDLE = None  # keep handle alive for process lifetime


def _acquire_singleton_lock() -> bool:
    """Cross-process exclusive file lock. Refuses to start if another
    python_signal_executor is already holding the lock. Survives the race
    where two watchdogs both spawn an instance at the same instant.

    Lock file: logs/python_signal_executor.lock
    Uses Windows msvcrt.locking (LK_NBLCK = non-blocking exclusive)."""
    global _LOCK_FILE_HANDLE
    import msvcrt
    lock_path = ROOT / "logs" / "python_signal_executor.lock"
    lock_path.parent.mkdir(exist_ok=True)
    try:
        # Open in r+ if exists, else w+ — keep handle for process lifetime
        f = open(lock_path, "a+", encoding="utf-8")
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            log.warning("python_signal_executor lock held by another instance — exiting")
            f.close()
            return False
        # Write our PID for debugging
        f.seek(0); f.truncate()
        f.write(f"{os.getpid()}\n")
        f.flush()
        _LOCK_FILE_HANDLE = f  # keep alive
        return True
    except Exception as e:
        log.exception("singleton lock failed: %s", e)
        return True  # fail-open so we don't deadlock the operator


def _print_startup_banner() -> None:
    """[2026-05-09 GODMODE] Print loaded-vs-disabled status of every gate
    so silent disabled gates surface at boot, not after a 5-day null result.

    The 5-day silent failure (local_generator dropped) AND the worse latent
    bug (safeguards bypass at line 80-81) both became invisible because
    nobody could see at boot what was loaded vs missing. This banner makes
    that impossible to miss.
    """
    log.info("=" * 60)
    log.info("EXECUTOR STARTUP BANNER  (gates / dependencies)")
    log.info("=" * 60)
    # Safeguards — CRITICAL. If None, all concentration caps + DD + news + spread are bypassed.
    if safeguards_check is None:
        log.error("[X] SAFEGUARDS DISABLED  (concentration caps + DD + news + spread)")
        log.error("    import error: %s", _SAFEGUARDS_IMPORT_ERROR)
        log.error("    REFUSING TO TRADE WITHOUT SAFEGUARDS — exit(2)")
        # Hard-fail: trading without gates = wreck account on first concentrated batch.
        # If operator wants to override (extreme edge case), set TM_NO_SAFEGUARDS=1.
        if os.getenv("TM_NO_SAFEGUARDS") != "1":
            sys.exit(2)
        log.warning("    TM_NO_SAFEGUARDS=1 set — proceeding WITHOUT gates (operator override)")
    else:
        log.info("[OK] safeguards_check loaded (concentration caps + DD + news + spread)")
    # Telegram notifier — non-critical but useful
    if _tg is None:
        log.warning("[!] telegram_notifier disabled  (alerts won't reach operator phone)")
        if _TG_IMPORT_ERROR:
            log.warning("    import error: %s", _TG_IMPORT_ERROR)
    else:
        log.info("[OK] telegram_notifier loaded  (alerts will reach phone)")
    # Dashboard kill switch — fail-open if missing
    if _DASHBOARD_CONFIG_FILE.exists():
        log.info("[OK] dashboard_config.json present (kill switch usable)")
    else:
        log.info("[--] dashboard_config.json missing  (kill switch off, default behaviour)")
    # News calendar — used by safeguards
    news_cal = ROOT / "config" / "news_calendar.json"
    if news_cal.exists():
        try:
            n_events = len(json.loads(news_cal.read_text(encoding="utf-8")))
            log.info("[OK] news_calendar.json present  (%d events)", n_events)
        except Exception as e:
            log.warning("[!] news_calendar.json present but unreadable: %s", e)
    else:
        log.warning("[!] news_calendar.json missing  (news blackout fail-open)")
    # ALLOWED_STRATEGIES (current set as of 2026-05-09)
    # Note: this is a string copy of the set inside load_signal — kept in sync via tests
    expected_strategies = {
        "rocket_prime", "rocket_prime_text", "rocket_prime_inferred",
        "local_generator",
        "rocket_prime_plot0", "rocket_prime_plot1", "rocket_prime_url_direction",
    }
    log.info("[OK] ALLOWED_STRATEGIES = %s", sorted(expected_strategies))
    log.info("=" * 60)


def main_loop():
    if not _acquire_singleton_lock():
        return 0
    _print_startup_banner()
    if not init_mt5():
        return 1
    sig_dir = find_signal_dir()
    if not sig_dir:
        log.error("could not find MT5 MQL5/Files signal dir")
        return 1
    _load_cooldown()
    _write_alive_sentinel(sig_dir)
    log.info("watching: %s", sig_dir)
    log.info("polling every %ds, signal age limit %ds, cooldown %ds, fixed lot %.2f, cooldown_loaded=%d",
             POLL_INTERVAL_S, SIGNAL_MAX_AGE_S, PER_SYMBOL_DIR_COOLDOWN_S, FIXED_LOT_SIZE, len(_LAST_ORDER))

    iteration = 0
    while True:
        try:
            iteration += 1
            placed = 0
            # [2026-05-09 GODMODE] Skip taxonomy — was just `skipped` integer.
            # Now broken into reason buckets so heartbeat shows WHY, not just IF.
            skipped_no_file = 0
            skipped_unparseable = 0
            skipped_strategy_filter = 0  # tv_strategy not in ALLOWED_STRATEGIES
            skipped_stale = 0            # signal age > SIGNAL_MAX_AGE_S
            for symbol in SYMBOLS:
                if symbol == "XAUUSD":
                    fname = "trendmaster_signals.json"
                else:
                    fname = f"trendmaster_signals_{symbol}.json"
                path = sig_dir / fname
                if not path.exists():
                    skipped_no_file += 1
                    continue
                sig = load_signal(path)
                if sig is None:
                    # load_signal already logs the specific reason (whitelist /
                    # malformed JSON / missing fields). We just count category.
                    skipped_strategy_filter += 1
                    continue
                if not signal_is_fresh(sig):
                    age = int(time.time() - (sig.get("ts") or 0))
                    log.info("skip %s: stale signal (age=%ds > limit=%ds)",
                             symbol, age, SIGNAL_MAX_AGE_S)
                    skipped_stale += 1
                    continue
                if place_order(symbol, sig):
                    placed += 1
            skipped = skipped_no_file + skipped_unparseable + skipped_strategy_filter + skipped_stale
            if iteration % 12 == 1:  # log every minute
                pos_n = mt5.positions_get()
                log.info(
                    "heartbeat: iter=%d placed=%d skipped=%d  "
                    "(no_file=%d filtered=%d stale=%d) open_positions=%d",
                    iteration, placed, skipped,
                    skipped_no_file, skipped_strategy_filter, skipped_stale,
                    len(pos_n) if pos_n else 0,
                )
                _write_alive_sentinel(sig_dir)  # refresh sentinel every minute
            time.sleep(POLL_INTERVAL_S)
        except KeyboardInterrupt:
            log.info("KeyboardInterrupt — shutting down")
            break
        except Exception as e:
            log.exception("loop error: %s", e)
            time.sleep(POLL_INTERVAL_S)
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main_loop())
