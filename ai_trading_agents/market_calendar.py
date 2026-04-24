"""
market_calendar.py — weekend + holiday gate for TrendMaster v14.

Why this exists
---------------
The brain currently ticks 24/7 — including weekends when forex markets
are closed and major market holidays (Christmas, Thanksgiving, New Year,
May Day, Golden Week, etc.). That's:

  * Wasted CPU and MT5 API load on dead markets.
  * False drift signals from spread/quote noise during thin liquidity.
  * Garbage feature rows entering the training data if we ever
    resumed live-capture.

This module supplies a single function `is_market_open(sym, now_utc)`
returning `(bool, reason)`. The brain can use it as a gate before
pulling bars. Institutional systems universally have one of these.

Coverage
--------
  * Weekends — Saturday 22:00 UTC through Sunday 22:00 UTC closed for
    forex and CFDs.
  * US federal holidays — closes XAUUSD, XAGUSD, USD pairs, crypto stays
    24/7.
  * Major regional holidays — UK (BOE), Japan (BOJ), Eurozone, Australia,
    Canada.
  * Christmas Day, New Year's Day — every major market.
  * Crypto stays 24/7 — `BTCUSD` / `ETHUSD` not gated by this module.

Calendar is static, hand-curated — same pattern as `news_calendar.json`.
File: `config/market_holidays.json`. Refresh yearly.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("market_calendar")


# ---------- symbol → market classification ----------
_FOREX = {
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCAD",
    "USDCHF",
    "AUDUSD",
    "NZDUSD",
    "EURJPY",
    "GBPJPY",
    "EURGBP",
    "AUDJPY",
    "CADJPY",
}
_METALS = {"XAUUSD", "XAGUSD"}
_COMMODITIES = {"XTIUSD", "XBRUSD", "XNGUSD"}
_CRYPTO = {"BTCUSD", "ETHUSD"}


def _market(sym: str) -> str:
    if sym in _CRYPTO:
        return "CRYPTO"
    if sym in _METALS:
        return "METALS"
    if sym in _COMMODITIES:
        return "COMMODITIES"
    if sym in _FOREX:
        return "FOREX"
    return "UNKNOWN"


# Crypto trades 24/7 — never gated.
# Forex closes Friday 22:00 UTC through Sunday 22:00 UTC.
# Metals + commodities follow the forex close.


def is_weekend_closed(now_utc: datetime, sym: str) -> Tuple[bool, str]:
    """Returns (closed, reason). Crypto returns open regardless."""
    if _market(sym) == "CRYPTO":
        return False, "crypto-24x7"
    dow = now_utc.weekday()  # Mon=0 ... Sun=6
    hour = now_utc.hour
    # Friday after 22:00 UTC → closed.
    if dow == 4 and hour >= 22:
        return True, "weekend close (Fri 22:00 UTC)"
    # All of Saturday closed.
    if dow == 5:
        return True, "weekend (Saturday)"
    # Sunday before 22:00 UTC → closed.
    if dow == 6 and hour < 22:
        return True, "weekend (Sunday pre-open)"
    return False, "weekday"


# =====================================================================
# Holiday table loader
# =====================================================================
_CACHE: dict = {"loaded_ts": 0.0, "holidays": []}
_CACHE_TTL_S = 3600.0


def _load_holidays(path: Optional[Path] = None) -> list:
    """Read `config/market_holidays.json`. Cached for 1h.

    Schema:
        [
          {"date": "2026-12-25", "name": "Christmas Day",
           "markets": ["ALL"]},
          {"date": "2026-01-01", "name": "New Year's Day",
           "markets": ["ALL"]},
          {"date": "2026-07-04", "name": "US Independence Day",
           "markets": ["METALS", "COMMODITIES", "FOREX_USD"]},
          ...
        ]
    `markets` values: ALL, METALS, COMMODITIES, FOREX_USD, FOREX_EUR,
    FOREX_GBP, FOREX_JPY, CRYPTO. CRYPTO only closes on the rare
    exchange-wide outages you hand-add.
    """
    import time as _t

    now = _t.time()
    if (now - _CACHE["loaded_ts"]) < _CACHE_TTL_S and _CACHE["holidays"]:
        return _CACHE["holidays"]
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config" / "market_holidays.json"
    items: list = []
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f) or []
    except Exception as e:
        logger.debug("market_holidays load failed: %s", e)
        items = []
    _CACHE["loaded_ts"] = now
    _CACHE["holidays"] = items
    return items


def _sym_markets(sym: str) -> set:
    """Which market-classification tags apply to this symbol.

    Crypto is NEVER matched by the `ALL` tag — crypto exchanges run
    24/7/365 and are only closed for explicit CRYPTO-marked outages
    that an operator must hand-add.
    """
    mkt = _market(sym)
    # Crypto only matches explicit "CRYPTO" entries.
    if mkt == "CRYPTO":
        return {"CRYPTO"}
    tags = {mkt, "ALL"}
    # Forex sub-currencies — FOREX_USD matches USDCAD, EURUSD, GBPUSD, etc.
    if mkt == "FOREX":
        for cur in ("USD", "EUR", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD"):
            if cur in sym:
                tags.add(f"FOREX_{cur}")
    elif mkt == "METALS":
        tags.add("FOREX_USD")  # gold/silver price'd in USD
    elif mkt == "COMMODITIES":
        tags.add("FOREX_USD")
    return tags


def is_holiday(now_utc: datetime, sym: str) -> Tuple[bool, str]:
    date_str = now_utc.strftime("%Y-%m-%d")
    tags = _sym_markets(sym)
    for ev in _load_holidays():
        if ev.get("date") != date_str:
            continue
        ev_markets = set(ev.get("markets") or [])
        if ev_markets & tags:
            return True, f"holiday: {ev.get('name', 'unknown')}"
    return False, "no holiday"


def is_market_open(sym: str, now_utc: Optional[datetime] = None) -> Tuple[bool, str]:
    """Single-entry gate used by the brain.

    Returns (open_bool, reason_string). open_bool=False => the brain
    should veto this tick for this symbol.
    """
    now = now_utc or datetime.now(timezone.utc)
    closed, reason = is_weekend_closed(now, sym)
    if closed:
        return False, reason
    holiday, hol_reason = is_holiday(now, sym)
    if holiday:
        return False, hol_reason
    return True, "open"


__all__ = ["is_weekend_closed", "is_holiday", "is_market_open"]
