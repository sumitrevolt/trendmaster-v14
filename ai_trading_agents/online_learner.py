"""
online_learner.py — incremental ML adapter for TrendMaster v14.

Why this exists
---------------
The batch-retraining pipeline (`tools/train_per_team.py`) is the right
default — stable models, honest CPCV evaluation, easy rollback. But
markets drift, and a batch retrain run once a week lags reality. An
online classifier updates on every closed trade, catching drift in
minutes instead of days.

This module is an adapter. If `river` (the canonical Python
online-learning lib, 2019+) is installed we use its `LogisticRegression`
/ `HoeffdingTreeClassifier`; otherwise we fall back to a hand-rolled
incremental logistic regression (SGD). No hard dependency.

Reference: online-ml/river (GitHub), scikit-multiflow's HoeffdingTree,
"River: Machine Learning for Streaming Data in Python" (2020).

Integration (opt-in)
--------------------
Enable via `ONLINE_LEARNER.enabled=True`. When a closed deal lands in
`trade_tracker`, the brain also calls `online_learner.learn_one(feat,
is_win)`. Predictions (used as a secondary "freshness" score alongside
the batch LGBM) are gated behind `ONLINE_LEARNER.predict_active=True`.
"""
from __future__ import annotations

import logging
import math
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("online_learner")

try:
    from river import linear_model as _river_lm  # type: ignore
    from river import preprocessing as _river_pp  # type: ignore
    from river import compose as _river_compose  # type: ignore
    from river import metrics as _river_metrics  # type: ignore
    _HAS_RIVER = True
except Exception:
    _HAS_RIVER = False


# ======================================================================
# Manual fallback — stateful SGD logistic regression
# ======================================================================
@dataclass
class _ManualSGDLogReg:
    """One-pass stochastic gradient logistic regression with L2."""
    lr:           float = 0.05
    l2:           float = 1e-4
    _weights:     Dict[str, float] = field(default_factory=dict)
    _bias:        float = 0.0
    _seen:        int   = 0

    def _z(self, x: Dict[str, float]) -> float:
        return self._bias + sum(self._weights.get(k, 0.0) * v for k, v in x.items())

    def predict_proba(self, x: Dict[str, float]) -> float:
        z = self._z(x)
        if z >= 0:
            ez = math.exp(-z)
            return 1.0 / (1.0 + ez)
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def learn_one(self, x: Dict[str, float], y: int) -> None:
        p = self.predict_proba(x)
        err = p - float(y)
        for k, v in x.items():
            w = self._weights.get(k, 0.0)
            grad = err * v + self.l2 * w
            self._weights[k] = w - self.lr * grad
        self._bias -= self.lr * err
        self._seen += 1


# ======================================================================
# Wrapper — river-first, falls back to manual
# ======================================================================
@dataclass
class OnlineLearner:
    team:        str   = "DEFAULT"
    model:       Any   = None
    _lock:       Lock  = field(default_factory=Lock)
    _seen:       int   = 0
    _backend:    str   = ""

    def __post_init__(self):
        if self.model is None:
            if _HAS_RIVER:
                try:
                    self.model = _river_compose.Pipeline(
                        _river_pp.StandardScaler(),
                        _river_lm.LogisticRegression(),
                    )
                    self._backend = "river.LogisticRegression"
                except Exception:
                    self.model = _ManualSGDLogReg()
                    self._backend = "fallback.SGDLogReg"
            else:
                self.model = _ManualSGDLogReg()
                self._backend = "fallback.SGDLogReg"

    # --- Training ---
    def learn_one(self, features: Dict[str, float], is_win: bool) -> None:
        y = int(bool(is_win))
        with self._lock:
            try:
                self.model.learn_one(features, y)
                self._seen += 1
            except Exception as e:
                logger.debug("learn_one failed for %s: %s", self.team, e)

    # --- Inference ---
    def predict_proba(self, features: Dict[str, float]) -> float:
        with self._lock:
            try:
                return float(self.model.predict_proba_one(features)[1]
                             if hasattr(self.model, "predict_proba_one")
                             else self.model.predict_proba(features))
            except Exception as e:
                logger.debug("predict failed for %s: %s", self.team, e)
                return 0.5

    def predict_is_win(self, features: Dict[str, float],
                       threshold: float = 0.55) -> Tuple[bool, float]:
        p = self.predict_proba(features)
        return p >= threshold, p

    # --- Persistence ---
    def save(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            pickle.dump({
                "team":     self.team,
                "backend":  self._backend,
                "seen":     self._seen,
                "model":    self.model,
            }, f)

    @classmethod
    def load(cls, path: str) -> "OnlineLearner":
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            with open(p, "rb") as f:
                blob = pickle.load(f)
            ol = cls(team=blob.get("team", "DEFAULT"), model=blob.get("model"))
            ol._backend = str(blob.get("backend", ""))
            ol._seen = int(blob.get("seen", 0) or 0)
            return ol
        except Exception as e:
            logger.warning("online_learner load failed (%s) — returning fresh", e)
            return cls()


__all__ = ["OnlineLearner"]
