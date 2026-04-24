# ML validation report - METALS

_Generated: 2026-04-24T16:17:38.893267+00:00_

## Verdict: **OK**

- walk-forward and CPCV metrics within tolerance of holdout baseline

## Holdout baseline (from registry)

- n_samples: 241
- win_rate:  71.4%
- test_auc:  0.726
- trained_at: 2026-04-23T07:24:38.508903+00:00

## Walk-forward (expanding window)

- folds:    5
- mean AUC: 0.589 (std 0.126)
- mean WR:  69.6% (std 13.3%)
- error:    -

### Per-fold

| fold | n_train | n_test | train_auc | test_auc | test_acc | test_wr | notes |
|-----:|--------:|-------:|----------:|---------:|---------:|--------:|:------|
| 0 | 40 | 40 | 0.717 | 0.500 | 0.450 | 52.5% |  |
| 1 | 80 | 40 | 0.848 | 0.588 | 0.550 | 55.0% |  |
| 2 | 120 | 40 | 0.859 | 0.543 | 0.575 | 77.5% |  |
| 3 | 160 | 40 | 0.863 | 0.484 | 0.525 | 77.5% |  |
| 4 | 200 | 41 | 0.840 | 0.831 | 0.780 | 85.4% |  |

## CPCV (combinatorial purged CV, embargo=5)

- folds:    15
- mean AUC: 0.586 (std 0.075)
- mean WR:  71.3% (std 8.0%)
- error:    -
