---
name: trading-optimization
description: "Parameter optimization and tuning for trading strategies without curve-fitting. Use when running MT5 Strategy Tester, sweeping Python-side hyperparameters, picking between brute-force / genetic / Bayesian search, setting up walk-forward + combinatorial purged cross-validation, and detecting overfitting. Covers MT5 .set files, Optuna integration, deflation adjustments, and the 'when to stop tuning' rule."
---

# trading-optimization

Optimization is where most retail bots die — not from bad ideas, but from *over*-fitting them. A parameter sweep that shows "Strategy X returns 300% at (RSI=17, EMA=23, ATR=2.4)" almost certainly does not generalize. This skill covers how to tune without fooling yourself.

**Core principle:** Never optimize on data you will evaluate on. Never fit more parameters than your trade count can statistically support. Always report the *deflated* metric, not the best one.

## When to use

- First-time parameter selection for a new strategy.
- Re-tuning after drift (symbol regime changed; retune on recent data).
- Comparing two strategy variants head-to-head.
- Deciding which inputs to expose vs. hard-code.
- Running a genetic optimization in MT5 Strategy Tester.

## 1. The overfitting tax

Every additional parameter you optimize costs you statistical confidence. A rule of thumb from Lopez de Prado / Bailey:

> If you optimize `K` independent parameters, expect the best-of-K Sharpe on the training set to be inflated by ~`√(2 ln K / N)` where `N` is the number of trades.

Practical implication: **don't optimize more than 3-4 parameters** on a strategy producing fewer than 200 trades. Beyond that, any "improvement" is selection bias.

### Deflated Sharpe adjustment

After picking a best-of-K optimization, compute a deflated Sharpe:

```python
import numpy as np
def deflated_sharpe(sr_best, n_trials, n_trades, skew=0, kurt=3):
    """Bailey & Lopez de Prado (2014)"""
    v = 1 - np.euler_gamma + np.euler_gamma * np.log(n_trials) + (1 - np.euler_gamma) * np.log(np.log(n_trials))
    threshold = np.sqrt(v) / np.sqrt(n_trades)
    # very simplified; see paper for full form with skew/kurt
    return sr_best - threshold
```

If the deflated Sharpe < 0.5, don't ship.

## 2. MT5 Strategy Tester — the native path

MT5's Strategy Tester is powerful but has quirks you must know.

### Modes

| Mode | Use | Speed | Risk |
|---|---|---|---|
| **Every tick based on real ticks** | Final validation | Slow | — |
| **Every tick** | Dev iteration | Medium | Simulated ticks can diverge from real |
| **1 minute OHLC** | Rough sweeps | Fast | Misses intra-minute behavior |
| **Open prices only** | Not recommended | Very fast | Unrealistic — orders fill at open only |

**Default to "Every tick based on real ticks" for final runs.** "1 minute OHLC" is fine for a first parameter sweep to narrow the space.

### Optimization types

- **Slow complete algorithm** — brute force. Feasible for ≤ 3-4 parameters × ≤ 10 values each (≤ 10,000 runs).
- **Fast genetic based algorithm** — MT5's built-in genetic. Good for larger spaces but noisy (multiple runs give different winners).
- **All symbols**, **All symbols selected in Market Watch** — parallelize parameter sweep across symbols; use to test robustness.

### Custom optimization criterion

MT5's default "Balance" or "Profit Factor" are bad optimization targets — they favor lucky runs. A better criterion:

```cpp
double OnTester()
{
    double pf    = TesterStatistics(STAT_PROFIT_FACTOR);
    double dd    = TesterStatistics(STAT_BALANCE_DD_RELATIVE);
    double trades= TesterStatistics(STAT_TRADES);
    double sharpe= TesterStatistics(STAT_SHARPE_RATIO);

    if(trades < 30) return 0;                      // not enough signal
    if(dd > 30.0)   return 0;                      // reject >30% DD
    // weighted score — Sharpe dominates, PF breaks ties, penalize DD
    return sharpe * 2.0 + pf - (dd / 10.0);
}
```

### `.set` files — save/load parameters

Right-click in Strategy Tester → Save Set → `*.set`. Plain text, commit to git. A parameter change that's not checked into a `.set` file didn't really happen.

```ini
; .set file format
InpRiskPct=0.5
InpMaxSpreadPoints=500
InpHTF_ADX_Min=20.0
...
```

Keep one `.set` per deployed configuration, labeled with date + symbol + TF: `trendmaster_xauusd_h1_2026-04.set`.

### Walk-forward in MT5

Native walk-forward in MT5 is awkward. Workaround:

