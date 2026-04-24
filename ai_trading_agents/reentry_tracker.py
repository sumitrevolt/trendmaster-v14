"""
reentry_tracker.py — Smart re-entry after stop-loss
=====================================================

Why this exists
---------------
A pair that just got stopped out is often the HIGHEST-edge pair in the
next 30 minutes — the original setup might still be structurally intact,
the stop just clipped a wick. The standard behaviour (brain goes
cooldown, waits for the next fresh signal N hours later) throws away
that edge.

This module mints a one-shot "re-entry permit" whenever a recent loss
close to full 1R is observed. The brain, on its next tick, checks for an
available permit matching the symbol+direction. If one exists, base lots
are multiplied by `size_mult` (default 0.7 = 70 % of normal risk) and
the permit is consumed. Caps apply per (symbol, UTC date).

Pure Python — no MT5 imports at module load. Permits are persisted by
the caller in `state["reentry_permits"]` (list of dicts) so they survive
a brain restart.

Config (config.settings.REENTRY):
    enabled                  — master flag
    cooldown_minutes         — minimum gap between SL-hit and re-entry
    size_mult                — lot multiplier for the re-entry (< 1)
    max_reentries            — hard cap per symbol per UTC day
    require_same_direction   — if True, only re-enter on same direction
    max_age_minutes          — permit expires this many minutes after SL
    alert_telegram           — (caller-side) send a Telegram alert on use

Idempotency
-----------
Every permit carries the `deal_id` of the SL-hit trade. `scan_for_sl_hits`
keeps a `_seen_deal_ids` set (hydrated from state on first call) so
scanning twice never mints two permits for the same close.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ai_trading_agents.trade_tracker import pnl_of

logger = logging.getLogger("reentry_tracker")


# Threshold for "SL was hit" — close to a full 1R loss. Wick kisses that
# happen to tag stop and bounce back are normally r_mult ≈ -1.0; we allow a
# little slack so accounting noise (commissions/swap) doesn't hide a real SL.
_SL_R_MULT_THRESHOLD = -0.9


@dataclass
class ReentryPermit:
    """One-shot authorization to re-enter a stopped-out pair at reduced size."""

    symbol: str
    direction: str  # "BUY" or "SELL" (original trade direction)
    original_sl_ts: int  # unix seconds when the SL hit
    expires_ts: int  # original_sl_ts + max_age_minutes * 60
    deal_id: int = 0  # broker ticket of the stopped-out deal
    used: bool = False
    size_mult: float = 0.7

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ReentryPermit":
        return cls(
            symbol=str(d.get("symbol", "")),
            direction=str(d.get("direction", "")),
            original_sl_ts=int(d.get("original_sl_ts", 0) or 0),
            expires_ts=int(d.get("expires_ts", 0) or 0),
            deal_id=int(d.get("deal_id", 0) or 0),
            used=bool(d.get("used", False)),
            size_mult=float(d.get("size_mult", 0.7)),
        )


@dataclass
class ReentryTracker:
    """Minter + matcher for re-entry permits."""

    cfg: Dict[str, Any] = field(default_factory=dict)
    _seen_deal_ids: set = field(default_factory=set)

    # ────────────────────────────────────────────────────────────────
    #                       CONFIG ACCESSORS
    # ────────────────────────────────────────────────────────────────
    def _cooldown_s(self) -> int:
        return int(self.cfg.get("cooldown_minutes", 30)) * 60

    def _max_age_s(self) -> int:
        return int(self.cfg.get("max_age_minutes", 180)) * 60

    def _size_mult(self) -> float:
        return float(self.cfg.get("size_mult", 0.7))

    def _max_reentries(self) -> int:
        return int(self.cfg.get("max_reentries", 1))

    def _require_same_direction(self) -> bool:
        return bool(self.cfg.get("require_same_direction", True))

    # ────────────────────────────────────────────────────────────────
    #                       STATE HYDRATION
    # ────────────────────────────────────────────────────────────────
    def _load_permits(self, state: Dict[str, Any]) -> List[ReentryPermit]:
        raw = state.get("reentry_permits", []) or []
        out: List[ReentryPermit] = []
        for r in raw:
            if isinstance(r, ReentryPermit):
                out.append(r)
                continue
            if not isinstance(r, dict):
                continue
            try:
                out.append(ReentryPermit.from_dict(r))
            except Exception as e:
                logger.debug("skip malformed permit: %s", e)
        return out

    def _save_permits(self, state: Dict[str, Any], permits: List[ReentryPermit]) -> None:
        state["reentry_permits"] = [p.to_dict() for p in permits]

    def _hydrate_seen(self, permits: List[ReentryPermit]) -> None:
        if self._seen_deal_ids:
            return
        for p in permits:
            if p.deal_id:
                self._seen_deal_ids.add(int(p.deal_id))

    # ────────────────────────────────────────────────────────────────
    #                       PERMIT MINTING
    # ────────────────────────────────────────────────────────────────
    def scan_for_sl_hits(self, state: Dict[str, Any]) -> List[ReentryPermit]:
        """
        Scan state['recent_results'] for newly-closed losses that look
        like SL hits (r_mult <= -0.9). Mint one permit per new hit.
        Returns the list of permits newly minted (empty list on no-op).

        Caller is responsible for persisting state after this runs.
        """
        results = list(state.get("recent_results", []))
        permits = self._load_permits(state)
        self._hydrate_seen(permits)

        # Side-channel: the brain writes `state["last_signal_direction"][symbol]`
        # on every non-NONE signal. We read it here to stamp the original
        # direction onto the permit, since trade_tracker doesn't record it.
        last_dir_map: Dict[str, str] = dict(state.get("last_signal_direction", {}) or {})

        newly_minted: List[ReentryPermit] = []
        max_age_s = self._max_age_s()
        size_mult = self._size_mult()

        for r in results:
            if not isinstance(r, dict):
                continue
            deal_id = int(r.get("deal_id", 0) or 0)
            if deal_id <= 0:
                continue
            if deal_id in self._seen_deal_ids:
                continue
            pnl = pnl_of(r)
            if pnl >= 0:
                continue
            # r_mult is the canonical "how close to 1R was the loss" signal.
            try:
                r_mult = float(r.get("r_mult", 0.0) or 0.0)
            except (TypeError, ValueError):
                r_mult = 0.0
            if r_mult > _SL_R_MULT_THRESHOLD:
                # Not a full stop — small scratch loss, skip.
                self._seen_deal_ids.add(deal_id)
                continue

            sym = str(r.get("symbol", "") or "")
            if not sym:
                self._seen_deal_ids.add(deal_id)
                continue

            sl_ts = int(r.get("ts", 0) or 0)
            if sl_ts <= 0:
                sl_ts = int(time.time())
            direction = last_dir_map.get(sym, "")

            permit = ReentryPermit(
                symbol=sym,
                direction=direction,  # may be "" if brain hasn't stamped yet
                original_sl_ts=sl_ts,
                expires_ts=sl_ts + max_age_s,
                deal_id=deal_id,
                used=False,
                size_mult=size_mult,
            )
            permits.append(permit)
            newly_minted.append(permit)
            self._seen_deal_ids.add(deal_id)
            logger.info(
                "reentry: minted permit symbol=%s dir=%s deal_id=%d expires_in=%ds",
                sym,
                direction or "?",
                deal_id,
                max_age_s,
            )

        if newly_minted:
            # Trim: drop long-expired permits so the list doesn't grow forever.
            now = int(time.time())
            cutoff = now - 86400  # one UTC day is plenty of history
            permits = [p for p in permits if p.expires_ts >= cutoff]
            self._save_permits(state, permits)

        return newly_minted

    # ────────────────────────────────────────────────────────────────
    #                    PERMIT DISCOVERY / USE
    # ────────────────────────────────────────────────────────────────
    def _count_used_today(self, permits: List[ReentryPermit], symbol: str, now_ts: int) -> int:
        """How many permits have been consumed for this symbol today (UTC)?"""
        today = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        n = 0
        for p in permits:
            if not p.used or p.symbol != symbol:
                continue
            pd = datetime.fromtimestamp(p.original_sl_ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if pd == today:
                n += 1
        return n

    def available_permit(
        self,
        symbol: str,
        direction: str,
        now_ts: int,
        state: Optional[Dict[str, Any]] = None,
        todays_permits_used: Optional[int] = None,
    ) -> Optional[ReentryPermit]:
        """
        Return a live unexpired permit matching symbol+direction.

        Respects:
          * cooldown      — (now_ts - original_sl_ts) >= cooldown_minutes * 60
          * expiry        — now_ts <= expires_ts
          * not used      — permit.used is False
          * direction     — if require_same_direction, permit.direction == direction
          * per-day cap   — already-used permits for (symbol, UTC-day) < max_reentries

        The caller may pass `state` so we read the durable list, OR pre-pass
        `todays_permits_used` for unit testing without a full state dict.
        """
        if state is None:
            state = {}
        permits = self._load_permits(state)

        cooldown_s = self._cooldown_s()
        require_same = self._require_same_direction()
        max_reentries = self._max_reentries()

        if todays_permits_used is None:
            todays_permits_used = self._count_used_today(permits, symbol, now_ts)

        if todays_permits_used >= max_reentries:
            return None

        for p in permits:
            if p.used:
                continue
            if p.symbol != symbol:
                continue
            if now_ts > p.expires_ts:
                continue
            if (now_ts - p.original_sl_ts) < cooldown_s:
                continue
            if require_same:
                # Direction must match — and if permit has no recorded
                # direction (brain didn't stamp), we can't verify ⇒ skip.
                if not p.direction or p.direction != direction:
                    continue
            return p
        return None

    def consume(self, permit: ReentryPermit, state: Optional[Dict[str, Any]] = None) -> None:
        """
        Mark the permit used so it won't match again. If `state` is given,
        also mutates the persisted list in-place (caller handles save).
        """
        permit.used = True
        if state is None:
            return
        permits = self._load_permits(state)
        for p in permits:
            if p.deal_id == permit.deal_id and p.symbol == permit.symbol:
                p.used = True
        self._save_permits(state, permits)


__all__ = ["ReentryPermit", "ReentryTracker"]
