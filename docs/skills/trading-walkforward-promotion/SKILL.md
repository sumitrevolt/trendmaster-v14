---
name: trading-walkforward-promotion
description: Decide whether a candidate ML model in TrendMaster v14 is allowed to replace the production model. Runs a CI-style gate combining CPCV-Sharpe (mean > 0, stdev < 0.5×mean), drift-stable (PSI < 0.2 vs production training set), calibration-ECE (< 0.10), and class-balance (no class < 15%). Use when the user asks "promote model", "is this model ready for production", "model promotion gate", "should I ship this retrain", or after any tools/train_v14_better.py run.
---

# Trading Walkforward Promotion

A model file is just bytes until something says "this is allowed to replace production". This skill is that something. Hard CI-style gate combining the four checks the operator currently does manually, and refuses to PROMOTE if any fails.

## When to invoke

- After any `tools/train_v14_better.py` run that produces a candidate model.
- Before any operator-driven swap of `<team>_model.lgb`.
- Quarterly re-validation of currently-deployed models.

## The four gates

| # | Gate | Threshold | Source |
|---|---|---|---|
| 1 | **CPCV mean Sharpe** | mean > 0 AND stdev < 0.5 × mean | `tools/cpcv.py::CPCVSplit` (already in repo) |
| 2 | **Drift vs prod training set** | PSI < 0.20 on every input feature | `ai_trading_agents/drift_detector.py` |
| 3 | **Calibration ECE** | < 0.10 (10-bin Expected Calibration Error) | Recomputed from CPCV out-of-fold preds |
| 4 | **Class balance** | No class < 15% of total | Direct count |

A model that fails any gate is **HOLD**, not PROMOTE. The "trades on rules > trades on broken ML > no trades" invariant means the cost of holding a borderline model is ~0; the cost of promoting a bad one is days of opportunity cost or worse.

## Inputs

- `--candidate <path>` — path to the candidate `.lgb` file.
- `--prod <path>` — currently-deployed model.
- `--data <path>` — training/validation parquet/csv.
- `--team <name>` — for routing into the right symbol set.

## Output

```
Walkforward Promotion Gate — CRYPTO team
========================================
Candidate: crypto_model_2026-04-25.lgb (size 2.4MB, trained on 47,201 bars)
Production: crypto_model.lgb (size 2.3MB, age 21 days)

Gate 1: CPCV (N=6, k=2 → 15 paths)
  Mean Sharpe: 0.72   stdev: 0.31   stdev/mean: 0.43
  [PASS]  mean > 0 AND stdev < 0.5 × mean

Gate 2: Drift vs production training set
  Max PSI across 25 features: 0.14 (rsi)
  [PASS]  no feature exceeded PSI 0.20

Gate 3: Calibration ECE (10-bin, on CPCV out-of-fold preds)
  ECE: 0.067
  [PASS]  ECE < 0.10

Gate 4: Class balance
  +1 (TP): 28.1%   0 (TIME): 43.2%   -1 (SL): 28.7%
  [PASS]  all classes ≥ 15%

VERDICT: PROMOTE

Promotion command (run manually after final review):
  copy /Y "ai_trading_agents\ml_models\_candidates\crypto_model_2026-04-25.lgb" ^
          "ai_trading_agents\ml_models\crypto_model.lgb"

After promotion:
  1. Restart brain via start_brain_clean.cmd (NOT taskkill)
  2. Confirm ml_align loads new feature_names cleanly: tools/diagnose_zero_trades.py --team crypto
  3. Run trading-model-healthcheck after first 50 trades

If you change your mind: previous prod is at ai_trading_agents/ml_models/_archive/<date>/
```

For HOLD verdict the output replaces the promotion command with:

```
VERDICT: HOLD

Failed gates: ECE=0.124 > 0.10
Recommendation:
  - Inspect predicted-prob calibration plot (per-class)
  - Likely cause: imbalanced sample weights — check getAvgUniqueness sample_weight
  - Re-train with corrected weights; re-run this gate.
  - Production model remains in service.
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-walkforward-promotion\promote.py ^
  --candidate ai_trading_agents\ml_models\_candidates\crypto_model_2026-04-25.lgb ^
  --prod ai_trading_agents\ml_models\crypto_model.lgb ^
  --data data\labels\crypto_combined_tb_h24_k2.0_1.5.parquet ^
  --team crypto
```

Pass `--write-archive` to (after a passing gate) print the archive command for the previous prod model.

## Critical guardrails

- **NEVER auto-execute the file copy.** The operator runs the promotion command manually after reviewing the report.
- **NEVER recommend bypassing a failed gate.** If ECE > 0.10, the right answer is fix ECE, not promote anyway.
- **Always preserve the previous prod model** under `_archive/<date>/` before swap. Skill prints the archive command but does not run it.
- **If candidate has fewer features than prod**, route through `ml_align` rather than refuse — feature alignment is exactly what that module exists to handle.

## Helper script

`promote.py` next to this SKILL.md.

## References

- TrendMaster `tools/cpcv.py::CPCVSplit` — already implements López de Prado CPCV.
- TrendMaster `ai_trading_agents/drift_detector.py::psi` — already implements PSI.
- TrendMaster `tools/validate_crypto_ml.py` — manual version of this gate.
- AFML ch.7 (Cross-Validation in Finance), ch.4 (Sample Weights).
