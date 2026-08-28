"""Quick scalping mode verification."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from config import settings

print("=" * 60)
print("  SCALPING MODE VERIFICATION")
print("=" * 60)

pairs = settings.TRADING_PAIRS
print(f"\n  Pairs ({len(pairs)}): {', '.join(pairs)}")

scoring = settings.CONFLUENCE_SCORING
print(f"  min_score:       {scoring['min_score']}")
print(f"  chop_adx:        {scoring['veto_chop_adx_threshold']}")
print(f"  scoring_enabled: {scoring['enabled']}")

po = settings.PROFIT_OPTIMIZER
print(f"  vol_regime:      {po['vol_regime']}")
print(f"  session_window:  {po['session_window']}")
print(f"  news_blackout:   {po['news_blackout']}")
print(f"  profit_lock:     {po['profit_lock']}")
print(f"  loss_cooldown:   {po['loss_cooldown']}")
print(f"  best_hours:      {len(po['best_hours_utc'])}h ({po['best_hours_utc'][0]}-{po['best_hours_utc'][-1]} UTC)")

tm = settings.TRENDMASTER_V14
print(f"  inference_ms:    {tm['inference_interval_ms']}")
print(f"  multi_symbol:    {tm['multi_symbol']}")
print(f"  min_conf:        {tm['min_ml_confidence']}")
print(f"  agent_min_votes: {tm['agent_min_votes']}")

# Test timeframe overrides
from config.settings import timeframes_for
for p in pairs:
    tf = timeframes_for(p)
    print(f"  {p:8s} -> {tf}")

print(f"\n  Risk %: {settings.RISK['risk_percent']}")

# Test scoring
import numpy as np
import pandas as pd
np.random.seed(42)
n = 250
close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0005)
df = pd.DataFrame({
    'open': close - np.random.rand(n) * 0.0003,
    'high': close + np.random.rand(n) * 0.0005,
    'low': close - np.random.rand(n) * 0.0005,
    'close': close,
    'volume': np.random.randint(100, 1000, n).astype(float),
})

from ai_trading_agents.scoring import compute_confluence_score
for d in ["BUY", "SELL"]:
    r = compute_confluence_score(df, d, hour_utc=14, min_score=3.0)
    print(f"  Synthetic {d}: score={r.score:.1f} direction={r.direction} detail={r.detail}")

print("\n  ALL OK - Scalping mode ready!")
