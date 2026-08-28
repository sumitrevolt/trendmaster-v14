"""Trailing stop loss manager — watches TREND-leg positions, trails SL.

Runs alongside python_signal_executor.py. Polls every 10 seconds. For each
position with magic == MAGIC_TREND:
  1. Check if price has moved favorably by at least TRAIL_ACTIVATE_ATR × ATR
     since entry. If not, leave SL at original.
  2. Once activated, candidate SL = current_price ± (TRAIL_DISTANCE_ATR × ATR)
     in the favorable direction.
  3. Update SL via TRADE_ACTION_SLTP only if the candidate is BETTER (further
     from current price in our favor) than the existing SL. Never tighten
     against ourselves.

Telegram notification fires the FIRST time trailing activates per position
(so we don't spam every 10s).
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Dict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "trailing_stop.log"

_handlers = [logging.FileHandler(LOG_PATH, encoding="utf-8")]
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
log = logging.getLogger("trail_mgr")

try:
    from ai_trading_agents.telegram_notifier import get_notifier
    _tg = get_notifier()
except Exception:
    _tg = None


def _tg_send(text: str) -> None:
    try:
        if _tg and _tg.enabled:
            _tg.send(text)
    except Exception:
        pass


# ─── config (mirrors executor) ──────────────────────────────────────────
MAGIC_TREND = 14015
POLL_INTERVAL_S = 10
TRAIL_ACTIVATE_ATR = 1.0
TRAIL_DISTANCE_ATR = 1.5

# Track per-ticket activation state so we only Telegram-notify once
_ACTIVATED: Dict[int, bool] = {}


def get_atr_h1(symbol, period=14):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, period + 1)
    if rates is None or len(rates) < period + 1:
        return None
    trs = []
    for i in range(1, len(rates)):
        h, l, pc = rates[i]["high"], rates[i]["low"], rates[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else None


def init_mt5() -> bool:
    if not mt5.initialize():
        log.error("mt5.initialize failed: %s", mt5.last_error())
        return False
    ti = mt5.terminal_info()
    log.info("MT5 connected build=%s trade_allowed=%s", ti.build if ti else "?",
             ti.trade_allowed if ti else False)
    return True


def manage_trailing():
    """Single pass: check all TREND positions, update SL where applicable."""
    pos = mt5.positions_get() or []
    trend_pos = [p for p in pos if p.magic == MAGIC_TREND]
    if not trend_pos:
        return 0, 0
    updated = 0
    activated = 0
    for p in trend_pos:
        info = mt5.symbol_info(p.symbol)
        tick = mt5.symbol_info_tick(p.symbol)
        if not info or not tick:
            continue
        atr = get_atr_h1(p.symbol)
        if not atr or atr <= 0:
            continue
        is_buy = p.type == mt5.ORDER_TYPE_BUY
        entry = p.price_open
        cur_price = tick.bid if is_buy else tick.ask  # exit price for our side
        # Favorable move (positive when in profit)
        favorable = (cur_price - entry) if is_buy else (entry - cur_price)
        activate_dist = TRAIL_ACTIVATE_ATR * atr
        if favorable < activate_dist:
            continue  # not yet in profit zone

        trail_dist = TRAIL_DISTANCE_ATR * atr
        if is_buy:
            candidate_sl = cur_price - trail_dist
        else:
            candidate_sl = cur_price + trail_dist
        candidate_sl = round(candidate_sl, info.digits)

        # Don't tighten against ourselves
        cur_sl = p.sl
        if cur_sl > 0:
            if is_buy and candidate_sl <= cur_sl:
                continue
            if (not is_buy) and candidate_sl >= cur_sl:
                continue

        # Send the SL update
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": p.ticket,
            "symbol": p.symbol,
            "sl": candidate_sl,
            "tp": p.tp,  # keep TP as-is
            "magic": p.magic,
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            updated += 1
            first_time = not _ACTIVATED.get(p.ticket, False)
            _ACTIVATED[p.ticket] = True
            if first_time:
                activated += 1
                log.info(
                    "TRAIL ACTIVATED %s %s ticket=%d entry=%.5f cur=%.5f sl=%.5f profit=%.2f",
                    p.symbol, "BUY" if is_buy else "SELL", p.ticket,
                    entry, cur_price, candidate_sl, p.profit,
                )
                _tg_send(
                    f"<b>📍 {p.symbol} TRAILING SL ACTIVE</b>\n"
                    f"Entry: <code>{entry:.5f}</code>  Now: <code>{cur_price:.5f}</code>\n"
                    f"SL moved to: <code>{candidate_sl:.5f}</code>\n"
                    f"Locked profit: <b>+{abs(candidate_sl - entry):.5f}</b> from entry\n"
                    f"<i>Riding the trend with {TRAIL_DISTANCE_ATR}×ATR trail</i>"
                )
            else:
                # Don't spam — just log subsequent updates
                log.info(
                    "TRAIL UPDATE %s ticket=%d sl: %.5f -> %.5f profit=%.2f",
                    p.symbol, p.ticket, cur_sl, candidate_sl, p.profit,
                )
        elif res:
            log.warning("TRAIL FAIL %s ticket=%d: ret=%s %s",
                        p.symbol, p.ticket, res.retcode, res.comment)
    return updated, activated


_LOCK_FILE_HANDLE = None


def _acquire_singleton_lock() -> bool:
    """File-lock based singleton — survives spawn races."""
    global _LOCK_FILE_HANDLE
    import os
    import msvcrt
    from pathlib import Path as _Path
    lock_path = _Path("C:/Users/Ratanshila/Documents/autmated trading/logs/trailing_stop_manager.lock")
    lock_path.parent.mkdir(exist_ok=True)
    try:
        f = open(lock_path, "a+", encoding="utf-8")
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            log.warning("trailing_stop_manager lock held — exiting")
            f.close()
            return False
        f.seek(0); f.truncate()
        f.write(f"{os.getpid()}\n")
        f.flush()
        _LOCK_FILE_HANDLE = f
        return True
    except Exception as e:
        log.exception("singleton lock failed: %s", e)
        return True


def main():
    if not _acquire_singleton_lock():
        return 0
    if not init_mt5():
        return 1
    log.info("Trailing manager started. Polling every %ds, activate=%g×ATR, distance=%g×ATR",
             POLL_INTERVAL_S, TRAIL_ACTIVATE_ATR, TRAIL_DISTANCE_ATR)
    iteration = 0
    while True:
        try:
            iteration += 1
            updated, activated = manage_trailing()
            if iteration % 30 == 1:  # every ~5 min
                pos = mt5.positions_get() or []
                trend_n = sum(1 for p in pos if p.magic == MAGIC_TREND)
                log.info("heartbeat iter=%d trend_positions=%d updates_this_round=%d activations=%d",
                         iteration, trend_n, updated, activated)
            time.sleep(POLL_INTERVAL_S)
        except KeyboardInterrupt:
            log.info("KeyboardInterrupt — exit")
            break
        except Exception as e:
            log.exception("loop error: %s", e)
            time.sleep(POLL_INTERVAL_S)
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
