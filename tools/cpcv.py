"""
tools/cpcv.py — Combinatorial Purged Cross-Validation splitter.

Reference
---------
Marcos López de Prado, *Advances in Financial Machine Learning*, ch. 7
(2018). Summary: https://en.wikipedia.org/wiki/Purged_cross-validation

Why this exists
---------------
`tools/train_per_team.py` currently uses an 80/20 train-test split on
trade-level feature rows. That's fine for a static dataset but *leaks*
information in a time-series setting: labels for trade_t can depend on
price movements that also feed features for trade_t+k, so testing on
t+k while training on t gives an optimistically biased estimate.

CPCV fixes this by:

  1. Splitting the N observations into K contiguous groups.
  2. Choosing every combination of K_test groups as the test set
     (rather than one-leave-out or fixed split).
  3. PURGING: removing training samples whose label-windows overlap the
     test window.
  4. EMBARGOING: dropping the next M samples after each test group
     from the training set (to prevent serial-correlation leakage
     across the boundary).

Output is a list of (train_idx, test_idx) tuples usable anywhere sklearn
expects a CV iterator.

Usage
-----
    from tools.cpcv import CPCVSplit
    cv = CPCVSplit(n_groups=6, n_test=2,
                   label_times=timestamps, label_horizon_bars=10,
                   embargo_bars=5)
    for train_idx, test_idx in cv.split(X, y):
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        yhat = model.predict(X.iloc[test_idx])
        ...

Pure Python + numpy. No sklearn requirement — we manually check shapes.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger("cpcv")


@dataclass
class CPCVSplit:
    """Combinatorial Purged CV with embargo.

    Parameters
    ----------
    n_groups : int
        K in the paper. Total number of contiguous time-ordered groups.
        Typical: 6–10 for financial data.
    n_test : int
        How many groups per test fold. Typical: 2 (so the train/test
        ratio is (K - n_test) / n_test).
    label_times : Optional[Sequence]
        Per-row label window end times (monotone). Used for purging —
        a training row whose label extends into the test window is
        removed. If None, purging is disabled.
    label_horizon_bars : int
        How many bars forward each label is computed over. Applied
        when `label_times` is None — we fall back to "drop the last N
        rows of each training fold that sit within the test fold's
        horizon".
    embargo_bars : int
        Bars to drop after each test group — prevents leakage via
        autocorrelation across the boundary. 0 to disable.
    """

    n_groups: int = 6
    n_test: int = 2
    label_times: Optional[Sequence] = None
    label_horizon_bars: int = 0
    embargo_bars: int = 0

    def __post_init__(self):
        if self.n_groups < 2:
            raise ValueError("n_groups must be >= 2")
        if self.n_test < 1 or self.n_test >= self.n_groups:
            raise ValueError("1 <= n_test < n_groups required")

    # ──────────────────────────────────────────────────────────────────
    def _group_indices(self, n: int) -> List[np.ndarray]:
        """Partition 0..n-1 into n_groups contiguous chunks."""
        edges = np.linspace(0, n, self.n_groups + 1, dtype=int)
        return [np.arange(edges[i], edges[i + 1]) for i in range(self.n_groups)]

    def _apply_embargo(self, train: np.ndarray, test: np.ndarray, n_total: int) -> np.ndarray:
        if self.embargo_bars <= 0:
            return train
        to_drop = set()
        for t in test:
            for k in range(1, self.embargo_bars + 1):
                if t + k < n_total:
                    to_drop.add(int(t + k))
        if not to_drop:
            return train
        return np.array([x for x in train if x not in to_drop], dtype=int)

    def _apply_purge(self, train: np.ndarray, test: np.ndarray) -> np.ndarray:
        """Purge training rows whose label horizon overlaps the test window."""
        if self.label_times is not None:
            try:
                lt = np.asarray(self.label_times)
            except Exception:
                return train
            if len(lt) == 0 or len(test) == 0:
                return train
            test_start = float(lt[test[0]])
            test_end = float(lt[test[-1]])
            # Keep training rows whose label window ends BEFORE test_start
            # or starts AFTER test_end.
            return np.array([i for i in train if float(lt[i]) < test_start or float(lt[i]) > test_end], dtype=int)

        # Fallback: drop the last `label_horizon_bars` rows of any
        # training fold that sits immediately before the test window.
        if self.label_horizon_bars <= 0 or len(test) == 0:
            return train
        first_test = int(test[0])
        cutoff = first_test - self.label_horizon_bars
        return np.array([i for i in train if i < cutoff or i >= int(test[-1])], dtype=int)

    # ──────────────────────────────────────────────────────────────────
    def split(self, X, y=None) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        """Yield (train_idx, test_idx) numpy arrays.

        `X` is any sequence/ndarray/DataFrame we can take `len()` of.
        `y` is unused — kept for sklearn-iterator compatibility.
        """
        n = len(X)
        groups = self._group_indices(n)
        test_combos = list(itertools.combinations(range(self.n_groups), self.n_test))
        if not test_combos:
            return
        for combo in test_combos:
            test_idx = np.concatenate([groups[g] for g in combo])
            test_idx.sort()
            train_groups = [g for g in range(self.n_groups) if g not in combo]
            if not train_groups:
                continue
            train_idx = np.concatenate([groups[g] for g in train_groups])
            train_idx.sort()
            train_idx = self._apply_purge(train_idx, test_idx)
            train_idx = self._apply_embargo(train_idx, test_idx, n)
            if len(train_idx) == 0 or len(test_idx) == 0:
                logger.debug("cpcv: empty fold skipped (combo=%s)", combo)
                continue
            yield train_idx, test_idx

    def get_n_splits(self, X=None, y=None, groups=None) -> int:
        # sklearn-compat hook.
        from math import comb

        return comb(self.n_groups, self.n_test)


def purged_walk_forward(n: int, n_splits: int = 5, embargo: int = 10) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
    """Simpler alternative — anchored walk-forward with embargo gap.

    For datasets too small for CPCV, a plain rolling train/test split
    with an embargo gap between them still outperforms a vanilla 80/20
    split. Cheap and cheerful.
    """
    if n_splits < 1:
        return
    fold = n // (n_splits + 1)
    if fold <= 1:
        return
    for k in range(1, n_splits + 1):
        train_end = k * fold
        test_start = min(n - 1, train_end + embargo)
        test_end = min(n, (k + 1) * fold + embargo)
        if test_end - test_start < 2:
            continue
        train_idx = np.arange(0, train_end)
        test_idx = np.arange(test_start, test_end)
        yield train_idx, test_idx


__all__ = ["CPCVSplit", "purged_walk_forward"]
