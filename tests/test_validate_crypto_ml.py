"""Smoke tests for tools/validate_crypto_ml.py.

Verifies the pieces that don't require lightgbm at import time:
  - feature extraction handles both dict-valued 'features' column and
    columnar features
  - load_holdout_baseline flattens nested test_metrics.auc_roc into
    top-level test_auc (registry schema drift caught)
  - verdict() fires on AUC drop, WR drop, and passes within tolerance
  - walk_forward_cv refuses datasets that are too small
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from validate_crypto_ml import (  # noqa: E402
    FEATURE_COLS,
    CVReport,
    extract_xy,
    load_holdout_baseline,
    verdict,
    walk_forward_cv,
)


def test_extract_xy_from_dict_features():
    df = pd.DataFrame(
        [
            {"symbol": "BTCUSD", "is_win": 1, "features": {c: 1 for c in FEATURE_COLS}},
            {"symbol": "BTCUSD", "is_win": 0, "features": {c: 0 for c in FEATURE_COLS}},
        ]
    )
    X, y = extract_xy(df)
    assert list(X.columns) == FEATURE_COLS
    assert len(X) == len(y) == 2
    assert y.tolist() == [1, 0]


def test_extract_xy_from_outcome_column():
    cols = {c: 0 for c in FEATURE_COLS}
    df = pd.DataFrame(
        [
            {"symbol": "BTCUSD", "outcome": "win", **cols},
            {"symbol": "BTCUSD", "outcome": "loss", **cols},
        ]
    )
    X, y = extract_xy(df)
    assert y.tolist() == [1, 0]
    assert list(X.columns) == FEATURE_COLS


def test_load_holdout_baseline_flattens_test_metrics(tmp_path):
    reg = {
        "teams": {
            "CRYPTO": {
                "n_samples": 259,
                "win_rate": 0.992,
                "trained_at": "2026-04-23T07:24:38+00:00",
                "test_metrics": {"accuracy": 0.942, "auc_roc": 0.961},
                "train_metrics": {"accuracy": 0.990, "auc_roc": 0.995},
            }
        }
    }
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(reg))
    flat = load_holdout_baseline("CRYPTO", p)
    assert flat["test_auc"] == pytest.approx(0.961)
    assert flat["test_acc"] == pytest.approx(0.942)
    assert flat["win_rate"] == pytest.approx(0.992)
    assert flat["n_samples"] == 259


def test_load_holdout_baseline_missing_registry(tmp_path):
    result = load_holdout_baseline("CRYPTO", tmp_path / "nope.json")
    assert "error" in result


def test_load_holdout_baseline_missing_team(tmp_path):
    reg = {"teams": {"METALS": {"n_samples": 100}}}
    p = tmp_path / "r.json"
    p.write_text(json.dumps(reg))
    result = load_holdout_baseline("CRYPTO", p)
    assert "error" in result


def test_verdict_triggers_on_auc_drop():
    holdout = {"test_auc": 0.96, "win_rate": 0.99}
    walk = CVReport("walk_forward", 5, mean_auc=0.70, mean_wr=0.85, std_auc=None, std_wr=None, folds=[])
    cpcv = CVReport("cpcv", 10, mean_auc=0.65, mean_wr=0.80, std_auc=None, std_wr=None, folds=[])
    v, reasons = verdict(holdout, walk, cpcv)
    assert v == "OVERFIT - DO NOT DEPLOY"
    assert any("walk-forward AUC" in r for r in reasons)
    assert any("CPCV AUC" in r for r in reasons)


def test_verdict_triggers_on_wr_drop():
    holdout = {"test_auc": 0.70, "win_rate": 0.95}
    walk = CVReport("walk_forward", 5, mean_auc=0.68, mean_wr=0.55, std_auc=None, std_wr=None, folds=[])
    cpcv = CVReport("cpcv", 10, mean_auc=0.66, mean_wr=0.58, std_auc=None, std_wr=None, folds=[])
    v, reasons = verdict(holdout, walk, cpcv)
    assert v == "OVERFIT - DO NOT DEPLOY"
    assert any("WR dropped" in r for r in reasons)


def test_verdict_ok_when_within_tolerance():
    holdout = {"test_auc": 0.75, "win_rate": 0.70}
    walk = CVReport("walk_forward", 5, mean_auc=0.72, mean_wr=0.68, std_auc=None, std_wr=None, folds=[])
    cpcv = CVReport("cpcv", 10, mean_auc=0.70, mean_wr=0.66, std_auc=None, std_wr=None, folds=[])
    v, _ = verdict(holdout, walk, cpcv)
    assert v == "OK"


def test_verdict_inconclusive_without_metrics():
    holdout = {"test_auc": 0.75, "win_rate": 0.70}
    walk = CVReport(
        "walk_forward", 0, mean_auc=None, mean_wr=None, std_auc=None, std_wr=None, folds=[], error="skipped"
    )
    cpcv = CVReport("cpcv", 0, mean_auc=None, mean_wr=None, std_auc=None, std_wr=None, folds=[], error="skipped")
    v, _ = verdict(holdout, walk, cpcv)
    assert v == "INCONCLUSIVE"


def test_walk_forward_cv_refuses_tiny_data():
    # Need at least (5+1)*10 = 60 rows; give 20.
    X = pd.DataFrame({c: [0] * 20 for c in FEATURE_COLS})
    y = pd.Series([0, 1] * 10)
    r = walk_forward_cv(X, y, n_folds=5)
    assert r.error is not None
    assert "samples" in r.error.lower()
