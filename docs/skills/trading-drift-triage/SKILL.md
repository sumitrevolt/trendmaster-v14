---
name: trading-drift-triage
description: When TrendMaster v14's ADWIN drift detector fires, return a triage report — which feature(s), which team(s), which last-3 trades would have flipped under current vs baseline distribution, and which step on the action ladder (log / degrade-to-rules / full halt) the operator should take. Use when the user asks "drift fired", "why did the drift detector page", "drift triage", "interpret this drift alert", or after `/drift` Telegram command returns red.
---

# Trading Drift Triage

Translate an ADWIN drift signal into a concrete operator action. Sits on top of `ai_trading_agents/drift_detector.py` (already implemented) and decides where on the action ladder the response should land.

## When to invoke

- ADWIN flag fires in the brain (visible via `/drift` Telegram command or `state.drift_alerts[]`).
- Operator asks "drift triage", "interpret this drift", "what should I do".
- After the morning `model-healthcheck` returns AMBER on `pvr` or `ece`.

## The action ladder

Per the 2025 ML-Ops drift survey, drift response should be **graduated, not binary**. Three tiers:

| Tier | Trigger | Action |
|---|---|---|
| **L1: Log only** | Single feature PSI > 0.2, but prediction-error stream stable. | Log the drift event; no behavior change. Continue trading. |
| **L2: Degrade** | ADWIN flag on prediction-error stream OR multi-feature PSI > 0.2 OR PvR-gap > 0.10. | Route the affected team to `infer_rule` via `ml_align` guard. Continue trading on rules. |
| **L3: Full halt** | L2 conditions PLUS 5-day P&L < -2σ vs baseline. | `state.trading_paused = True` for affected team; page operator. |

This skill computes which tier applies and prints the exact remediation command.

## Inputs

- `logs/drift_alerts.jsonl` — append-only log written by `drift_detector.ADWINDriftDetector`.
- `ai_trading_agents/ml_models/<team>_model.lgb` — for feature-list lookup.
- `data/<symbol>_m5_history.csv` — for current-vs-baseline distribution comparison.
- `brain_memory.json::trade_history[]` — for last-3-trades counterfactual.
- `state.trading_paused`, `state.drawdown_lockout_until` — context.

## Output

```
Drift Triage — 2026-04-25 11:42 UTC
===================================

Active drift alerts: 1
  team=CRYPTO  detector=ADWIN  feature=ema_stack  fired_at=11:38

Distribution comparison (current 200 bars vs baseline 2000 bars):
  CRYPTO/ema_stack:   PSI=0.34   KS=0.27   <-- significant drift
  CRYPTO/adx:         PSI=0.08   KS=0.05   ok
  CRYPTO/rsi:         PSI=0.11   KS=0.09   ok

Prediction-error stream (last 50 trades vs trailing 200):
  mean_residual now=+0.082  baseline=+0.003   shifted +0.079
  variance ratio=1.8        (drifted)

Last 3 trades that would have flipped under current vs baseline distribution:
  2026-04-25 09:30  BTCUSD long → SKIP    (current model = 0.51, would have been 0.62)
  2026-04-25 10:15  ETHUSD long → SKIP    (current model = 0.49, would have been 0.61)
  2026-04-25 11:00  XRPUSD short → KEEP   (still above conf floor)

5-day team P&L: -$48 (no positions liquidated, stop-out free)
Baseline 5-day mean: +$12  σ=$28
Z-score: -2.14   <-- exceeds -2σ threshold

==> RECOMMENDATION: TIER L3 (FULL HALT for CRYPTO team only)

Action commands (execute manually after confirming):
  1. Pause CRYPTO team:
     /halt-team crypto

  2. Confirm guard is doing its job (no behavior change for other teams):
     .venv\Scripts\python.exe tools\diagnose_zero_trades.py --team crypto

  3. Schedule retrain with cross-asset features once root cause is understood:
     .venv\Scripts\python.exe tools\train_v14_better.py --team crypto

  4. File postmortem template after resolution:
     /skills trading-postmortem-new --slug crypto_drift_2026-04-25 ...

DO NOT lower MIN_CONF below 0.50 to keep CRYPTO trading. Operator policy.
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-drift-triage\triage.py
```

Pass `--team <name>` to focus on one team. Pass `--explain` to dump the underlying PSI / KS computations.

## Decision rules

In code form (also embedded in `triage.py`):

```python
def decide_tier(psi_max, pvr_gap, recent_pl_z, adwin_fired) -> str:
    if not adwin_fired and psi_max < 0.2 and abs(pvr_gap) < 0.10:
        return "L0_no_action"
    if adwin_fired and recent_pl_z < -2.0:
        return "L3_full_halt"
    if adwin_fired or psi_max > 0.25 or abs(pvr_gap) > 0.10:
        return "L2_degrade_to_rules"
    return "L1_log_only"
```

Tunable thresholds live at the top of `triage.py`. Defaults reflect the 2025 Frontiers AI drift survey + Hudson & Thames practitioner blog.

## Critical guardrails

- **Recommend, never execute.** The triage skill prints commands; operator runs them. Auto-halting is too dangerous given Telegram-command idempotency edge-cases.
- **Don't recommend lowering MIN_CONF**. Operator policy is non-negotiable.
- **Don't recommend re-enabling spread_guard**. Same.
- **If drift is detected during a known macro event** (NFP, FOMC, CPI), tag the alert as `event_window` and de-rate the recommendation by one tier (L3 → L2). News-driven drift often self-resolves within 24h.

## Helper script

`triage.py` next to this SKILL.md.

## References

- Frontiers in AI 2024 drift survey (multivariate MMD test).
- APXML "concept drift strategies" guide (action ladder).
- Hudson & Thames blog on drift in production trading models.
- TrendMaster `ai_trading_agents/drift_detector.py::ADWINDriftDetector` — the detector this skill triages.
