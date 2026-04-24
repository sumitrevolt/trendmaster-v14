"""Unit tests for ai_trading_agents.market_calendar."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_trading_agents.market_calendar import (
    is_holiday, is_market_open, is_weekend_closed,
)


def _dt(y, mo, d, h=12):
    return datetime(y, mo, d, h, 0, 0, tzinfo=timezone.utc)


def test_crypto_always_open():
    # Saturday, Christmas — still open for crypto.
    sat = _dt(2026, 1, 3, 15)
    xmas = _dt(2026, 12, 25, 12)
    for sym in ("BTCUSD", "ETHUSD"):
        open_, _ = is_market_open(sym, now_utc=sat)
        assert open_
        open_, _ = is_market_open(sym, now_utc=xmas)
        assert open_


def test_forex_closed_weekend():
    # Saturday.
    sat = _dt(2026, 1, 3, 12)
    open_, reason = is_market_open("EURUSD", now_utc=sat)
    assert open_ is False
    assert "Saturday" in reason or "weekend" in reason.lower()


def test_forex_closed_friday_late():
    # Friday 23:00 UTC.
    fri_late = _dt(2026, 1, 2, 23)
    open_, reason = is_market_open("EURUSD", now_utc=fri_late)
    assert open_ is False


def test_forex_open_weekday():
    wed = _dt(2026, 1, 7, 12)
    open_, _ = is_market_open("EURUSD", now_utc=wed)
    assert open_ is True


def test_christmas_closes_all():
    xmas = _dt(2026, 12, 25, 12)
    open_, reason = is_market_open("XAUUSD", now_utc=xmas)
    assert open_ is False
    assert "Christmas" in reason or "holiday" in reason.lower()


def test_new_years_closes_all():
    ny = _dt(2026, 1, 1, 12)
    open_, reason = is_market_open("XAUUSD", now_utc=ny)
    assert open_ is False


def test_us_holiday_closes_usd_but_not_jpy_pairs():
    # Thanksgiving affects USD/metals/commodities, not JPY-only pairs.
    thx = _dt(2026, 11, 26, 15)
    usd_open, _ = is_market_open("USDCAD", now_utc=thx)
    # Both USD and CAD are impacted; should be closed.
    assert usd_open is False
    # EURJPY — neither EUR nor JPY is flagged for Thanksgiving.
    jpy_open, _ = is_market_open("EURJPY", now_utc=thx)
    assert jpy_open is True


def test_is_weekend_closed_explicit():
    fri = _dt(2026, 1, 2, 10)
    assert is_weekend_closed(fri, "EURUSD") == (False, "weekday")
    sun_open = _dt(2026, 1, 4, 23)
    # Sunday 23:00 UTC → back open.
    assert is_weekend_closed(sun_open, "EURUSD")[0] is False


def test_is_holiday_returns_false_on_normal_day():
    wed = _dt(2026, 1, 7, 12)
    closed, _ = is_holiday(wed, "EURUSD")
    assert closed is False


def test_unknown_symbol_still_gated_by_weekend():
    sat = _dt(2026, 1, 3, 12)
    open_, _ = is_market_open("FOOBAR", now_utc=sat)
    assert open_ is False
