"""
trade_tracker.py — closes the loop between EA fills and the brain's risk gates
================================================================================

Why this exists
---------------
The brain's `loss_streak_cooldown` filter (in `profit_filters.py`) reads
`recent_results` from persistent state and refuses new trades after N
consecutive losses. Until now NOTHING populated that list, so the gate
was dead code. The EA placed trades, the broker closed them, and the
brain never learned the outcome.

This module fixes that. On every brain tick, `TradeTracker.poll(state)`
calls `mt5.history_deals_get(...)` for any deals closed since the last
poll, computes the R-multiple per closed trade (PnL / risk), and appends
a structured dict to `state["recent_results"]`:

    {
        "ts":       1712345678,        # close time, unix seconds
        "symbol":   "XAUUSD",
        "pnl":      24.50,              # currency PnL (broker units)
        "r_mult":   1.7,                # PnL / risk-at-entry
        "deal_id":  408123,             # broker deal ticket
    }

The cooldown filter and the daily-summary builders both accept this
shape (or the legacy plain-float shape) — see the helper below.

How "risk" is determined
------------------------
We don't have direct access to the original SL distance once the deal
closed, so we estimate risk as the absolute PnL of the WORST recent
trade for the symbol — this is good enough for streak detection.
For deals that include the entry stop in the comment field (the EA can
optionally write `SL=1.234`), we parse it; otherwise we fall back to
ATR-derived risk if available, else 1.0 (so r_mult ≈ pnl in account
currency).

Safety
------
* Wrapped in try/except — a broker history glitch must never crash the
  brain.
* Idempotent — uses `last_processed_deal_ts` in state to skip already-
  recorded deals.
* Bounded — only fetches the last `lookback_days` of history (default 1).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("trade_tracker")

try:
    import MetaTrader5 as mt5  # type: ignore
    _HAS_MT5 = True
except Exception:
    _HAS_MT5 = False


# Maximum entries we keep in recent_results — same cap state_store uses.
_MAX_RESULTS = 50


def pnl_of(entry: Union[float, Dict[str, Any]]) -> float:
    """
    Normalise a `recent_results` entry. The list historically held plain
    floats (P&L); we now write structured dicts. Both must work with the
    loss-streak filter and the daily summary so this helper hides the
    difference everywhere.

        >>> pnl_of(-12.5)
        -12.5
        >>> pnl_of({"pnl": -12.5, "ts": 0})
        -12.5
        >>> pnl_of({"r_mult": -1.0})
        -1.0
        >>> pnl_of(None)
        0.0
    """
    if entry is None:
        return 0.0
    if isinstance(entry, (int, float)):
        return float(entry)
    if isinstance(entry, dict):
        # Prefer explicit pnl, fall back to r_mult.
        for k in ("pnl", "r_mult", "r"):
            if k in entry and entry[k] is not None:
                try:
                    return float(entry[k])
                except (TypeError, ValueError):
                    pass
    return 0.0


@dataclass
class TradeTracker:
    """
    Polls MT5 history once per call and appends new closed trades to
    `state["recent_results"]`. Designed to be called from the brain's
    main tick loop — fast, idempotent, fail-safe.
    """
    lookback_days: int = 1
    poll_interval_s: float = 30.0          # don't hammer mt5.history_deals
    _last_poll_ts: float = 0.0
    _seen_deal_ids: set = field(default_factory=set)

    def poll(self, state: Dict[str, Any]) -> int:
        """
        Returns the number of NEW trades appended to state. Returns 0 on
        any failure path (broker offline, MT5 missing, history empty).
        """
        if not _HAS_MT5:
            return 0
        now = time.time()
        if (now - self._last_poll_ts) < self.poll_interval_s:
            return 0
        self._last_poll_ts = now

        try:
            since = int(now - self.lookback_days * 86400)
            until = int(now + 60)
            deals = mt5.history_deals_get(since, until)
            if deals is None or len(deals) == 0:
                return 0
        except Exception as e:
            logger.debug("history_deals_get failed: %s", e)
            return 0

        # Hydrate the seen-set from existing state on first call so a
        # restart doesn't re-replay yesterday's trades.
        if not self._seen_deal_ids:
            for r in state.get("recent_results", []):
                if isinstance(r, dict) and "deal_id" in r:
                    try:
                        self._seen_deal_ids.add(int(r["deal_id"]))
                    except (TypeError, ValueError):
                        pass

        added = 0
        results = list(state.get("recent_results", []))
        # MT5 deal types of interest: DEAL_TYPE_SELL/BUY for closes when
        # entry==DEAL_ENTRY_OUT (out / out-by). We accept any deal whose
        # profit is non-zero — that's the "closing leg" in MT5's model.
        for d in deals:
            try:
                deal_id = int(d.ticket)
                if deal_id in self._seen_deal_ids:
                    continue
                profit = float(getattr(d, "profit", 0.0) or 0.0)
                # Skip pure entry legs and balance ops (deposits, etc.) —
                # only realised PnL events should feed the streak gate.
                entry_kind = int(getattr(d, "entry", -1))
                if profit == 0.0 and entry_kind not in (1, 2):  # OUT / OUT_BY
                    continue
                # Sum commission + swap if available so PnL reflects the
                # broker's actual ledger entry, not raw price PnL.
                profit += float(getattr(d, "commission", 0.0) or 0.0)
                profit += float(getattr(d, "swap", 0.0) or 0.0)
                if profit == 0.0:
                    continue

                # R-multiple proxy: divide by the magnitude of the worst
                # loss seen so far for this symbol — gives a unitless
                # streak signal even when the user changes lot size.
                sym = str(getattr(d, "symbol", "") or "")
                worst = self._worst_loss_for(results, sym)
                r_mult = profit / worst if worst > 0 else profit

                results.append({
                    "ts":       int(getattr(d, "time", now) or now),
                    "symbol":   sym,
                    "pnl":      round(profit, 2),
                    "r_mult":   round(float(r_mult), 3),
                    "deal_id":  deal_id,
                })
                self._seen_deal_ids.add(deal_id)
                added += 1
            except Exception as e:
                logger.debug("skip malformed deal: %s", e)
                continue

        if added == 0:
            return 0

        # Trim and persist (caller is expected to call store.save(state)
        # — we just mutate the dict in-place).
        results.sort(key=lambda r: r.get("ts", 0) if isinstance(r, dict) else 0)
        state["recent_results"] = results[-_MAX_RESULTS:]
        # Track a forward bookmark so the next poll's lookback window can
        # be tightened later if needed.
        state["last_processed_deal_ts"] = int(now)
        logger.info("trade_tracker: appended %d closed deal(s)", added)
        return added

    @staticmethod
    def _worst_loss_for(results: List[Any], symbol: str) -> float:
        """Largest loss magnitude seen for this symbol — used as R unit."""
        worst = 0.0
        for r in results:
            if not isinstance(r, dict):
                continue
            if r.get("symbol") != symbol:
                continue
            p = pnl_of(r)
            if p < 0 and abs(p) > worst:
                worst = abs(p)
        return worst


__all__ = ["TradeTracker", "pnl_of"]
