"""Sample-weight utilities for TrendMaster v14 trainers.

Implements López de Prado AFML Chapter 4 average-uniqueness weighting
for sequential triple-barrier labels. Used by:

  tools/train_v14_b3.py          (3-class primary model)
  tools/train_v14_c1_metalabel.py  (binary act/skip global)
  tools/train_v14_c2_metalabel_perteam.py  (binary act/skip per-team)

Why bother?
-----------
Triple-barrier labels have hold_bars=12. Consecutive label windows
overlap by 11/12 bars — they are NOT i.i.d. LightGBM's stock bagging
treats every sample as independent, so it memorises the co-dependent
structure and produces overfit OOF metrics.

Average uniqueness (avg_uniq[i]) = mean(1/c[t] for t in label window i)
where c[t] = number of concurrent label windows that include bar t.

Interpretation
  avg_uniq = 1.0   → label window is entirely non-overlapping (edges)
  avg_uniq ≈ 1/12  → label window overlaps maximally (interior, hold=12)

Using avg_uniq as sample_weight in lgb.Dataset tells LightGBM to focus
gradient updates on the "freshest" information (high-uniqueness samples)
rather than the repeated signal in overlapping windows. Combined with
balanced class weights this replaces bagging_fraction as the
de-duplication mechanism, yielding more honest OOF estimates.

Reference
  López de Prado, M. (2018). Advances in Financial Machine Learning.
  Wiley. Chapter 4 — Sample Weights.
"""

from __future__ import annotations

import numpy as np


def avg_uniqueness(n: int, hold_bars: int) -> np.ndarray:
    """Average uniqueness for n sequential labels with integer-indexed windows.

    Label i's window spans bars [i, i + hold_bars - 1] (inclusive).
    c[t] = number of labels whose windows include bar t.
    avg_uniqueness[i] = mean(1 / c[t]  for t in [i, i + hold_bars - 1])

    Implementation uses a difference-array cumsum trick for O(n) runtime.

    Parameters
    ----------
    n         : number of labels (samples)
    hold_bars : label horizon in bars (e.g. 12 for HOLD_BARS=12)

    Returns
    -------
    np.ndarray of shape (n,), dtype float64, values in (0, 1].
    Edge samples near position 0 and n-1 have higher uniqueness because
    their windows have fewer concurrent neighbours.

    Examples
    --------
    >>> w = avg_uniqueness(100, 12)
    >>> w.shape
    (100,)
    >>> w.min(), w.max()      # interior ≈ 1/12, edges ≈ 1.0
    (0.083..., 1.0)
    """
    if n <= 0 or hold_bars <= 0:
        return np.ones(max(n, 0), dtype=np.float64)

    # Build concurrency array c[t] for t in [0, n + hold_bars - 1].
    # Label i contributes +1 to bars [i, i + hold_bars - 1].
    # Use difference array: diff[i] += 1, diff[i + hold_bars] -= 1, then cumsum.
    total = n + hold_bars
    diff = np.zeros(total + 1, dtype=np.float64)
    indices = np.arange(n, dtype=np.int64)
    np.add.at(diff, indices, 1.0)
    np.add.at(diff, indices + hold_bars, -1.0)
    c = np.cumsum(diff)[:total]  # c[t] = concurrent label count at bar t

    # Avoid division by zero (shouldn't happen for valid inputs, but guard)
    c_safe = np.where(c > 0, c, 1.0)

    # Cumulative sum of 1/c for fast window-mean queries.
    # avg_uniq[i] = (sum of 1/c[t] for t in [i, i+hold_bars-1]) / hold_bars
    inv_c = 1.0 / c_safe
    cum_inv = np.empty(total + 1, dtype=np.float64)
    cum_inv[0] = 0.0
    np.cumsum(inv_c, out=cum_inv[1:])

    # Window sums: cum_inv[i + hold_bars] - cum_inv[i]
    window_sums = cum_inv[hold_bars : n + hold_bars] - cum_inv[:n]
    uniq = window_sums / hold_bars

    # Clip to [epsilon, 1.0] for numerical safety
    return np.clip(uniq, 1e-6, 1.0)


def uniqueness_weights(
    n: int,
    hold_bars: int,
    y: np.ndarray,
    *,
    n_classes: int = 2,
) -> np.ndarray:
    """Combined sample weights: avg_uniqueness × balanced class weight.

    Produces the final ``weight`` array to pass to ``lgb.Dataset``.

    Parameters
    ----------
    n         : number of samples in this symbol's sequence
    hold_bars : label horizon (must match training config)
    y         : integer label array, shape (n,)
                  binary:     0 / 1
                  multiclass: 0 / 1 / 2  (SELL / NONE / BUY encoded)
    n_classes : number of classes (2 for C1/C2, 3 for B3)

    Returns
    -------
    np.ndarray of shape (n,), dtype float64.
    Weights are in (0, ∞) and are NOT normalised to sum to 1 —
    LightGBM uses them as relative importance, not probabilities.
    """
    uniq = avg_uniqueness(n, hold_bars)

    # Balanced class weights: w_c = n / (n_classes * count_c)
    y_arr = np.asarray(y, dtype=int)
    class_w = np.ones(n, dtype=np.float64)
    for cls in np.unique(y_arr):
        count = int((y_arr == cls).sum())
        if count > 0:
            class_w[y_arr == cls] = len(y_arr) / (n_classes * count)

    return uniq * class_w
