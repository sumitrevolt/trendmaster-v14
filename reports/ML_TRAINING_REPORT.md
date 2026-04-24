# TrendMaster v14 - Per-Team ML Training Report

Generated: 2026-04-23 07:24 UTC

Source: `logs/brain_memory.json` -> `trade_history[]` (bucketed by team using `risk_manager.team_of`).

## Summary

| Team | Status | N | Wins | Losses | Win% | Train Acc | Test Acc | Precision | Recall | F1 | AUC |
|------|--------|---|------|--------|------|-----------|----------|-----------|--------|----|-----|
| METALS | trained | 241 | 172 | 69 | 71.4% | 0.7812 | 0.7347 | 0.8857 | 0.7750 | 0.8267 | 0.7264 |
| FOREX | insufficient_data | 0 | - | - | - | - | - | - | - | - | - |
| CRYPTO | trained | 259 | 257 | 2 | 99.2% | 0.9903 | 0.9423 | 0.9800 | 0.9608 | 0.9703 | 0.9608 |
| COMMODITIES | insufficient_data | 0 | - | - | - | - | - | - | - | - | - |

## METALS

- Samples: 241 (172W / 69L, win rate 71.4%)
- Model: `ai_trading_agents/ml_models/lgbm_METALS.pkl`
- Trained at: 2026-04-23T07:24:38.508903+00:00

**Metrics**

| Split | Accuracy | Precision | Recall | F1 | AUC-ROC |
|-------|----------|-----------|--------|----|---------|
| train | 0.7812 | 0.8571 | 0.8182 | 0.8372 | 0.8526 |
| test  | 0.7347 | 0.8857 | 0.7750 | 0.8267 | 0.7264 |

**Top 5 features (LightGBM gain)**

1. `session_london` - gain 124.74
2. `session_ny` - gain 94.65
3. `good_volatility` - gain 87.14
4. `rsi_divergence` - gain 77.98
5. `fvg` - gain 77.06

## FOREX

- Status: **insufficient_data**  (N=0, min required=50)
- insufficient data - will train when N >= 50

## CRYPTO

- Samples: 259 (257W / 2L, win rate 99.2%)
- Model: `ai_trading_agents/ml_models/lgbm_CRYPTO.pkl`
- Trained at: 2026-04-23T07:24:38.699224+00:00

**Metrics**

| Split | Accuracy | Precision | Recall | F1 | AUC-ROC |
|-------|----------|-----------|--------|----|---------|
| train | 0.9903 | 1.0000 | 0.9903 | 0.9951 | 0.9951 |
| test  | 0.9423 | 0.9800 | 0.9608 | 0.9703 | 0.9608 |

**Top 5 features (LightGBM gain)**

1. `volume_spike` - gain 973.13
2. `rsi_divergence` - gain 564.44
3. `session_ny` - gain 564.00
4. `good_volatility` - gain 555.58
5. `session_london` - gain 84.34

## COMMODITIES

- Status: **insufficient_data**  (N=0, min required=50)
- insufficient data - will train when N >= 50

## Honest caveats

- **One day of data.** All 500 trades in `brain_memory.json` are stamped 2026-03-08. There is no regime diversity - no high-vol news day, no holiday tape, no weekend crypto flush - so the models only know one market mood.
- **Class imbalance.** Overall split is ~429W / 71L (~85% win rate). `class_weight='balanced'` helps but a model that predicts WIN on everything already scores ~85% accuracy - look at precision/recall/AUC rather than accuracy.
- **Only 2 of 4 teams have any data.** METALS (XAUUSD) and CRYPTO (ETHUSD) are represented. FOREX and COMMODITIES have zero trades in memory; their models are stubs.
- **No out-of-sample window.** The 80/20 split is time-based but all 500 trades fall on the same calendar day, so the 'test' slice is effectively the last ~90 minutes of the same session as training. That is not a real OOS test.
- **Single-symbol-per-team coverage.** METALS has XAUUSD only (no XAGUSD); CRYPTO has ETHUSD only (no BTCUSD). A model trained on one symbol still generalizes cross-symbol on faith.
- **15 boolean features only.** No price/ATR/spread context. The model can't distinguish 'trend_aligned during London on a 0.05% ATR day' from 'trend_aligned during a news spike'.

## Recommendation

**Do NOT wire these into `trend_master_brain.py` yet.** Keep the current single-model fallback in production.

Gates to hit before switching the brain to per-team models:

1. At least **300 closed trades per team** covering **>=10 distinct trading days** (ideally spanning a news week).
2. Each team's test-slice AUC-ROC stably above 0.60 on a held-out **calendar** window (not an intra-day tail).
3. Cross-symbol coverage inside each team (e.g. both XAUUSD and XAGUSD for METALS; both BTCUSD and ETHUSD for CRYPTO).
4. A second validation pass via `tools/ea_parity` backtest showing the per-team model does not degrade EA-parity expectancy vs the current single model.

Until those gates are met, these artifacts exist so the pipeline is testable and so we can iterate quickly once the trade-feedback loop accumulates real data. Treat today's metrics as plumbing proof, not signal.
