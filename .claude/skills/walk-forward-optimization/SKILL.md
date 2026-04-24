---
name: walk-forward-optimization
description: Run walk-forward optimization (WFO) and out-of-sample validation for the AMD trading bot's LightGBM brain and EA parameters. Use when retraining the brain, tuning MIN_CONFIDENCE / REQUIRED_CONFLUENCES / TRAIL_ATR_MULT, comparing parameter sets, or whenever the user worries the brain is overfit to recent market regime. Detects in-sample vs out-of-sample performance gaps and refuses to ship parameters that look like curve-fits.
---

# Walk-Forward Optimization

The single most common way an algo trading system dies is overfitting:
parameters look perfect on the data they were trained on, then collapse
on live tape. WFO is the defense.

## Core principle

Never test on data you fit to. Slide a train→validate→test window
forward through history and see if performance holds OUT of sample.

```
Window 1: [Train ────][Val][Test]                    weeks 1-12
Window 2:        [Train ────][Val][Test]              weeks 5-16
Window 3:               [Train ────][Val][Test]       weeks 9-20
...
```

In-sample (train) Sharpe of 3.5 means nothing if out-of-sample (test)
Sharpe is 0.4 — that gap *is* the overfit. A robust system shows
in-sample and out-of-sample within ~30% of each other.

## When to invoke this skill in this project

1. Before running `tools/train_v14_better.py` for a real promotion to live
2. After tuning anything in `config/settings.py`
3. When weekly demo PnL diverges sharply from backtest PnL
4. When the user says "the brain was working last week, now it's losing"
   — that's regime drift, and WFO is how you'd have caught it earlier

## Workflow for this repo

### Step 1: Pull a clean dataset
Use MT5 historical bars (M5/M15/H1) for at least 2 years per symbol.
Save to `data/wfo_<symbol>_<timeframe>.parquet` so reruns are reproducible.

### Step 2: Configure the windows
For an M5 strategy targeting daily-to-weekly holds:
- Train: 12 weeks
- Validate: 2 weeks (used to pick best params)
- Test: 2 weeks (untouched until final eval — NEVER tune to this)
- Step: 2 weeks (slide forward each iteration)

For a M5 system, that gives ~25 windows per year of data.

### Step 3: Run the sweep
```python
# Pseudo-code — tailor to tools/train_v14_better.py
for window in walk_forward_windows(data, train=12, val=2, test=2, step=2):
    for params in param_grid:
        train_brain(window.train, params)
        val_score = score(window.val)
    best = max(val_scores)
    test_score = score(window.test, best.params)
    record(window, best.params, val_score, test_score)
```

### Step 4: Read the result honestly

| Metric | Pass threshold |
|--------|----------------|
| Median test Sharpe | > 0.8 |
| Test Sharpe / Val Sharpe ratio | > 0.6 (anything <0.5 is overfit) |
| % windows with positive test PnL | > 55% |
| Max test drawdown | < 1.5x worst train drawdown |
| Best params consistency across windows | should cluster, not jump randomly |

If best params jump wildly per window (e.g. MIN_CONFIDENCE oscillating
between 0.45 and 0.75), the strategy has no stable optimum — it's noise.

## Specific anti-patterns to flag

- **Test set peeking.** If you ever look at test results then go back and
  re-tune, the test is contaminated. Cut a fresh test slice or accept
  the result.
- **Tiny param grids.** A 3-value sweep doesn't tell you the surface
  shape. Use 7-10 values minimum per knob.
- **Optimizing to total return only.** Sharpe, max drawdown, and trade
  count must all be in the objective; otherwise WFO picks lottery-ticket
  strategies that hit one big trade and call it a day.
- **Survivorship in symbol selection.** Don't only WFO on EURUSD because
  it's been profitable. Include the symbols the bot will actually trade.

## Anchored vs rolling windows

- **Rolling** (window above): each train uses *only* the most recent N
  weeks. Best for detecting regime drift; preferred for forex.
- **Anchored**: train start fixed, train end grows. Better for very stable
  regimes — rare in retail FX. Default to rolling here.

## Output: a WFO report

When WFO completes, produce `reports/wfo_<date>.md` with:
- Median in-sample vs out-of-sample Sharpe
- Distribution of best params across windows (histogram)
- Equity curve stitched from all out-of-sample test segments
- Pass/fail verdict against the thresholds above

If the verdict is FAIL, do not deploy. Tell the user clearly:
"The current parameter set is overfit — out-of-sample test Sharpe is
0.3 vs in-sample 2.1. Recommend simplifying the model or expanding the
training window before live promotion."

## Related skills

- `backtesting-frameworks` — owns the broader backtesting concepts
- `risk-metrics-calculation` — for the Sharpe/drawdown math used here
- `amd-trading-bot-ops` — for actually plugging WFO results into config
