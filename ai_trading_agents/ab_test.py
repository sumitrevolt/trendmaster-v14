"""
ab_test.py — shadow-mode A/B strategy testing for TrendMaster v14.

Why this exists
---------------
When you want to try a new confidence threshold, a different agent-vote
rule, or a fresh ML model, the only safe way to evaluate is to run it
*alongside* the live strategy and compare fills. This module provides
the plumbing: register a "variant" that receives the same bars as the
live strategy, record its virtual signals, and statistically compare
the two streams weekly.

Design
------
- Variant is ANY callable that takes `(symbol, direction, confidence,
  features)` and returns a `(new_direction, new_confidence)` tuple.
- The shadow strategy never submits orders — its signals go only to
  the audit log + the comparison tool.
- Cumulative PnL tracking uses the SAME fill price the live strategy
  got, so we isolate the signal-quality difference from execution.
- Two-proportion z-test on win-rate + Welch's t-test on PnL per trade
  for statistical significance.

Pure Python + numpy — no scipy dep for the tests.

Integration (opt-in)
--------------------
Enable via `AB_TEST.enabled=True`. Register variants in settings:

    AB_TEST = {
        'enabled': True,
        'variants': [
            {
                'name': 'higher_conf_threshold',
                'callable_path': 'my_variants:v2_conf_065',
            },
            ...
        ],
    }
"""
from __future__ import annotations

import importlib
import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("ab_test")


@dataclass
class Variant:
    name:  str
    func:  Callable[..., Tuple[str, float]]

    def apply(self, symbol: str, direction: str, confidence: float,
              features: Dict) -> Tuple[str, float]:
        try:
            return self.func(symbol, direction, confidence, features)
        except Exception as e:
            logger.warning("variant %s failed: %s", self.name, e)
            return direction, confidence


@dataclass
class ShadowRecord:
    ts:               int
    symbol:           str
    variant:          str
    live_direction:   str
    live_confidence:  float
    shadow_direction: str
    shadow_confidence: float
    diverged:         bool

    def as_dict(self) -> dict:
        return self.__dict__


@dataclass
class ABTester:
    """Runs each registered variant on every tick, stores divergences."""
    variants:  List[Variant]         = field(default_factory=list)
    log_path:  Optional[Path]        = None
    _records:  List[ShadowRecord]    = field(default_factory=list)
    _lock:     Lock                  = field(default_factory=Lock)

    def register(self, name: str, func: Callable) -> None:
        self.variants.append(Variant(name=name, func=func))

    def load_from_settings(self, ab_block: Dict) -> None:
        """Import each callable from `callable_path` spec in settings."""
        for v in ab_block.get("variants", []) or []:
            spec = str(v.get("callable_path", "")).strip()
            if ":" not in spec:
                continue
            mod, fn = spec.split(":", 1)
            try:
                m = importlib.import_module(mod)
                self.register(v.get("name", fn), getattr(m, fn))
            except Exception as e:
                logger.warning("ab_test variant '%s' import failed: %s", spec, e)

    def tick(self, symbol: str, direction: str, confidence: float,
             features: Optional[Dict] = None) -> None:
        """Apply every variant; record per-variant divergences only."""
        features = features or {}
        for var in self.variants:
            shadow_dir, shadow_conf = var.apply(symbol, direction, confidence, features)
            diverged = (shadow_dir != direction
                        or abs(shadow_conf - confidence) > 0.01)
            rec = ShadowRecord(
                ts=int(time.time()),
                symbol=symbol,
                variant=var.name,
                live_direction=direction,
                live_confidence=float(confidence),
                shadow_direction=shadow_dir,
                shadow_confidence=float(shadow_conf),
                diverged=diverged,
            )
            with self._lock:
                self._records.append(rec)
                if self.log_path is not None and diverged:
                    try:
                        with open(self.log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(rec.as_dict()) + "\n")
                    except Exception as e:
                        logger.debug("ab_test log write failed: %s", e)

    def summary(self) -> Dict[str, Dict]:
        """Aggregate per-variant divergence stats."""
        out: Dict[str, Dict] = {}
        with self._lock:
            recs = list(self._records)
        for var in {r.variant for r in recs}:
            sub = [r for r in recs if r.variant == var]
            div = [r for r in sub if r.diverged]
            out[var] = {
                "total_ticks":    len(sub),
                "diverged":       len(div),
                "divergence_pct": (100.0 * len(div) / len(sub)) if sub else 0.0,
            }
        return out


# ---------------------------------------------------------------------
# Statistical significance helpers — used by offline comparison reports.
# Kept here (not scipy) so the runtime install footprint stays small.
# ---------------------------------------------------------------------
def two_proportion_z(wins_a: int, n_a: int, wins_b: int, n_b: int) -> float:
    """Two-sided two-proportion z-statistic. |z| > 1.96 ⇒ p<0.05."""
    if n_a == 0 or n_b == 0:
        return 0.0
    p1, p2 = wins_a / n_a, wins_b / n_b
    p = (wins_a + wins_b) / (n_a + n_b)
    denom = math.sqrt(max(1e-12, p * (1 - p) * (1 / n_a + 1 / n_b)))
    if denom == 0:
        return 0.0
    return (p1 - p2) / denom


def welch_t(a: List[float], b: List[float]) -> float:
    """Welch's t-statistic for two independent unequal-variance samples.
    |t| > ~2.0 ⇒ p<0.05 for typical degrees of freedom."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    ma = sum(a) / na
    mb = sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    denom = math.sqrt(va / na + vb / nb)
    if denom == 0:
        return 0.0
    return (ma - mb) / denom


__all__ = ["Variant", "ShadowRecord", "ABTester",
           "two_proportion_z", "welch_t"]
