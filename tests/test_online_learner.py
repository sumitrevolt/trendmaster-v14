"""Unit tests for ai_trading_agents.online_learner."""

from __future__ import annotations

import pytest

from ai_trading_agents.online_learner import OnlineLearner


def test_fresh_learner_predicts_midpoint():
    ol = OnlineLearner()
    p = ol.predict_proba({"a": 0.0, "b": 0.0})
    # Untrained ⇒ near 0.5.
    assert 0.3 <= p <= 0.7


def test_learns_simple_pattern():
    ol = OnlineLearner()
    # Train: a>0 ⇒ win, a<0 ⇒ loss. Use many iterations for convergence.
    rng_seed = 7
    import random

    rng = random.Random(rng_seed)
    for _ in range(1500):
        a = rng.uniform(-1, 1)
        ol.learn_one({"a": a, "b": 0.0}, is_win=(a > 0))
    # Now a strongly positive input should give high p_win.
    p_pos = ol.predict_proba({"a": 1.0, "b": 0.0})
    p_neg = ol.predict_proba({"a": -1.0, "b": 0.0})
    assert p_pos > 0.5
    assert p_neg < 0.5
    assert p_pos > p_neg + 0.05


def test_predict_is_win_respects_threshold():
    ol = OnlineLearner()
    # Force near-0.5 proba, threshold 0.9 ⇒ is_win False.
    win, p = ol.predict_is_win({"a": 0.0}, threshold=0.9)
    assert win is False


def test_save_load_roundtrip(tmp_path):
    ol = OnlineLearner(team="METALS")
    for i in range(50):
        ol.learn_one({"f1": float(i), "f2": float(i * 2)}, is_win=(i % 2 == 0))
    path = tmp_path / "ol.pkl"
    ol.save(str(path))
    loaded = OnlineLearner.load(str(path))
    assert loaded.team == "METALS"
    assert loaded._seen == ol._seen
    # Predictions should match.
    p_before = ol.predict_proba({"f1": 10.0, "f2": 20.0})
    p_after = loaded.predict_proba({"f1": 10.0, "f2": 20.0})
    assert abs(p_before - p_after) < 1e-6


def test_load_missing_returns_fresh():
    ol = OnlineLearner.load("/tmp/nonexistent_online_learner.pkl")
    assert ol._seen == 0
    # Still functional.
    assert 0.0 <= ol.predict_proba({"x": 1.0}) <= 1.0
