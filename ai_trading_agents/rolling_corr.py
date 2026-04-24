"""
rolling_corr.py — live rolling-correlation cap for v14 risk manager.

Why this exists
---------------
`risk_manager._CORR_GROUPS` is a hand-authored static set of
correlation groups (USD majors, JPY crosses, metals, oils, crypto).
During regime shifts actual correlations diverge from that prior —
gold and USD can flip signs, oil and CAD can decorrelate, etc. The
static mapping then mis-gates trades on both sides of the error:

  * False-positives: rejects a perfectly uncorrelated pairing
    because they happened to share a group pre-regime-shift.
  * False-negatives: allows a same-direction stack of pairs that
    are currently highly correlated just because the pre-shift
    groupings didn't link them.

This module maintains a 20-bar (configurable) rolling correlation
matrix over all symbols in TRADING_PAIRS and exposes a drop-in
replacement for `_CORR_GROUPS` checks:

    from ai_trading_agents.rolling_corr import RollingCorrMatrix
    rcm = RollingCorrMatrix(window=20)
    rcm.update_bar({"EURUSD": 1.1001, "GBPUSD": 1.2700, ...})
    violation = rcm.check(symbol="EURUSD", direction="BUY",
                          open_positions=positions,
                          threshold=0.8)

Design
------
- Pure Python + numpy. No heavy stats lib required.
- Zero state on construction — the first N bars just warm the window.
- Threshold-based, not group-based — "block if I'd stack 2+ positions
  where pairwise rolling corr > 0.8".
- Negative correlation is also risk — EURUSD LONG + USDCHF SHORT
  (rolling corr near -1 between EURUSD and USDCHF) is effectively two
  longs on EUR. The check treats |corr| > threshold as a conflict.

Opt-in: `RISK.use_rolling_corr=True` in settings (not shipped here —
add it when you want to wire this in).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("rolling_corr")


@dataclass
class CorrViolation:
    other_symbol: str
    correlation: float
    direction: str  # the OTHER side's direction
    reason: str

    def as_dict(self) -> dict:
        return {
            "other_symbol": self.other_symbol,
            "correlation": round(self.correlation, 4),
            "direction": self.direction,
            "reason": self.reason,
        }


@dataclass
class RollingCorrMatrix:
    """Fixed-window rolling correlation matrix across a configurable
    symbol set. One update() call per bar; check() is O(N_open * W)."""

    window: int = 20
    _prices: Dict[str, "deque[float]"] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    # ──────────────────────────────────────────────────────────────────
    def update_bar(self, closes: Dict[str, float]) -> None:
        """Append one close per symbol. Any symbol missing from `closes`
        is skipped — the next bar will pick it up. Deques auto-trim."""
        with self._lock:
            for sym, px in closes.items():
                if px is None:
                    continue
                try:
                    val = float(px)
                except (TypeError, ValueError):
                    continue
                if sym not in self._prices:
                    self._prices[sym] = deque(maxlen=self.window)
                self._prices[sym].append(val)

    # ──────────────────────────────────────────────────────────────────
    def corr(self, sym_a: str, sym_b: str) -> Optional[float]:
        """Rolling correlation between log-returns of two symbols.
        Returns None if either deque is too short or variance is zero."""
        a = list(self._prices.get(sym_a, ()))
        b = list(self._prices.get(sym_b, ()))
        if len(a) < self.window or len(b) < self.window:
            return None
        la = np.diff(np.log(np.clip(np.asarray(a), 1e-12, None)))
        lb = np.diff(np.log(np.clip(np.asarray(b), 1e-12, None)))
        if la.std() == 0 or lb.std() == 0:
            return None
        try:
            c = float(np.corrcoef(la, lb)[0, 1])
            if np.isnan(c) or np.isinf(c):
                return None
            return c
        except Exception:
            return None

    # ──────────────────────────────────────────────────────────────────
    def check(
        self, symbol: str, direction: str, open_positions: Iterable, threshold: float = 0.8
    ) -> Optional[CorrViolation]:
        """Return the first conflict (if any) when trying to open
        `symbol` in `direction` given current `open_positions`.

        `open_positions` is any iterable of objects/dicts with `symbol`
        and `direction` attributes/keys. Absolute-value check: if rolling
        corr > +threshold and same direction → conflict. If rolling corr
        < -threshold and opposite direction → also a conflict (because
        it's effectively a same-side exposure).
        """
        for p in open_positions:
            other_sym = getattr(p, "symbol", None) or (p.get("symbol") if isinstance(p, dict) else None)
            other_dir = getattr(p, "direction", None) or (p.get("direction") if isinstance(p, dict) else None)
            if not other_sym or not other_dir or other_sym == symbol:
                continue
            c = self.corr(symbol, other_sym)
            if c is None:
                continue
            # Same direction + positive corr > threshold ⇒ stacked risk.
            if other_dir == direction and c > float(threshold):
                return CorrViolation(
                    other_symbol=other_sym,
                    correlation=c,
                    direction=other_dir,
                    reason=(
                        f"rolling corr {c:+.2f} with "
                        f"{other_sym} ({other_dir}) > +{threshold:.2f} "
                        f"— same-side stack risk"
                    ),
                )
            # Opposite direction + negative corr < -threshold ⇒
            # structurally same exposure (anti-correlated pair).
            if other_dir != direction and c < -float(threshold):
                return CorrViolation(
                    other_symbol=other_sym,
                    correlation=c,
                    direction=other_dir,
                    reason=(
                        f"rolling corr {c:+.2f} with "
                        f"{other_sym} ({other_dir}) < -{threshold:.2f} "
                        f"— anti-corr masks same exposure"
                    ),
                )
        return None

    # ──────────────────────────────────────────────────────────────────
    def coverage(self) -> Dict[str, int]:
        """How many bars each symbol has accumulated — operator debug."""
        return {s: len(self._prices[s]) for s in sorted(self._prices)}


__all__ = ["CorrViolation", "RollingCorrMatrix"]
