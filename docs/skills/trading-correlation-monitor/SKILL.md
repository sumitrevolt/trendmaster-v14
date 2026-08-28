---
name: trading-correlation-monitor
description: Daily pairwise correlation matrix across TrendMaster v14's 19 symbols, with regime-shift detection. Flags when known-stable pairs decouple (XAUUSD–DXY) or known-uncorrelated pairs suddenly correlate (BTCUSD–NASDAQ flip), which is a leading signal for cluster-risk concentration. Use when the user asks "correlation matrix", "are my positions actually diversified", "regime shift", "BTC-NASDAQ correlation", "XAU-DXY decoupling", or before increasing per-team max-open.
---

# Trading Correlation Monitor

The portfolio module already enforces per-cluster trade caps. This skill detects when the *clusters themselves* shift — which is when those caps stop protecting you.

## When to invoke

- Daily morning routine.
- Before any change to per-team max-open or per-symbol cap.
- After any unexplained joint drawdown across two or more "uncorrelated" pairs.
- Weekly trend review.

## What it computes

For each ordered pair (i, j) of the 19 symbols:

1. **30-day rolling Pearson correlation** of H1 returns (`close.pct_change()`).
2. **Baseline correlation** = trailing 180-day rolling mean.
3. **Regime shift score** = `|corr_30d − baseline| / std(baseline_window)`.

Pairs with regime shift score > 2.0 are flagged. Known relationships have explicit baselines so the skill knows what "decoupling" means:

| Pair | Expected baseline | Drift threshold |
|---|---|---|
| XAUUSD ↔ DXY | -0.65 | flag if abs > -0.35 |
| BTCUSD ↔ ETHUSD | +0.85 | flag if < 0.55 |
| BTCUSD ↔ NASDAQ proxy | +0.45 | flag if cross 0 |
| EURUSD ↔ GBPUSD | +0.70 | flag if < 0.40 |
| AUDUSD ↔ NZDUSD | +0.85 | flag if < 0.60 |
| USDJPY ↔ US10Y yield | +0.60 | flag if < 0.30 |

These thresholds reflect 2024-2026 cross-asset literature, not opinion.

## Output

```
Correlation Monitor — 2026-04-25 09:14 local
============================================

Per-team mean intra-team correlation (last 30 days vs 180-day baseline):
  METALS:    0.74 vs 0.78    (-0.04)   normal
  FOREX:     0.41 vs 0.46    (-0.05)   normal
  CRYPTO:    0.62 vs 0.81    (-0.19)   <-- WEAKENED — alts are decoupling from BTC
  COMMOD:    0.51 vs 0.49    (+0.02)   normal

Known-relationship checks:
  XAU/DXY:        -0.74 vs -0.65 baseline   normal (slightly more anti-correlated)
  BTC/ETH:         0.42 vs 0.85 baseline   <-- DECOUPLED  (regime shift)
  EUR/GBP:         0.66 vs 0.70 baseline    normal
  AUD/NZD:         0.78 vs 0.85 baseline    normal
  USDJPY/US10Y:    0.58 vs 0.60 baseline    normal

Regime shift events (z-score > 2):
  BTC ↔ ETH:    z=4.2   30d=0.42   baseline=0.85
    Implication: a BTC/ETH long pair is no longer naturally hedged.
                 Per-team max-open=2 now means real 2x exposure, not net 0.5x.

  XRP ↔ ETH:    z=2.4   30d=0.28   baseline=0.62
    Implication: alt ecosystem fragmentation continues.

Cluster recommendation (k-means on absolute corr, k=4):
  Old clusters:  {METALS}, {EUR/GBP/CHF}, {USDJPY/AUD/NZD/CAD}, {CRYPTO}, {COMMOD}
  New clusters:  {METALS+XAUUSD-DXY axis}, {EUR/GBP/CHF}, {USDJPY/AUD/NZD/CAD},
                 {BTC alone}, {ETH+ALTS+COMMOD}, {NZD+AUD as pair}
  
  Action: BTCUSD currently in CRYPTO team but cluster-wise drifted to its own
  cluster. If you hold BTCUSD long simultaneously with ETHUSD long, treat as
  TWO positions for risk-cap purposes, not one cluster of two.

Persisted: logs/correlation_history/2026-04-25.json
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-correlation-monitor\corr.py
```

Pass `--pair XAUUSD,DXY` to investigate a specific pair (skill will pull from cross-asset cache if symbol not in your data). Pass `--full-matrix` to dump all 19×19. Pass `--baseline-days 180` to override.

## Critical guardrails

- **Correlation is not causation.** Skill flags shifts; operator interprets cause.
- **30-day window is short**; a single tail event can move it. Always cross-check against 60-day.
- **Don't recommend "trade against the new correlation"** — that's a separate strategy decision; this skill is risk-monitoring.
- **Honor existing cluster caps from `portfolio_risk.py`** — if the new cluster recommendation would lift a cap, recommend a *tighter* cap, never looser.

## Helper script

`corr.py` next to this SKILL.md.

## References

- Quantpedia 2024 correlation-regime studies.
- TrendMaster `ai_trading_agents/portfolio_risk.py` cluster module.
- Robot Wealth blog on FX correlation regimes (2024-2025).