1. Run optimization on bars `[T0, T1]`.
2. Pick winning parameters by custom criterion.
3. Run a **single backtest** on `[T1, T2]` (out-of-sample window) with those parameters.
4. Only the `[T1, T2]` result counts. If negative, the optimization was curve-fit.
5. Repeat rolling: `[T0, T1]`→test on `[T1, T2]`; `[T1, T2]`→test on `[T2, T3]`; etc.

Aggregate the OOS segments into a single equity curve — **that** is your honest performance.

## 3. Python-side optimization — Optuna

For anything more complex than MT5 native can handle (e.g. multi-timeframe agent bus tuning), use Optuna with its TPE sampler.

```python
import optuna

def objective(trial):
    adx_min = trial.suggest_int("adx_min", 15, 30)
    rsi_low = trial.suggest_int("rsi_low", 30, 45)
    rsi_hi  = trial.suggest_int("rsi_hi",  55, 75)
    atr_mult= trial.suggest_float("atr_mult", 1.0, 3.0, step=0.25)

    params = dict(adx_min=adx_min, rsi_low=rsi_low, rsi_hi=rsi_hi, atr_mult=atr_mult)

    # Walk-forward OOS Sharpe
    fold_sharpes = walk_forward_backtest(params, folds=5, min_trades=30)
    if any(f is None for f in fold_sharpes):   # too few trades in some fold
        raise optuna.TrialPruned()
    return float(np.mean(fold_sharpes))

study = optuna.create_study(direction="maximize",
                            sampler=optuna.samplers.TPESampler(seed=42))
study.optimize(objective, n_trials=200, show_progress_bar=True)
print(study.best_params, study.best_value)
```

**Guardrails:**

- **Prune trials** that fail minimum-trades guard, don't return zero. Failed trials count against the trial budget; pruned don't.
- **Fixed seed** for reproducibility — `TPESampler(seed=42)`.
- **Limit trials** to what makes statistical sense. 200 trials on 4 parameters is sensible. 10,000 trials on 2 parameters is just overfitting fast.

### Suggest ranges sanely

- **Too narrow** → optimizer converges to boundary, suggesting the true optimum is outside. Widen.
- **Too wide** → wastes trials on obviously bad values. Narrow.
- **Start coarse, refine.** First sweep: 20 values per param, 50 trials. Second: narrow to ±20% around best, 200 trials.

## 4. Combinatorial Purged Cross-Validation (CPCV)

The gold standard from mlfinlab for time-series ML, approximating k-fold while respecting ordering.

Instead of a single train-test split per fold, CPCV generates **many** non-overlapping test combinations, with training data purged of any bars that could leak into the test set via feature windows.

```python
from mlfinlab.cross_validation import CombinatorialPurgedKFold

cv = CombinatorialPurgedKFold(n_splits=6, n_test_splits=2,
                              pct_embargo=0.01,
                              samples_info_sets=events["t1"])
for train_idx, test_idx in cv.split(X=features, y=labels):
    fit_and_evaluate(train_idx, test_idx)
```

**When to use CPCV:** model tuning where you have enough data (≥ 1 year of bars) and care about statistical rigor. For quick iteration, plain walk-forward is simpler.

## 5. What to optimize — and what to hard-code

A useful mental split:

**Optimize (expose as Inputs):**
- Risk sizing (`InpRiskPct`)
- Spread/session filters (broker-specific)
- SL/TP multipliers
- Key indicator thresholds (ADX min, RSI bounds)
- Number of agents required for consensus

