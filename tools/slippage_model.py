"""
tools/slippage_model.py — transaction-cost model for offline backtests.

Why this exists
---------------
`reports/BACKTEST_REAL_RESULT.md` states plainly that the current
backtest costs are *modeled*, not observed. There's no spread-at-entry
information stored per trade, so replays use a flat per-symbol cost
estimate. That's the single biggest gap between backtest expectancy
and live P&L on a small account.

This module provides a small, pluggable cost model that:

  * Takes a symbol + side + price + lot size and returns a filled
    price plus itemised cost breakdown (spread_cost + commission +
    slippage).
  * Supports three styles:
      - `flat`           — fixed cost per trade per symbol.
      - `spread_linear`  — cost = spread_pips * lots * pip_value.
      - `sqrt_impact`    — cost = k * sqrt(lots / adv) * pip_value
                            (Almgren-style market impact; for larger
                            accounts).
  * Ships a default profile for the OctaFX-Demo account that matches
    the `max_spread_pips` caps in `config/settings.py::MARKET_PARAMS`.
  * Adds per-symbol commission from a config dict (CFDs typically 0,
    ECN forex can be up to $7/lot round-turn).

Used by
-------
`tools/backtest_real.py` accepts a new `--realistic-costs` flag; when
set, costs come from this module instead of a hard-coded $0.80 per
trade. The previous numbers stay available for apples-to-apples
comparison.

References
----------
- QuantStart: Successful Backtesting Part II —
  https://www.quantstart.com/articles/Successful-Backtesting-of-Algorithmic-Trading-Strategies-Part-II/
- Hudson & Thames: Intro to Transaction Costs notebook.
- Interactive Brokers: Slippage in Model Backtesting whitepaper.
- LuxAlgo: Backtesting Limitations — slippage and liquidity.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger("slippage_model")


# Default broker profile — OctaFX-Demo spreads (pips) and commissions
# (USD per round-turn lot). Derived from `config/settings.py` MARKET_PARAMS
# `max_spread_pips` values; use those as the ceiling and roughly halve
# for a "normal session" median.
DEFAULT_OCTAFX_PROFILE: Dict[str, Dict[str, float]] = {
    "XAUUSD": {"spread_pips_median": 20.0, "spread_pips_p95": 40.0, "commission_per_lot": 0.0},
    "XAGUSD": {"spread_pips_median": 15.0, "spread_pips_p95": 30.0, "commission_per_lot": 0.0},
    "EURUSD": {"spread_pips_median": 0.8, "spread_pips_p95": 2.5, "commission_per_lot": 0.0},
    "GBPUSD": {"spread_pips_median": 1.2, "spread_pips_p95": 3.5, "commission_per_lot": 0.0},
    "USDJPY": {"spread_pips_median": 0.9, "spread_pips_p95": 2.8, "commission_per_lot": 0.0},
    "USDCAD": {"spread_pips_median": 1.5, "spread_pips_p95": 4.0, "commission_per_lot": 0.0},
    "USDCHF": {"spread_pips_median": 1.8, "spread_pips_p95": 4.5, "commission_per_lot": 0.0},
    "AUDUSD": {"spread_pips_median": 1.3, "spread_pips_p95": 3.5, "commission_per_lot": 0.0},
    "NZDUSD": {"spread_pips_median": 1.8, "spread_pips_p95": 4.5, "commission_per_lot": 0.0},
    "EURJPY": {"spread_pips_median": 1.5, "spread_pips_p95": 4.0, "commission_per_lot": 0.0},
    "EURGBP": {"spread_pips_median": 1.5, "spread_pips_p95": 4.5, "commission_per_lot": 0.0},
    "GBPJPY": {"spread_pips_median": 2.8, "spread_pips_p95": 6.5, "commission_per_lot": 0.0},
    "AUDJPY": {"spread_pips_median": 1.8, "spread_pips_p95": 4.5, "commission_per_lot": 0.0},
    "CADJPY": {"spread_pips_median": 2.2, "spread_pips_p95": 5.5, "commission_per_lot": 0.0},
    "BTCUSD": {"spread_pips_median": 40.0, "spread_pips_p95": 100.0, "commission_per_lot": 0.0},
    "ETHUSD": {"spread_pips_median": 30.0, "spread_pips_p95": 80.0, "commission_per_lot": 0.0},
    "XTIUSD": {"spread_pips_median": 25.0, "spread_pips_p95": 60.0, "commission_per_lot": 0.0},
    "XBRUSD": {"spread_pips_median": 25.0, "spread_pips_p95": 60.0, "commission_per_lot": 0.0},
    "XNGUSD": {"spread_pips_median": 35.0, "spread_pips_p95": 70.0, "commission_per_lot": 0.0},
}


# Per-symbol pip size & pip value (account=USD) — used when a broker
# doesn't supply these at the Python level. Close enough for backtests.
_PIP_SIZE = {
    "XAUUSD": 0.1,
    "XAGUSD": 0.01,
    "BTCUSD": 1.0,
    "ETHUSD": 0.1,
    "XTIUSD": 0.01,
    "XBRUSD": 0.01,
    "XNGUSD": 0.001,
}

_DEFAULT_PIP = 0.0001  # forex default (major)
_JPY_PIP = 0.01  # JPY crosses


def _pip_size(symbol: str) -> float:
    if symbol in _PIP_SIZE:
        return _PIP_SIZE[symbol]
    if symbol.endswith("JPY"):
        return _JPY_PIP
    return _DEFAULT_PIP


def _pip_value_usd_per_lot(symbol: str, price: float) -> float:
    """Rough USD per pip per standard lot (100k units). Good enough
    for backtest cost estimates; real execution should read MT5's
    `symbol_info().trade_tick_value`."""
    pip = _pip_size(symbol)
    if symbol.startswith("XAU"):
        return pip * 100.0  # gold: 100 oz/lot
    if symbol.startswith("XAG"):
        return pip * 5000.0  # silver: 5000 oz/lot
    if symbol in ("BTCUSD", "ETHUSD"):
        return pip * 1.0  # crypto: per coin
    if symbol.endswith("JPY"):
        return (pip / price) * 100_000.0 if price > 0 else 9.0  # ~$9.00
    # Major forex:
    return pip * 100_000.0 / (price if price > 0 else 1.0) * (price or 1.0)


@dataclass
class Fill:
    side: str  # "buy" | "sell"
    requested_price: float
    filled_price: float
    lots: float
    spread_cost_usd: float
    commission_usd: float
    slippage_usd: float

    @property
    def total_cost_usd(self) -> float:
        return self.spread_cost_usd + self.commission_usd + self.slippage_usd

    def as_dict(self) -> dict:
        return {
            "side": self.side,
            "requested_price": self.requested_price,
            "filled_price": self.filled_price,
            "lots": self.lots,
            "spread_cost_usd": round(self.spread_cost_usd, 4),
            "commission_usd": round(self.commission_usd, 4),
            "slippage_usd": round(self.slippage_usd, 4),
            "total_cost_usd": round(self.total_cost_usd, 4),
        }


@dataclass
class CostModel:
    profile: Dict[str, Dict[str, float]] = field(default_factory=lambda: dict(DEFAULT_OCTAFX_PROFILE))
    style: str = "spread_linear"  # | "flat" | "sqrt_impact"
    flat_cost_usd: float = 0.80
    slippage_pips: float = 0.5  # constant random-side slip
    # For sqrt_impact — parameterise per symbol if desired.
    impact_k: float = 0.1

    def fill(self, symbol: str, side: str, price: float, lots: float, use_p95_spread: bool = False) -> Fill:
        """Return a Fill with side-aware spread handling.

        side == "buy"  ⇒ we pay the ask  (requested + half-spread)
        side == "sell" ⇒ we hit the bid  (requested - half-spread)
        Slippage is applied against-trade-direction (worst-case).
        """
        side = side.lower()
        sym = self.profile.get(symbol, {})
        if use_p95_spread:
            spread_pips = float(sym.get("spread_pips_p95", 2.0))
        else:
            spread_pips = float(sym.get("spread_pips_median", 2.0))
        commission = float(sym.get("commission_per_lot", 0.0)) * float(lots)
        pip = _pip_size(symbol)
        pip_val = _pip_value_usd_per_lot(symbol, price)

        if self.style == "flat":
            spread_cost = float(self.flat_cost_usd)
            impact = 0.0
        elif self.style == "sqrt_impact":
            spread_cost = spread_pips * pip_val * float(lots)
            impact = self.impact_k * math.sqrt(max(0.0, float(lots))) * pip_val
        else:  # spread_linear default
            spread_cost = spread_pips * pip_val * float(lots)
            impact = 0.0

        # Price = what the trader sees (ask for buy, bid for sell).
        half = (spread_pips / 2.0) * pip
        filled = price + half if side == "buy" else price - half
        # Slippage — always adverse.
        slip_price = self.slippage_pips * pip * (1 if side == "buy" else -1)
        filled += slip_price
        slip_cost = abs(self.slippage_pips) * pip_val * float(lots)

        return Fill(
            side=side,
            requested_price=float(price),
            filled_price=float(filled),
            lots=float(lots),
            spread_cost_usd=float(spread_cost + impact),
            commission_usd=float(commission),
            slippage_usd=float(slip_cost),
        )


__all__ = ["CostModel", "Fill", "DEFAULT_OCTAFX_PROFILE"]
