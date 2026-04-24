# ML validation report - CRYPTO

_Generated: 2026-04-24T16:17:39.706160+00:00_

## Verdict: **INSUFFICIENT_DATA - SEVERE CLASS IMBALANCE**

- minority class is only 0.8% of samples (threshold 10%); binary CV degenerates - most folds are single-class and AUC is undefined
- remediation: collect more loss trades OR relabel target (e.g., profit-bucket instead of win/loss) before trusting this model

## Holdout baseline (from registry)

- n_samples: 259
- win_rate:  99.2%
- test_auc:  0.961
- trained_at: 2026-04-23T07:24:38.699224+00:00

## Walk-forward (expanding window)

- folds:    5
- mean AUC: 1.000 (std -)
- mean WR:  99.4% (std 1.0%)
- error:    -

### Per-fold

| fold | n_train | n_test | train_auc | test_auc | test_acc | test_wr | notes |
|-----:|--------:|-------:|----------:|---------:|---------:|--------:|:------|
| 0 | 43 | 43 | - | - | - | - | single-class training fold |
| 1 | 86 | 43 | - | - | 0.930 | 100.0% | single-class test fold (AUC undefined) |
| 2 | 129 | 43 | - | - | 0.977 | 100.0% | single-class test fold (AUC undefined) |
| 3 | 172 | 43 | 0.994 | 1.000 | 0.977 | 97.7% |  |
| 4 | 215 | 44 | - | - | 0.977 | 100.0% | single-class test fold (AUC undefined) |

## CPCV (combinatorial purged CV, embargo=5)

- folds:    15
- mean AUC: 0.974 (std 0.013)
- mean WR:  99.3% (std 0.6%)
- error:    -
