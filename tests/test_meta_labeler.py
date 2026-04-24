"""Unit tests for ai_trading_agents.meta_labeler."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from ai_trading_agents.meta_labeler import (
    MetaConfig,
    MetaLabeler,
    MetaPrediction,
)


def test_null_labeler_passes_through():
    lab = MetaLabeler()  # trained=False
    pred = lab.predict({"ema20": 1.0, "rsi": 50.0}, "BUY")
    assert pred.act is True
    assert pred.scale == 1.0
    assert "not trained" in pred.reason


def test_predict_rejects_non_buy_sell():
    lab = MetaLabeler(trained=True)
    # model is None but trained is set — that's an invalid state we still
    # guard against.
    pred = lab.predict({"x": 1.0}, "NONE")
    assert pred.act is False
    assert pred.scale == 0.0
    assert "unexpected primary direction" in pred.reason


def test_train_on_balanced_dataset():
    rng = np.random.default_rng(7)
    n, f = 200, 5
    X = rng.normal(size=(n, f))
    side = rng.choice([-1.0, 1.0], size=n)
    # Make y weakly dependent on one feature — should be learnable.
    y = (X[:, 0] + 0.2 * side > 0).astype(int)
    lab = MetaLabeler.train(
        X,
        y,
        side,
        feature_order=[f"f{i}" for i in range(f)],
    )
    assert lab.trained is True
    assert lab.model is not None
    # Out-of-holdout accuracy should beat random.
    assert lab.metrics["accuracy"] > 0.55


def test_predict_returns_bounded_scale():
    rng = np.random.default_rng(42)
    X = rng.normal(size=(300, 4))
    side = rng.choice([-1.0, 1.0], size=300)
    y = (X[:, 0] > 0).astype(int)
    lab = MetaLabeler.train(X, y, side, feature_order=list("abcd"))
    feats = {"a": 5.0, "b": 0.0, "c": 0.0, "d": 0.0}  # strong positive signal
    pred = lab.predict(feats, "BUY")
    assert 0.0 <= pred.p_win <= 1.0
    # Scale must respect max_scale (default 1.5).
    assert pred.scale <= lab.cfg.max_scale
    assert pred.scale >= 0.0


def test_save_load_roundtrip(tmp_path):
    rng = np.random.default_rng(11)
    X = rng.normal(size=(150, 3))
    side = rng.choice([-1.0, 1.0], size=150)
    y = (X[:, 0] > 0).astype(int)
    lab = MetaLabeler.train(X, y, side, feature_order=list("xyz"))
    path = tmp_path / "meta.pkl"
    lab.save(str(path))
    loaded = MetaLabeler.load(str(path))
    assert loaded.trained is True
    # Prediction must be identical (up to float).
    feats = {"x": 1.5, "y": 0.2, "z": -0.3}
    p1 = lab.predict(feats, "BUY")
    p2 = loaded.predict(feats, "BUY")
    assert p1.p_win == pytest.approx(p2.p_win, abs=1e-6)


def test_load_missing_file_returns_null():
    lab = MetaLabeler.load("/tmp/does_not_exist_for_sure.pkl")
    assert lab.trained is False
    assert lab.model is None


def test_threshold_gates_acting():
    # Force a threshold that will fail — p_win should be < 0.9.
    cfg = MetaConfig(p_win_threshold=0.9, feature_order=list("abc"))
    rng = np.random.default_rng(2)
    X = rng.normal(size=(100, 3))
    side = rng.choice([-1.0, 1.0], size=100)
    y = (rng.random(100) < 0.5).astype(int)  # essentially random labels
    lab = MetaLabeler.train(X, y, side, feature_order=list("abc"), cfg=cfg)
    # With random labels the learned p_win is near 0.5 — threshold=0.9 ⇒ act=False.
    pred = lab.predict({"a": 0.0, "b": 0.0, "c": 0.0}, "BUY")
    assert pred.act is False
    assert pred.scale == 0.0


def test_cpcv_integration_produces_oof_metrics():
    # Run train() with the CPCV splitter from tools/cpcv.py.
    from tools.cpcv import CPCVSplit

    rng = np.random.default_rng(3)
    X = rng.normal(size=(200, 4))
    side = rng.choice([-1.0, 1.0], size=200)
    y = (X[:, 0] + 0.3 * side > 0).astype(int)
    cv = CPCVSplit(n_groups=5, n_test=1, embargo_bars=2)
    lab = MetaLabeler.train(X, y, side, feature_order=list("abcd"), cv_splitter=cv)
    # AUC should be computable on the pooled OOF predictions.
    assert "auc_roc" in lab.metrics
    # Better than random-ish.
    if not np.isnan(lab.metrics["auc_roc"]):
        assert lab.metrics["auc_roc"] > 0.5
