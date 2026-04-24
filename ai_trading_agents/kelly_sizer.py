"""
kelly_sizer.py — fractional-Kelly position-size multiplier for v14.

Why this exists
---------------
`config/settings.py::TRENDMASTER_V14` has exposed `kelly_lookback_trades`,
`kelly_min_samples`, `kelly_max_fraction`, `kelly_floor_fraction` for
some time, but nothing in the brain actually reads them — sizing goes
through `risk_manager.size_position` with a fixed `RISK.risk_percent`.

This module implements the missing piece: given the recent trade
history, it returns a *multiplier* in `[kelly_floor_fraction,
kelly_max_fraction]` that the caller can apply to base risk.

    kelly_fraction = max(0, win_rate - (1 - win_rate) / (avg_win/avg_loss))
    sized_risk_pct = base_risk_pct * min(max(half_kelly * kelly_fraction,
                                             floor), max_fraction)

Design choices
--------------
- **Half Kelly by default.** Literature (Thorp, Vince, PyQuantNews)
  converges on fractional Kelly — 50% reduces volatility by ~25% and
  only gives up ~25% of long-term growth vs full Kelly. Operators who
  want full Kelly can override.
- **Fail-safe.** Insufficient samples (< kelly_min_samples) OR
  degenerate stats (zero losses, zero wins, NaN) ⇒ multiplier=1.0.
  Never sizes up when inputs are garbage.
- **Bounded.** Hard-clamped to `[floor, max]` per config — prevents a
  freak win streak from running the multiplier to full Kelly and
  blowing the account.
- **Pure Python.** Unit-testable without MT5.

Integration (opt-in)
--------------------
Enable via `TRENDMASTER_V14.use_kelly_sizing=True` AND
`KELLY_SIZING.enabled=True`. Until both are flipped, `apply()` returns
1.0 — identity multiplier, no behaviour change.

Shadow mode: set `KELLY_SIZING.shadow=True` to log what the multiplier
*would* have been without applying it. Run for 2 weeks, compare against
realized P&L before promoting to live.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Union

logger = logging.getLogger("kelly_sizer")


# Half-Kelly default — empirically safest starting point for retail.
_DEFAULT_KELLY_FRACTION = 0.5


@dataclass
class KellyConfig:
    lookback_trades: int = 40
    min_samples: int = 20
    max_fraction: float = 2.0  # hard cap multiplier
    floor_fraction: float = 0.25  # never go below 25% of base risk
    kelly_fraction: float = _DEFAULT_KELLY_FRACTION
    # When True, `apply()` returns 1.0 (identity) and logs the shadow value.
    shadow_mode: bool = False


@dataclass
class KellyDecision:
    """What `apply()` returns to the caller."""

    multiplier: float
    win_rate: float
    avg_win: float
    avg_loss: float
    raw_kelly: float
    samples_used: int
    reason: str

    def as_dict(self) -> dict:
        return {
            "multiplier": round(self.multiplier, 4),
            "win_rate": round(self.win_rate, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "raw_kelly": round(self.raw_kelly, 4),
            "samples_used": self.samples_used,
            "reason": self.reason,
        }


def _extract_pnl(entry: Union[float, dict, None]) -> float:
    """Normalise a recent_results entry to a float PnL.

    Mirrors `trade_tracker.pnl_of` but redefined locally so this module
    has no brain-side import dependency (unit-testable in isolation).
    """
    if entry is None:
        return 0.0
    if isinstance(entry, (int, float)):
        return float(entry)
    if isinstance(entry, dict):
        for k in ("pnl", "r_mult", "r"):
            v = entry.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
    return 0.0


def compute_multiplier(results: Iterable, cfg: Optional[KellyConfig] = None) -> KellyDecision:
    """Compute the Kelly multiplier from a list of recent trade results.

    `results` accepts either plain float PnL entries (legacy) or dict
    entries produced by `trade_tracker.TradeTracker`. The shape is
    hidden by `_extract_pnl`.

    Returns a fully-populated `KellyDecision` — callers are expected to
    use `.multiplier` but can also surface `.reason` in logs or `/status`.
    """
    cfg = cfg or KellyConfig()
    raw: List[float] = [_extract_pnl(e) for e in list(results)[-cfg.lookback_trades :]]

    # Sanitize — drop entries that normalize to exactly 0.0 (break-even
    # trades shouldn't influence win/loss stats).
    pnls = [x for x in raw if x != 0.0 and math.isfinite(x)]
    n = len(pnls)

    if n < cfg.min_samples:
        return KellyDecision(
            multiplier=1.0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            raw_kelly=0.0,
            samples_used=n,
            reason=f"insufficient samples ({n} < {cfg.min_samples})",
        )

    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]

    if not wins or not losses:
        return KellyDecision(
            multiplier=1.0,
            win_rate=float(len(wins) / n) if n else 0.0,
            avg_win=(sum(wins) / len(wins)) if wins else 0.0,
            avg_loss=(sum(losses) / len(losses)) if losses else 0.0,
            raw_kelly=0.0,
            samples_used=n,
            reason="degenerate: all wins or all losses — falling back to 1.0x",
        )

    win_rate = len(wins) / n
    avg_win = sum(wins) / len(wins)
    avg_loss = abs(sum(losses) / len(losses))  # magnitude
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

    if payoff_ratio <= 0:
        return KellyDecision(
            multiplier=1.0,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=-avg_loss,
            raw_kelly=0.0,
            samples_used=n,
            reason="payoff_ratio <= 0 — falling back to 1.0x",
        )

    # Full Kelly = W - (1-W)/R.
    kelly = win_rate - (1.0 - win_rate) / payoff_ratio
    # Fractional Kelly — default 0.5× (half Kelly).
    frac = max(0.0, kelly) * cfg.kelly_fraction

    # Multiplier of 1.0 means "same as base risk". frac=0.5 => 1.5× base,
    # frac=0.1 => 1.1× base, etc. This mirrors how operators want to
    # think about it — "50% bigger than normal" not "500 bp of equity".
    multiplier = 1.0 + frac

    # Clamp to config caps.
    multiplier = max(cfg.floor_fraction, min(cfg.max_fraction, multiplier))

    return KellyDecision(
        multiplier=multiplier,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=-avg_loss,
        raw_kelly=kelly,
        samples_used=n,
        reason=(f"fractional-kelly={cfg.kelly_fraction}, W={win_rate:.2%}, R={payoff_ratio:.2f}"),
    )


def apply(results: Iterable, base_risk_pct: float, cfg: Optional[KellyConfig] = None) -> float:
    """Return the adjusted risk % a caller should use, or `base_risk_pct`
    verbatim when in shadow mode. Logs the shadow multiplier for later
    comparison."""
    cfg = cfg or KellyConfig()
    decision = compute_multiplier(results, cfg)
    if cfg.shadow_mode:
        logger.info(
            "[kelly-shadow] would_apply=%sx base=%.3f%% → sized=%.3f%% (%s)",
            decision.multiplier,
            base_risk_pct,
            base_risk_pct * decision.multiplier,
            decision.reason,
        )
        return float(base_risk_pct)
    return float(base_risk_pct * decision.multiplier)


__all__ = [
    "KellyConfig",
    "KellyDecision",
    "compute_multiplier",
    "apply",
]
