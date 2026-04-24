"""Unit tests for the ML feature-alignment helper.

Covers the scenario that caused the 2026-04-24 zero-trades incident: the
retrained `trend_master_model.lgb` expected features in a different
order than the brain's module-level FEATURE_COLS, and because
`Booster.predict(numpy_array)` drops column names, the booster was
silently fed misaligned columns and returned ~0.344 +/- 0.005 across
all 18 markets.

`align_feature_row` is supposed to:
  1. Use the model's `feature_name()` to pick columns from x in the
     order the model was trained with.
  2. Fall back to `fallback_cols` if the model does not expose a
     training-time feature list.
  3. Return (None, used, missing) if any required column is missing
     from x, so the caller can route to a rule-based fallback.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ai_trading_agents.ml_align import align_feature_row, trained_feature_names


# ---------------------------------------------------------------------------
# Mock models: only implement the surface that align_feature_row touches.


class _ModelWithFeatureName:
    def __init__(self, names):
        self._names = list(names)

    def feature_name(self):  # LightGBM Booster API
        return list(self._names)


class _ModelSklearnStyle:
    def __init__(self, names):
        self.feature_names_in_ = list(names)


class _ModelNoNames:
    pass


# ---------------------------------------------------------------------------


def test_trained_feature_names_lgbm():
    m = _ModelWithFeatureName(["a", "b", "c"])
    assert trained_feature_names(m) == ["a", "b", "c"]


def test_trained_feature_names_sklearn_style():
    m = _ModelSklearnStyle(["x", "y"])
    assert trained_feature_names(m) == ["x", "y"]


def test_trained_feature_names_absent_returns_empty():
    assert trained_feature_names(_ModelNoNames()) == []


def test_align_uses_model_order_not_fallback():
    """The core regression: brain's FEATURE_COLS drifts from the model's order.

    If alignment is honoured, the returned row[0] must match
    df[model_order].iloc[-1:].values[0], NOT df[fallback_cols].values[0].
    """
    model = _ModelWithFeatureName(["c", "a", "b"])  # model trained on c,a,b
    fallback = ["a", "b", "c"]  # brain believes a,b,c
    df = pd.DataFrame({"a": [1, 10], "b": [2, 20], "c": [3, 30]})

    row, used, missing = align_feature_row(df, model, fallback)

    assert missing == []
    assert used == ["c", "a", "b"]
    # Last row re-ordered to model's training order:
    np.testing.assert_array_equal(row, np.array([[30, 10, 20]]))


def test_align_falls_back_when_model_has_no_names():
    model = _ModelNoNames()
    fallback = ["a", "b"]
    df = pd.DataFrame({"a": [1, 10], "b": [2, 20]})
    row, used, missing = align_feature_row(df, model, fallback)
    assert missing == []
    assert used == ["a", "b"]
    np.testing.assert_array_equal(row, np.array([[10, 20]]))


def test_align_reports_missing_columns_and_returns_none():
    model = _ModelWithFeatureName(["a", "b", "c"])
    df = pd.DataFrame({"a": [1], "b": [2]})  # no "c"
    row, used, missing = align_feature_row(df, model, ["a", "b", "c"])
    assert row is None
    assert missing == ["c"]
    assert used == ["a", "b", "c"]


def test_align_handles_empty_model_feature_list_and_no_fallback():
    model = _ModelWithFeatureName([])
    df = pd.DataFrame({"a": [1]})
    row, used, missing = align_feature_row(df, model, [])
    assert row is None
    assert used == []
    assert missing == []


def test_align_returns_only_one_row_even_with_multi_row_input():
    """Inference should only ever score the latest bar."""
    model = _ModelWithFeatureName(["a", "b"])
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [10, 20, 30, 40]})
    row, _, _ = align_feature_row(df, model, ["a", "b"])
    assert row is not None
    assert row.shape == (1, 2)
    np.testing.assert_array_equal(row, np.array([[4, 40]]))
