"""Unit tests for ai_trading_agents.reentry_tracker.

Covers the six behaviors specified in the R11 spec:
  1. scan_for_sl_hits mints exactly one permit per new loss
  2. idempotency — scanning twice doesn't duplicate
  3. available_permit respects cooldown
  4. available_permit respects max_reentries / day
  5. available_permit respects max_age (expiry)
  6. consume marks used; used permits don't match again
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from ai_trading_agents.reentry_tracker import ReentryPermit, ReentryTracker


# ---------------------------------------------------------------------------
#                              FIXTURES
# ---------------------------------------------------------------------------
def _base_cfg() -> Dict[str, Any]:
    return {
        "enabled": True,
        "cooldown_minutes": 30,
        "size_mult": 0.7,
        "max_reentries": 1,
        "require_same_direction": True,
        "max_age_minutes": 180,
        "alert_telegram": False,
    }


def _make_sl_result(
    deal_id: int, symbol: str = "EURUSD", pnl: float = -10.0, r_mult: float = -1.0, ts: int | None = None
) -> Dict[str, Any]:
    """Build a trade_tracker-shaped recent_results entry that counts as an SL hit."""
    return {
        "ts": int(ts if ts is not None else time.time()),
        "symbol": symbol,
        "pnl": float(pnl),
        "r_mult": float(r_mult),
        "deal_id": int(deal_id),
    }


@pytest.fixture
def state_with_buy_direction():
    """State pre-stamped with last_signal_direction so minted permits
    carry a usable direction."""
    return {
        "recent_results": [],
        "reentry_permits": [],
        "last_signal_direction": {"EURUSD": "BUY"},
    }


# ---------------------------------------------------------------------------
#                         MINTING + IDEMPOTENCY
# ---------------------------------------------------------------------------
def test_scan_mints_one_permit_per_new_loss(state_with_buy_direction):
    cfg = _base_cfg()
    t = ReentryTracker(cfg)
    state = state_with_buy_direction
    state["recent_results"] = [
        _make_sl_result(deal_id=1001, r_mult=-1.0),
        _make_sl_result(deal_id=1002, r_mult=-1.05),
    ]
    minted = t.scan_for_sl_hits(state)
    assert len(minted) == 2
    assert {p.deal_id for p in minted} == {1001, 1002}
    # All should carry the stamped BUY direction.
    assert all(p.direction == "BUY" for p in minted)
    # And be persisted.
    assert len(state["reentry_permits"]) == 2


def test_scan_skips_scratch_losses(state_with_buy_direction):
    """Small losses that didn't hit the full stop don't earn a permit."""
    cfg = _base_cfg()
    t = ReentryTracker(cfg)
    state = state_with_buy_direction
    state["recent_results"] = [
        _make_sl_result(deal_id=2001, r_mult=-0.4, pnl=-4.0),  # scratch
        _make_sl_result(deal_id=2002, r_mult=-1.0, pnl=-10.0),  # real SL
    ]
    minted = t.scan_for_sl_hits(state)
    assert len(minted) == 1
    assert minted[0].deal_id == 2002


def test_scan_skips_wins(state_with_buy_direction):
    cfg = _base_cfg()
    t = ReentryTracker(cfg)
    state = state_with_buy_direction
    state["recent_results"] = [
        _make_sl_result(deal_id=3001, r_mult=1.5, pnl=15.0),
    ]
    minted = t.scan_for_sl_hits(state)
    assert len(minted) == 0


def test_scan_idempotent(state_with_buy_direction):
    """Scanning the same recent_results twice must not duplicate permits."""
    cfg = _base_cfg()
    t = ReentryTracker(cfg)
    state = state_with_buy_direction
    state["recent_results"] = [
        _make_sl_result(deal_id=4001),
    ]
    first = t.scan_for_sl_hits(state)
    assert len(first) == 1
    second = t.scan_for_sl_hits(state)
    assert len(second) == 0
    assert len(state["reentry_permits"]) == 1


def test_scan_survives_restart(state_with_buy_direction):
    """A fresh ReentryTracker instance must hydrate seen-deal-ids from state."""
    cfg = _base_cfg()
    # First run.
    t1 = ReentryTracker(cfg)
    state = state_with_buy_direction
    state["recent_results"] = [_make_sl_result(deal_id=5001)]
    t1.scan_for_sl_hits(state)
    assert len(state["reentry_permits"]) == 1

    # Simulate restart — build a fresh tracker against the same state.
    t2 = ReentryTracker(cfg)
    minted = t2.scan_for_sl_hits(state)
    assert len(minted) == 0
    assert len(state["reentry_permits"]) == 1


# ---------------------------------------------------------------------------
#                         AVAILABLE PERMIT
# ---------------------------------------------------------------------------
def test_available_permit_respects_cooldown(state_with_buy_direction):
    cfg = _base_cfg()
    cfg["cooldown_minutes"] = 30
    t = ReentryTracker(cfg)
    now = int(time.time())
    state = state_with_buy_direction
    # Mint a permit 10 minutes ago (< cooldown).
    state["recent_results"] = [_make_sl_result(deal_id=6001, ts=now - 600)]
    t.scan_for_sl_hits(state)
    assert t.available_permit("EURUSD", "BUY", now_ts=now, state=state) is None
    # After cooldown passes, permit becomes available.
    assert t.available_permit("EURUSD", "BUY", now_ts=now + 35 * 60, state=state) is not None


def test_available_permit_respects_max_age(state_with_buy_direction):
    cfg = _base_cfg()
    cfg["cooldown_minutes"] = 0
    cfg["max_age_minutes"] = 60
    t = ReentryTracker(cfg)
    now = int(time.time())
    state = state_with_buy_direction
    state["recent_results"] = [_make_sl_result(deal_id=7001, ts=now - 300)]
    t.scan_for_sl_hits(state)
    # Within age window: available.
    assert t.available_permit("EURUSD", "BUY", now_ts=now, state=state) is not None
    # Past expiry: gone.
    assert t.available_permit("EURUSD", "BUY", now_ts=now + 120 * 60, state=state) is None


def test_available_permit_respects_max_reentries(state_with_buy_direction):
    cfg = _base_cfg()
    cfg["max_reentries"] = 1
    cfg["cooldown_minutes"] = 0
    t = ReentryTracker(cfg)
    now = int(time.time())
    state = state_with_buy_direction
    state["recent_results"] = [
        _make_sl_result(deal_id=8001, ts=now - 60),
        _make_sl_result(deal_id=8002, ts=now - 30),
    ]
    t.scan_for_sl_hits(state)

    # First consume uses one.
    p1 = t.available_permit("EURUSD", "BUY", now_ts=now, state=state)
    assert p1 is not None
    t.consume(p1, state=state)
    # Cap is 1 — second attempt (same UTC day) must return None.
    p2 = t.available_permit("EURUSD", "BUY", now_ts=now, state=state)
    assert p2 is None


def test_available_permit_require_same_direction(state_with_buy_direction):
    cfg = _base_cfg()
    cfg["require_same_direction"] = True
    cfg["cooldown_minutes"] = 0
    t = ReentryTracker(cfg)
    now = int(time.time())
    state = state_with_buy_direction  # stamps BUY
    state["recent_results"] = [_make_sl_result(deal_id=9001, ts=now - 60)]
    t.scan_for_sl_hits(state)
    # BUY signal matches — should find permit.
    assert t.available_permit("EURUSD", "BUY", now_ts=now, state=state) is not None
    # SELL signal doesn't match — should return None.
    assert t.available_permit("EURUSD", "SELL", now_ts=now, state=state) is None


def test_available_permit_wrong_symbol(state_with_buy_direction):
    cfg = _base_cfg()
    cfg["cooldown_minutes"] = 0
    t = ReentryTracker(cfg)
    now = int(time.time())
    state = state_with_buy_direction
    state["recent_results"] = [_make_sl_result(deal_id=10001, ts=now - 60)]
    t.scan_for_sl_hits(state)
    assert t.available_permit("GBPUSD", "BUY", now_ts=now, state=state) is None


# ---------------------------------------------------------------------------
#                         CONSUMING PERMITS
# ---------------------------------------------------------------------------
def test_consume_marks_used_and_blocks_reuse(state_with_buy_direction):
    cfg = _base_cfg()
    cfg["cooldown_minutes"] = 0
    cfg["max_reentries"] = 5  # high cap so only `used` blocks the reuse
    t = ReentryTracker(cfg)
    now = int(time.time())
    state = state_with_buy_direction
    state["recent_results"] = [_make_sl_result(deal_id=11001, ts=now - 60)]
    t.scan_for_sl_hits(state)

    p1 = t.available_permit("EURUSD", "BUY", now_ts=now, state=state)
    assert p1 is not None
    t.consume(p1, state=state)
    # Permit is now marked used; re-lookup finds no match.
    p2 = t.available_permit("EURUSD", "BUY", now_ts=now, state=state)
    assert p2 is None
    # State reflects used=True on the stored dict.
    stored = state["reentry_permits"][0]
    assert stored["used"] is True
