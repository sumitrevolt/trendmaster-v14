"""Safety checks the Python executor consults before placing any order.

Each function returns (allowed: bool, reason: str). The executor calls them
in sequence; the first one to refuse stops the trade and logs the reason.

Modules:
    1. news_blackout_active(symbol)         — skip trades around high-impact news
    2. drawdown_breaker_tripped()           — pause if today's DD > 5%
    3. spread_too_wide(symbol)              — skip if spread > 50% of ATR
    4. correlation_overexposed(symbol, dir) — limit USD exposure across pairs
    5. mt5_health_check()                   — detect disconnects (used by watchdog)
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Tuple

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("safeguards")

# Persistent state
_DD_STATE_PATH = LOG_DIR / "dd_state.json"

# ──────────────────────────────────────────────────────────────────────
# 1. NEWS BLACKOUT
# ──────────────────────────────────────────────────────────────────────
NEWS_LEAD_MIN = 60   # block trades 60 min before high-impact news
NEWS_LAG_MIN = 30    # block trades 30 min after high-impact news
NEWS_CALENDAR_PATH = ROOT / "config" / "news_calendar.json"


def _currencies_for(symbol: str):
    """Extract currencies the symbol is exposed to.
    EURUSD → ('EUR', 'USD'); XAUUSD → ('XAU', 'USD'); BTCUSD → ('BTC', 'USD')."""
    s = symbol.upper()
    # 6-char standard FX
    if len(s) == 6:
        return (s[:3], s[3:])
    # Treat XAU/XAG/XTI/XBR/XNG as commodity vs USD
    if len(s) == 6 and s[:3] in ("XAU", "XAG", "XTI", "XBR", "XNG"):
        return (s[:3], "USD")
    return (s, "USD")


def news_blackout_active(symbol: str) -> Tuple[bool, str]:
    """True (blocked) if a high-impact news event for this symbol's currency
    is within [-LEAD, +LAG] minutes from now."""
    if not NEWS_CALENDAR_PATH.exists():
        return False, "no calendar"
    try:
        events = json.loads(NEWS_CALENDAR_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("news calendar read failed: %s", e)
        return False, "calendar parse error"

    now = datetime.now(timezone.utc)
    syms = set(_currencies_for(symbol))
    for ev in events:
        impact = (ev.get("impact") or "").lower()
        if impact != "high":
            continue
        cur = (ev.get("currency") or "").upper()
        if cur not in syms:
            continue
        try:
            ev_time = datetime.fromisoformat(ev["datetime_utc"].replace("Z", "+00:00"))
        except Exception:
            continue
        lead = ev_time - timedelta(minutes=NEWS_LEAD_MIN)
        lag = ev_time + timedelta(minutes=NEWS_LAG_MIN)
        if lead <= now <= lag:
            return True, f"news blackout: {cur} {ev.get('event','?')} @ {ev_time.strftime('%H:%M')}UTC"
    return False, "no nearby news"


# ──────────────────────────────────────────────────────────────────────
# 2. DAILY DRAWDOWN CIRCUIT BREAKER
# ──────────────────────────────────────────────────────────────────────
MAX_DAILY_DD_PCT = 5.0  # if today's drawdown exceeds 5% of start equity, halt


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_dd_state() -> dict:
    if _DD_STATE_PATH.exists():
        try:
            return json.loads(_DD_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_dd_state(d: dict) -> None:
    try:
        _DD_STATE_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


def drawdown_breaker_tripped() -> Tuple[bool, str]:
    """Check today's drawdown vs start-of-day equity.
    Stores start_equity per day. If equity drops > MAX_DAILY_DD_PCT, returns True."""
    ai = mt5.account_info()
    if not ai:
        return False, "no account info"
    today = _today_str()
    state = _load_dd_state()
    if state.get("date") != today:
        # New day — record start equity
        state = {"date": today, "start_equity": ai.equity, "tripped": False, "trip_at": None}
        _save_dd_state(state)
        return False, "new day, recorded start"
    # Sticky trip — once tripped, stays tripped until midnight
    if state.get("tripped"):
        return True, f"DD tripped earlier today at equity={state.get('trip_at')}"
    start_eq = state.get("start_equity", ai.equity)
    dd_pct = (start_eq - ai.equity) / start_eq * 100 if start_eq > 0 else 0
    if dd_pct >= MAX_DAILY_DD_PCT:
        state["tripped"] = True
        state["trip_at"] = ai.equity
        state["trip_dd_pct"] = round(dd_pct, 2)
        _save_dd_state(state)
        return True, f"DD breaker TRIPPED: {dd_pct:.1f}% loss today (start={start_eq:.2f}, now={ai.equity:.2f})"
    return False, f"DD ok: {dd_pct:.2f}% today"


# ──────────────────────────────────────────────────────────────────────
# 3. SPREAD CHECK
# ──────────────────────────────────────────────────────────────────────
MAX_SPREAD_ATR_RATIO = 0.5  # spread > 50% of ATR(H1) → reject (truly broken price)


def spread_too_wide(symbol: str) -> Tuple[bool, str]:
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if not info or not tick:
        return False, "no tick"
    spread_pr = tick.ask - tick.bid
    if spread_pr <= 0:
        return False, "no spread (likely closed market)"
    # Get ATR(H1)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 15)
    if rates is None or len(rates) < 15:
        return False, "no ATR data"
    trs = []
    for i in range(1, len(rates)):
        h, l, pc = rates[i]["high"], rates[i]["low"], rates[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else 0
    if atr <= 0:
        return False, "atr=0"
    ratio = spread_pr / atr
    if ratio > MAX_SPREAD_ATR_RATIO:
        return True, f"spread too wide: {ratio*100:.0f}% of ATR (cap {MAX_SPREAD_ATR_RATIO*100:.0f}%)"
    return False, f"spread ok: {ratio*100:.0f}% of ATR"


# ──────────────────────────────────────────────────────────────────────
# 4. CORRELATION GUARD (USD exposure)
# ──────────────────────────────────────────────────────────────────────
MAX_SAME_SIDE_USD_POSITIONS = 3  # at most 3 positions tilting same way on USD


def _usd_side(symbol: str, is_buy: bool) -> int:
    """+1 = long USD; -1 = short USD; 0 = no USD exposure."""
    s = symbol.upper()
    if s.endswith("USD") or s.startswith("XAU") or s.startswith("XAG") or s in ("BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD", "XNGUSD"):
        # XXXUSD — BUY = short USD, SELL = long USD
        return -1 if is_buy else +1
    if s.startswith("USD"):
        # USDXXX — BUY = long USD, SELL = short USD
        return +1 if is_buy else -1
    return 0  # cross-pair (EURJPY etc.) — no direct USD exposure


def correlation_overexposed(symbol: str, direction: str) -> Tuple[bool, str]:
    """Reject if adding this trade would put us > MAX same-side USD positions."""
    pos = mt5.positions_get() or []
    cur_long = 0
    cur_short = 0
    for p in pos:
        side = _usd_side(p.symbol, p.type == mt5.ORDER_TYPE_BUY)
        if side > 0:
            cur_long += 1
        elif side < 0:
            cur_short += 1
    new_side = _usd_side(symbol, direction.upper() == "BUY")
    if new_side > 0 and cur_long >= MAX_SAME_SIDE_USD_POSITIONS:
        return True, f"already {cur_long} long-USD positions (cap {MAX_SAME_SIDE_USD_POSITIONS})"
    if new_side < 0 and cur_short >= MAX_SAME_SIDE_USD_POSITIONS:
        return True, f"already {cur_short} short-USD positions (cap {MAX_SAME_SIDE_USD_POSITIONS})"
    return False, f"USD exposure ok (long={cur_long}, short={cur_short})"


# ──────────────────────────────────────────────────────────────────────
# 5. MT5 HEALTH CHECK (used by watchdog)
# ──────────────────────────────────────────────────────────────────────
def mt5_health_check() -> Tuple[bool, str]:
    """Return (healthy, msg). False if disconnected from broker."""
    if not mt5.initialize():
        return False, f"mt5.initialize failed: {mt5.last_error()}"
    ti = mt5.terminal_info()
    if not ti:
        return False, "no terminal_info"
    if not ti.connected:
        return False, "MT5 disconnected from broker"
    ai = mt5.account_info()
    if not ai:
        return False, "no account_info (login failed?)"
    return True, f"MT5 ok build={ti.build} balance=${ai.balance:.2f}"


# ──────────────────────────────────────────────────────────────────────
# Master gate — called by executor
# ──────────────────────────────────────────────────────────────────────
def check_all(symbol: str, direction: str) -> Tuple[bool, str]:
    """Run all order-time safeguards. Returns (allowed, reason).
    Order matters: cheapest checks first."""
    # Drawdown first (account-level, no per-symbol cost)
    blocked, reason = drawdown_breaker_tripped()
    if blocked:
        return False, reason
    # News (cheap file read)
    blocked, reason = news_blackout_active(symbol)
    if blocked:
        return False, reason
    # Correlation (cheap MT5 query)
    blocked, reason = correlation_overexposed(symbol, direction)
    if blocked:
        return False, reason
    # Spread (more expensive ATR fetch, last)
    blocked, reason = spread_too_wide(symbol)
    if blocked:
        return False, reason
    return True, "all safeguards passed"


if __name__ == "__main__":
    # CLI smoke test
    mt5.initialize()
    print("=== safeguards smoke test ===")
    for fn_name, fn in [
        ("DD breaker", lambda: drawdown_breaker_tripped()),
        ("news XAUUSD", lambda: news_blackout_active("XAUUSD")),
        ("news EURUSD", lambda: news_blackout_active("EURUSD")),
        ("spread XAUUSD", lambda: spread_too_wide("XAUUSD")),
        ("spread EURUSD", lambda: spread_too_wide("EURUSD")),
        ("corr XAUUSD BUY", lambda: correlation_overexposed("XAUUSD", "BUY")),
        ("MT5 health", lambda: mt5_health_check()),
    ]:
        blocked, reason = fn()
        mark = "BLOCK" if blocked else "OK   "
        print(f"  [{mark}] {fn_name}: {reason}")
    mt5.shutdown()
