"""
multi_agent.py — simple, rule-based advanced-agent layer for v14.

Three independent "specialist" agents each look at one timeframe and
return a directional vote:

    +1 = BUY   -1 = SELL   0 = NONE

Agent voting (bus model):

    trend_agent       (H4) : macro / regime
    momentum_agent    (H1) : short-trend follow-through
    timing_agent      (M30): entry trigger

Final direction = sign(sum(votes))   if len({+1 votes}) == N   or  {-1 votes} == N
                  else NONE

i.e. we require **unanimous** agreement across all three agents — that's
the "simple but profitable" setup: few signals, all of them high-conviction.

The heavy ML brain is still optional — this module replaces *nothing* in
the brain, it just gives the brain a second, deterministic, transparent
opinion we can show in logs/dashboard. The EA's existing 3-of-3 local
check is unchanged.

Each agent keeps its rule **simple** so the whole module fits on one
screen and a user can audit exactly why a trade fired.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
import numpy as np
import pandas as pd


# ---------- indicator helpers (small, no TA-Lib dep) ----------
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    rs = g / l.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _macd_hist(s: pd.Series,
               fast: int = 12, slow: int = 26, sig: int = 9) -> pd.Series:
    line = _ema(s, fast) - _ema(s, slow)
    return line - _ema(line, sig)


def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus  = np.where((up > dn) & (up > 0),  up, 0.0)
    minus = np.where((dn > up) & (dn > 0),  dn, 0.0)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=n, adjust=False).mean()
    pdi = 100 * pd.Series(plus,  index=df.index).ewm(span=n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus, index=df.index).ewm(span=n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(span=n, adjust=False).mean()


# ---------- vote result ----------
@dataclass
class AgentVote:
    name: str
    vote: int            # +1 buy, -1 sell, 0 none
    reason: str          # short human-readable why

    def as_dict(self) -> dict:
        return {"name": self.name, "vote": self.vote, "reason": self.reason}


# ---------- agents ----------
def trend_agent_h4(df: pd.DataFrame) -> AgentVote:
    """H4 macro/regime. Requires clean EMA fan + ADX strength."""
    if len(df) < 200:
        return AgentVote("trend_h4", 0, "insufficient H4 bars")
    close = df["close"]
    e20 = _ema(close, 20).iloc[-1]
    e50 = _ema(close, 50).iloc[-1]
    e200 = _ema(close, 200).iloc[-1]
    adx = _adx(df).iloc[-1]
    if not np.isfinite(adx) or adx < 20:
        return AgentVote("trend_h4", 0, f"adx too weak ({adx:.1f})")
    px = close.iloc[-1]
    if e20 > e50 > e200 and px > e20:
        return AgentVote("trend_h4", +1, f"bull fan adx={adx:.1f}")
    if e20 < e50 < e200 and px < e20:
        return AgentVote("trend_h4", -1, f"bear fan adx={adx:.1f}")
    return AgentVote("trend_h4", 0, "no clean fan")


def momentum_agent_h1(df: pd.DataFrame) -> AgentVote:
    """H1 follow-through. MACD histogram trending in direction."""
    if len(df) < 50:
        return AgentVote("momentum_h1", 0, "insufficient H1 bars")
    hist = _macd_hist(df["close"])
    h, hp = hist.iloc[-1], hist.iloc[-2]
    if not np.isfinite(h) or not np.isfinite(hp):
        return AgentVote("momentum_h1", 0, "macd NaN")
    # Rising histogram above 0 -> bull; falling below 0 -> bear
    if h > 0 and h > hp:
        return AgentVote("momentum_h1", +1, f"macd hist rising {h:+.4f}")
    if h < 0 and h < hp:
        return AgentVote("momentum_h1", -1, f"macd hist falling {h:+.4f}")
    return AgentVote("momentum_h1", 0, f"macd hist flat {h:+.4f}")


def timing_agent_m30(df: pd.DataFrame) -> AgentVote:
    """M30 entry trigger. Pullback-respected or breakout with RSI conf."""
    if len(df) < 60:
        return AgentVote("timing_m30", 0, "insufficient M30 bars")
    close = df["close"]
    e20 = _ema(close, 20)
    rsi = _rsi(close, 14)
    px, e = close.iloc[-1], e20.iloc[-1]
    r = rsi.iloc[-1]
    if not np.isfinite(r):
        return AgentVote("timing_m30", 0, "rsi NaN")
    # Bullish: price above M30 EMA20 and RSI between 45-70 (not overbought)
    if px > e and 45 < r < 70:
        return AgentVote("timing_m30", +1, f"px>ema20 rsi={r:.1f}")
    # Bearish: price below M30 EMA20 and RSI between 30-55
    if px < e and 30 < r < 55:
        return AgentVote("timing_m30", -1, f"px<ema20 rsi={r:.1f}")
    return AgentVote("timing_m30", 0, f"no trigger rsi={r:.1f}")


# ---------- bus ----------
def vote_all(frames: Dict[str, pd.DataFrame],
             min_votes: int = 3) -> tuple[int, List[AgentVote]]:
    """
    Run every agent, return (direction, detailed_votes).

    direction: +1 / -1 / 0. Only non-zero if *unanimous* among non-zero votes
    AND at least min_votes agents vote in that direction.
    """
    votes = [
        trend_agent_h4     (frames.get("H4",  pd.DataFrame())),
        momentum_agent_h1  (frames.get("H1",  pd.DataFrame())),
        timing_agent_m30   (frames.get("M30", pd.DataFrame())),
    ]
    buys   = sum(1 for v in votes if v.vote ==  1)
    sells  = sum(1 for v in votes if v.vote == -1)
    if buys  >= min_votes and sells == 0:  return +1, votes
    if sells >= min_votes and buys  == 0:  return -1, votes
    return 0, votes


__all__ = [
    "AgentVote", "trend_agent_h4", "momentum_agent_h1",
    "timing_agent_m30", "vote_all",
]
