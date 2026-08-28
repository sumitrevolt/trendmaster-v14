---
name: trading-model-healthcheck
description: Emit a six-metric model-health scorecard per TrendMaster v14 team — confidence-distribution std, Expected Calibration Error, prediction entropy, predicted-vs-realised gap, feature null-rate, retrain-age. Use when the user asks "is the model healthy", "model healthcheck", "model scorecard", "confidence distribution", "calibration", "is the brain still trustworthy", or as part of the morning routine. Would have caught the 2026-04-24 silent-failure on day 1, not day 47.
---

# Trading Model Healthcheck

Single-shot scorecard answering "is each team's model still trustworthy?" Six metrics with green/amber/red flags. Designed to run in <10 seconds during morning routine.

## When to invoke

- Operator asks "is the model healthy", "calibration", "scorecard".
- Daily morning routine, ideally before market open in operator timezone.
- After any retrain, drift event, or change to `infer_ml`.
- After any unexplained gap in trade activity (>24h with no signals despite live brain).

## The six metrics

| # | Metric | Why it matters | Green | Amber | Red |
|---|---|---|---|---|---|
| 1 | **conf_std_across_symbols** | Detects the 2026-04-24 silent failure (model returns same prob for all inputs) | >0.08 | 0.05–0.08 | <0.05 |
| 2 | **ECE_weekly** (Expected Calibration Error) | Predicted prob ≠ realised win-rate ⇒ model is mis-calibrated | <0.05 | 0.05–0.10 | >0.10 |
| 3 | **prediction_entropy_mean** | log(3)≈1.10 means uniform-noise; near 0 means overconfident | 0.6–1.0 | 0.4–0.6 or 1.0–1.05 | <0.4 or >1.05 |
| 4 | **PvR_gap_50tr** (predicted-vs-realised, last 50 trades) | Direct calibration error in live action | \|gap\| < 0.05 | 0.05–0.10 | >0.10 |
| 5 | **feature_null_rate** | Silent feed gaps; broker disconnect partials | <1% | 1–5% | >5% |
| 6 | **retrain_age_days** | Stale models drift | <14 | 14–28 | >28 |

## Inputs

- `ai_trading_agents/ml_models/<team>_model.lgb` — trained model files per team.
- `logs/brain_state.json` — last_signal_per_symbol with confidence values.
- `brain_memory.json::trade_history[]` — for realised-vs-predicted comparison.
- `data/<symbol>_m5_history.csv` — for fresh feature batch.

## Output

```
Model Healthcheck — 2026-04-25 09:14 local
==========================================

METALS team
  conf_std_across_symbols   0.092   GREEN   (XAUUSD/XAGUSD)
  ECE_weekly                0.043   GREEN
  prediction_entropy_mean   0.81    GREEN
  PvR_gap_50tr             +0.012   GREEN
  feature_null_rate         0.4%    GREEN
  retrain_age_days          7       GREEN
  Verdict: HEALTHY

FOREX team
  conf_std_across_symbols   0.061   AMBER   (8 majors)
  ECE_weekly                0.078   AMBER
  prediction_entropy_mean   0.93    GREEN
  PvR_gap_50tr             -0.067   AMBER
  feature_null_rate         0.6%    GREEN
  retrain_age_days          21      AMBER
  Verdict: AMBER — schedule retrain this week, watch closely

CRYPTO team
  conf_std_across_symbols   0.038   RED     <-- ALERT
  ECE_weekly                0.124   RED
  prediction_entropy_mean   0.42    RED     (overconfident)
  PvR_gap_50tr             +0.118   RED
  feature_null_rate         0.5%    GREEN
  retrain_age_days          5       GREEN
  Verdict: RED — degrade CRYPTO to infer_rule until investigated.
           This is the same shape as 2026-04-24. Check feature alignment
           with tools/diagnose_zero_trades.py --team crypto.

COMMODITIES team
  conf_std_across_symbols   0.087   GREEN
  ECE_weekly                0.051   GREEN
  prediction_entropy_mean   0.79    GREEN
  PvR_gap_50tr             -0.023   GREEN
  feature_null_rate         0.8%    GREEN
  retrain_age_days          11      GREEN
  Verdict: HEALTHY
```

Persist scorecard to `logs/model_healthcheck/<run_ts>.json`.

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-model-healthcheck\health_metrics.py --team all
```

Pass `--team crypto` to focus on one team. Pass `--explain` to print remediation steps for any RED finding.

## Critical guardrails

- **A RED `conf_std_across_symbols` is the canonical "model is broken" signal.** Recommend the operator degrade that team to `infer_rule` via the existing alignment-guard path, NOT lower MIN_CONF to force trades.
- **ECE depends on ≥30 trades in the window.** With fewer, mark as `INSUFFICIENT_DATA` rather than red.
- **retrain_age is informational not fatal.** A 60-day-old model that's still calibrated is fine.

## Helper script

`health_metrics.py` next to this SKILL.md.

## References

- Evidently+Grafana ML monitoring blog (2024).
- ICLR 2025 calibration blog post (ECE methodology).
- TrendMaster postmortem `docs/POSTMORTEMS/2026-04-24_zero_trades.md` — the failure shape this skill exists to catch.
