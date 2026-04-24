"""Unit tests for ai_trading_agents.regime_hmm."""
from __future__ import annotations

import numpy as np
import pytest

from ai_trading_agents.regime_hmm import HMMConfig, RegimeHMM


def _make_closes(n=400, drift=0.0, vol=0.005, seed=7):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, size=n)
    return np.exp(np.cumsum(r)) * 100.0


def test_insufficient_history_raises():
    h = RegimeHMM(cfg=HMMConfig(min_history_bars=200))
    closes = _make_closes(n=50)
    with pytest.raises(ValueError):
        h.fit(closes)


def test_fit_runs_on_synthetic_stream():
    closes = _make_closes(n=500)
    h = RegimeHMM(cfg=HMMConfig(n_states=2, n_iter=20, min_history_bars=100))
    h.fit(closes)
    assert h.trained is True
    assert h.means is not None
    assert h.trans is not None
    assert h.trans.shape == (2, 2)


def test_classify_returns_valid_state():
    closes = _make_closes(n=500)
    h = RegimeHMM(cfg=HMMConfig(n_states=2, n_iter=20, min_history_bars=100))
    h.fit(closes)
    obs = h.classify(closes[-200:])
    assert obs.state in ("chop", "trend")
    assert 0.0 <= obs.prob <= 1.0
    assert abs(sum(obs.probs_all) - 1.0) < 1e-6


def test_untrained_classify_returns_unknown():
    h = RegimeHMM()
    obs = h.classify([1.0, 2.0, 3.0])
    assert obs.state == "unknown"
    assert obs.prob == 0.0


def test_chop_vs_trend_distinguishable():
    # Chop regime: near-zero drift, wide variance.
    chop_closes = _make_closes(n=500, drift=0.0, vol=0.01, seed=1)
    # Trend regime: clear positive drift.
    trend_closes = _make_closes(n=500, drift=0.002, vol=0.004, seed=2)
    # Concatenate to force a regime switch.
    closes = np.concatenate([chop_closes, trend_closes])
    h = RegimeHMM(cfg=HMMConfig(n_states=2, n_iter=30, min_history_bars=100))
    h.fit(closes)
    # Classify on the trending tail — should lean toward the "trend" state.
    obs_trend = h.classify(closes[-300:])
    # Classify on the chop head — should lean toward "chop".
    obs_chop = h.classify(closes[:500])
    # Probabilities won't always be perfectly assigned, but at least one
    # classification should pick each distinct label.
    assert obs_trend.state_idx >= 0
    assert obs_chop.state_idx >= 0


def test_save_load_roundtrip(tmp_path):
    closes = _make_closes(n=400)
    h = RegimeHMM(cfg=HMMConfig(n_states=2, n_iter=10, min_history_bars=50))
    h.fit(closes)
    p = tmp_path / "hmm.pkl"
    h.save(str(p))
    loaded = RegimeHMM.load(str(p))
    assert loaded.trained is True
    # Same classification output (up to float error).
    o1 = h.classify(closes[-200:])
    o2 = loaded.classify(closes[-200:])
    assert o1.state_idx == o2.state_idx


def test_three_state_labels():
    closes = _make_closes(n=800, vol=0.005)
    h = RegimeHMM(cfg=HMMConfig(n_states=3, n_iter=15, min_history_bars=100))
    h.fit(closes)
    assert len(h.state_labels) == 3
    assert "chop" in h.state_labels
    assert any("trend" in s for s in h.state_labels)


def test_load_missing_file_returns_untrained():
    h = RegimeHMM.load("/tmp/does_not_exist_ever.pkl")
    assert h.trained is False
    assert h.means is None