**Don't optimize (hard-code or conservative default):**
- Indicator periods (EMA 20/50/200 are canonical; optimizing doesn't help much and invites overfit)
- SL direction (always protective, never hopeful)
- Daily kill-switch percent (set by your risk tolerance, not the backtest)
- Logging level

A common failure mode: exposing 30 `Inp*` params, optimizing all, finding a magic combination that returns 800% in backtest and -50% live. The magic combination fit a random-looking pattern in the backtest period.

## 6. Overfitting detection

Five tests to run on any optimization result:

### 6a. Parameter stability

Perturb each winning parameter by ±10% and re-backtest. If results collapse, you overfit a knife-edge peak. Stable strategies have broad plateaus.

### 6b. Time-robustness

Split your data into 3 equal thirds. Run the same parameters on each third separately. If returns are wildly different (3×, -1×, 0.5×) across thirds, the strategy depends on a specific regime you won't have going forward.

### 6c. Similar-symbol test

Optimize on EURUSD → does it still profit on GBPUSD, AUDUSD? If it only works on the one it was optimized for, the optimization found symbol-specific noise.

### 6d. White's Reality Check (approx)

Record the *distribution* of all trial returns. If the best trial is only a little better than the 90th percentile, the "edge" is within noise. Only celebrate when the best is clearly in the right tail.

### 6e. Monte Carlo trade shuffling

Take the trade-by-trade returns of your best run. Shuffle the sequence 1000 times. Plot the distribution of final equity. If the actual run lands in the middle of the distribution, your result is consistent with random trade ordering — meaning the specific entries didn't matter much.

## 7. Genetic optimization — pros and pitfalls

MT5's genetic optimizer is fast and explores large spaces, but:

- **Non-deterministic** — seed isn't exposed, so two runs give different "best" params.
- **Elite convergence** — tends to cluster around one local optimum; misses multi-modal landscapes.
- **Early termination** — stops on generations-without-improvement heuristic; sometimes the true optimum hasn't been found.

**Mitigation:** run genetic optimization 3+ times, take the **median** of winning param sets, not the single best. Confirms consistency and avoids lucky outliers.

## 8. Bayesian optimization — Optuna TPE

Better than genetic for expensive objective functions. TPE (Tree-structured Parzen Estimator) builds a probabilistic model of "promising" vs. "not promising" regions and samples accordingly.

Good when:
- Each backtest run takes > 10 seconds.
- Parameter space is smooth (small change → small metric change).
- You want reproducibility (fixed seed).

Not ideal when:
- Objective is very noisy — then a broader sampler (CmaEs, random search) is more robust.
- Strong discrete structure — e.g. "use agent A or agent B but never both" — is awkward in TPE.

## 9. Multi-objective optimization

Rarely do you want pure return. More common: maximize Sharpe subject to max DD < 20%. Optuna handles this natively:

```python
study = optuna.create_study(
    directions=["maximize", "minimize"],   # sharpe, dd
)

def objective(trial):
    params = {...}
    sharpe, dd = backtest(params)
    return sharpe, dd

study.optimize(objective, n_trials=300)
# study.best_trials returns the Pareto front
```

Pick from the Pareto front according to your risk appetite — the highest-Sharpe point isn't always best if its DD is 40%.

## 10. When to stop tuning

A common retail trap is infinite tuning. Rules to stop:

- **Budget:** "I'll run 200 trials, take the best, deploy." Commit in advance.
- **Plateau:** if the last 30 trials haven't improved the best by > 5%, stop.
- **Walk-forward OOS degrades** relative to in-sample by > 30% — the added params are fitting noise.
- **You've re-tuned 3 times in a row and each retune gives different winners** — the strategy's edge is too fragile to tune; rebuild it, don't optimize it.

## 11. `.set` file conventions for this project

```
chart_surgery/
  trendmaster_xauusd_h4_2026-04.set        # current live
  trendmaster_xauusd_h4_2026-03.set        # previous live (for A/B rollback)
  trendmaster_eurusd_h1_experimental.set   # A/B candidate
```

Every deploy flips the live `.set`, saves the previous as `.previous.set`. Rollback is one file-copy.

## 12. Common optimization bugs

- **Optimizing in-sample, "validating" on nearby window** → bars in the validation window touched by feature lookbacks from the training window leak. Embargo or purge.
- **Different spread/commission assumptions** between optimization and live → tune with *higher-than-live* costs (50% safety margin). Optimizing with zero costs always wins.
- **Reporting best instead of median** of a genetic/TPE run → lucky outlier. Report median + IQR.
- **Forgetting trade count in objective** → optimizer finds "strategy that took 2 trades in 5 years, both wins, Sharpe 10". Reject below minimum trades.
- **Optimizing for returns, deploying on leverage** → returns optimum doesn't care about DD, but leveraged deployment does. Use Sharpe or Sortino, not pure return.

## 13. GitHub references

- `optuna/optuna` — primary hyperparameter tuner.
- `hudson-and-thames/mlfinlab` — `cross_validation` module for CPCV, purging, embargo.
- `scikit-optimize` — alternative Bayesian optimizer if Optuna feels heavy.
- `freqtrade/freqtrade` — read `freqtrade hyperopt` docs; they've solved these problems cleanly at retail scale.
- `quantopian/research_public` — historical notebooks on overfitting detection techniques.

## Extension workflow

Optimizing a new parameter:

1. Define sensible bounds in a comment — justify why (research, prior knowledge).
2. Run a coarse sweep (20 values, 50 trials).
3. Check parameter stability — is the winner on a broad plateau or a spike?
4. Run walk-forward OOS test on the winner.
5. Run same-symbol-different-period and different-symbol robustness checks.
6. If all pass, save as a `.set` file with date and commit.
7. Deploy → monitor for one week in dry-run before live.

Re-optimizing after drift:

1. Freeze current live `.set` as `.previous.set`.
2. Pull last 3 months of bars + re-run optimization.
3. Compare new winner to current live on OOS slice — only flip if > 20% improvement.
4. If flipping, canary: run new params on half the account size for a week first.
