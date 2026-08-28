"""[MERGED 2026-08-25] This module was a drifting duplicate of tools/safeguards.py.

The canonical implementation lives in tools/safeguards.py (17 funcs — superset:
adds brain_agrees_with_signal, brain_explicitly_agrees, equity_tier_check,
correlation_cluster_overexposed, per_symbol_daily_loss_blocked,
time_of_day_blackout). The old 11-func copy here had silently diverged and
caused double-maintenance bugs.

This shim re-exports everything so any legacy
`from ai_trading_agents.safeguards import X` keeps working.
Pre-merge original: backup/duplicate_merge_2026-08-25/safeguards.py
"""
from tools.safeguards import *  # noqa: F401,F403
from tools.safeguards import (  # explicit for clarity
    check_all,
    correlation_overexposed,
    drawdown_breaker_tripped,
    mt5_health_check,
    news_blackout_active,
    spread_too_wide,
)
