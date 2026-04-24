"""Unit tests for ai_trading_agents/multi_agent.py."""

from __future__ import annotations

import pandas as pd

from ai_trading_agents.multi_agent import (
    AgentVote,
    trend_agent_h4,
    momentum_agent_h1,
    timing_agent_m30,
    vote_all,
)


def test_agent_vote_serializes():
    v = AgentVote("trend_h4", +1, "bull fan")
    d = v.as_dict()
    assert d == {"name": "trend_h4", "vote": 1, "reason": "bull fan"}


def test_insufficient_bars_yield_zero_vote():
    thin = pd.DataFrame(
        {"open": [1.0] * 10, "high": [1.1] * 10, "low": [0.9] * 10, "close": [1.0] * 10, "volume": [100] * 10}
    )
    assert trend_agent_h4(thin).vote == 0
    assert momentum_agent_h1(thin).vote == 0
    assert timing_agent_m30(thin).vote == 0


def test_bullish_frames_vote_buy_or_abstain(bullish_frames):
    """With a strong uptrend, the bus must never vote SELL."""
    direction, votes = vote_all(bullish_frames, min_votes=2)
    assert direction in (0, +1), f"unexpected sell in uptrend: {votes}"
    # At least one agent should be bullish or zero — never all three bearish.
    assert sum(1 for v in votes if v.vote == -1) < len(votes)


def test_sideways_frames_dont_force_trade(sideways_frames):
    direction, _ = vote_all(sideways_frames, min_votes=3)
    # With no trend + adx weak, unanimous vote is unlikely → expect 0.
    assert direction == 0


def test_vote_all_requires_unanimity():
    """Two bulls + one zero should still return 0 when min_votes=3."""
    import ai_trading_agents.multi_agent as ma

    def _stub_bull(df):
        return ma.AgentVote("stub_bull", +1, "stub")

    def _stub_none(df):
        return ma.AgentVote("stub_none", 0, "stub")

    saved = ma.trend_agent_h4, ma.momentum_agent_h1, ma.timing_agent_m30
    ma.trend_agent_h4 = _stub_bull
    ma.momentum_agent_h1 = _stub_bull
    ma.timing_agent_m30 = _stub_none
    try:
        d, _ = ma.vote_all({"H4": pd.DataFrame(), "H1": pd.DataFrame(), "M30": pd.DataFrame()}, min_votes=3)
        assert d == 0
        d2, _ = ma.vote_all({"H4": pd.DataFrame(), "H1": pd.DataFrame(), "M30": pd.DataFrame()}, min_votes=2)
        assert d2 == +1
    finally:
        ma.trend_agent_h4, ma.momentum_agent_h1, ma.timing_agent_m30 = saved
