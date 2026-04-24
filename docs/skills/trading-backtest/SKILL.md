---
name: trading-backtest
description: "Backtesting and ML training pipeline for an MT5-based trading bot. Use when building or reviewing the data pipeline (bar history, feature engineering), the label generator (ATR-threshold three-class bars), the model trainer (LightGBM multi-class with early stopping), walk-forward validation, and visualization of equity / drawdown / trade distribution. Covers the gap between raw CSVs and a deployable model."
---

# trading-backtest

Backtesting is where you find out if your idea has any edge before risking capital, and ML training is where you squeeze more out of the features you already have. Both live in Python, both need to be reproducible, and both are easy to lie to yourself with.

This skill codifies the patterns that worked for this project's v12/v14 model training, blended with common public-repo approaches (`freqtrade`, `backtrader`, `vectorbt`).

## When to use

- Training a new model (swapping features, swapping algorithm, retraining on fresh data).
- Evaluating a strategy change without going live.
- Adding walk-forward validation to catch look-ahead leakage.
- Building the equity / drawdown / trade-distribution visuals.
- Comparing two configs (A/B backtest) before picking one for production.

## 1. Data pipeline

Before any backtest, you need clean, timezone-sane bar data. The single biggest source of silent bugs is mixing a bar DataFrame in broker time with a feature DataFrame in UTC.

```python
import pandas as pd
import MetaTrader5 as mt5

def fetch_history(symbol: str, tf: str, n: int) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, _TF_MAP[tf], 0, n)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)   # UTC, always
    df = df.set_index("time").sort_index()
    # de-dup — MT5 occasionally returns duplicate seconds around DST boundaries
    df = df[~df.index.duplicated(keep="last")]
    # keep only closed bars — the last one from MT5 is live and will change
    df = df.iloc[:-1]
    return df
```

Cache to parquet, not CSV, for anything more than ~100k bars. Parquet is ~5× smaller and preserves dtypes.

## 2. Feature engineering — no leakage, every feature shift-able

A feature at time `t` must be computable using **only** data up to time `t-1` (or the `close` of bar `t` at earliest, depending on your entry rule). The classic leakage bug is using `rolling_mean(..., center=True)` or any future-touching function.

```python
def make_features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    c = df["close"]
    f["ret_1"]    = c.pct_change(1)
    f["ret_5"]    = c.pct_change(5)
    f["ema20"]    = c.ewm(span=20,  adjust=False).mean()
    f["ema50"]    = c.ewm(span=50,  adjust=False).mean()
    f["rsi14"]    = rsi(c, 14)
    f["macd_h"]   = macd_hist(c)
    f["adx14"]    = adx(df["high"], df["low"], c, 14)
    f["atr14"]    = atr(df["high"], df["low"], c, 14)
    f["atr_pct"]  = f["atr14"] / c
    f["hour"]     = df.index.hour
    f["dow"]      = df.index.dayofweek
    return f.dropna()
```

**Audit rule:** every feature should be safely `.shift(1)`-able without changing its meaning. If shifting breaks it, you have leakage.

## 3. Labels — ATR-threshold three-class

Binary up/down labels are a trap: every bar gets one, and the ratio of noise bars to signal bars is 5:1. Use a three-class ATR-threshold label.

```python
def label_atr(df: pd.DataFrame, horizon: int = 8, k_atr: float = 1.0) -> pd.Series:
    a  = atr(df["high"], df["low"], df["close"], 14)
    fwd_high = df["high"].rolling(horizon).max().shift(-horizon)
    fwd_low  = df["low"].rolling(horizon).min().shift(-horizon)
    c = df["close"]
    up = (fwd_high - c) >= k_atr * a
    dn = (c - fwd_low)  >= k_atr * a
    lbl = pd.Series(0, index=df.index, dtype="int8")  # 0 = noise
    lbl[up & ~dn] = +1                                 # clean up
    lbl[dn & ~up] = -1                                 # clean down
    # rows with both up and down within horizon stay 0 — by design, we don't trade them
    return lbl.iloc[:-horizon]                         # drop bars w/o enough forward data
```

**Defaults that work for XAUUSD H1:** `horizon=8`, `k_atr=1.0`. Class distribution lands around 25/50/25 (up/noise/down). If you see 5/90/5, your `k_atr` is too high; if 45/10/45, it's too low.

## 4. Train/test split — walk-forward only

Random splits leak time-series structure. Use an expanding or rolling walk-forward so every test period strictly follows its training data.

```python
from sklearn.model_selection import TimeSeriesSplit

tss = TimeSeriesSplit(n_splits=5, test_size=2000)  # ~2000 bars per test fold
for fold_i, (tr, te) in enumerate(tss.split(X)):
    X_tr, X_te = X.iloc[tr], X.iloc[te]
    y_tr, y_te = y.iloc[tr], y.iloc[te]
    ...
```

**Gap between train and test:** bigger than your feature window. If your longest feature uses `ewm(span=200)`, gap by 200 bars; otherwise rolling state contaminates.

## 5. Model — LightGBM multi-class with early stopping

LightGBM is the right default for tabular financial features: fast, handles NaN, robust to irrelevant features, no scaling required.

```python
import lightgbm as lgb

params = dict(
    objective="multiclass",
    num_class=3,
    learning_rate=0.05,
    num_leaves=63,
    min_data_in_leaf=200,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=5,
    lambda_l1=0.1,
    lambda_l2=0.1,
    metric="multi_logloss",
    verbose=-1,
)

# labels must be in [0, num_class-1] — map -1/0/+1 → 0/1/2
y_map = y.map({-1: 0, 0: 1, +1: 2})

model = lgb.train(
    params,
    lgb.Dataset(X_tr, y_tr_mapped),
    num_boost_round=2000,
    valid_sets=[lgb.Dataset(X_te, y_te_mapped)],
    callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
)
```

**Convert predictions back at inference time:**

```python
proba = model.predict(X_live)             # shape (N, 3)
pred_class = proba.argmax(axis=1)          # 0/1/2
pred_label = {0: "SELL", 1: "NONE", 2: "BUY"}[int(pred_class[-1])]
confidence = float(proba[-1, int(pred_class[-1])])
```

### Threshold

Don't trade every non-noise prediction. Require `confidence >= 0.55` (or whatever the calibrated threshold is from your backtest). Below that, return NONE. The EA should refuse anyway but defense in depth is good.

## 6. Backtest loop

You can build your own or use `backtrader`/`vectorbt`; for simple "on-close-of-bar" strategies the hand-rolled version is clearer and avoids a framework dependency.

```python
def backtest(df: pd.DataFrame, pred_series: pd.Series, tp_atr: float = 2.0, sl_atr: float = 1.0):
    a    = atr(df["high"], df["low"], df["close"], 14)
    equity = [10_000.0]
    trades = []
    in_pos = None    # (side, entry_idx, entry_px, sl, tp)
    for i in range(1, len(df)):
        row = df.iloc[i]
        if in_pos:
            side, entry_idx, entry_px, sl, tp = in_pos
            if side == +1:
                if row["low"] <= sl:
                    pnl = (sl - entry_px); _close(pnl)
                elif row["high"] >= tp:
                    pnl = (tp - entry_px); _close(pnl)
            else:
                if row["high"] >= sl:
                    pnl = (entry_px - sl); _close(pnl)
                elif row["low"] <= tp:
                    pnl = (entry_px - tp); _close(pnl)
        else:
            sig = pred_series.iloc[i]
            if sig in (+1, -1):
                entry_px = row["close"]
                sl = entry_px - sig * sl_atr * a.iloc[i]
                tp = entry_px + sig * tp_atr * a.iloc[i]
                in_pos = (sig, i, entry_px, sl, tp)
    # ... return equity, trades
```

**Required metrics per backtest:**

- Total return %
- Max drawdown % (peak-to-trough of the equity curve)
- Sharpe (or Sortino) — daily returns, sqrt(252) annualized for daily TF, sqrt(252*24) for H1
- Win rate and average R:R per trade
- Profit factor (gross wins / gross losses) — should be > 1.3 to take seriously
- Number of trades (< 30 = not statistically meaningful, reject the result)

## 7. Walk-forward equity curve

Concatenate the test-fold trades from every walk-forward fold. **Never** show an in-sample equity curve as if it were real performance — that's backtest-overfit lie #1.

```python
oos_equity = []
for fold in folds:
    oos_equity.extend(fold.test_trades)
curve = pd.Series(oos_equity).cumsum()
```

Plot that curve. If it doesn't go up and to the right, nothing else you do will save you — change the features or the label before you tune hyperparameters.

## 8. Visualization

Four plots are enough for most decisions:

1. **Equity curve** (cumulative PnL over time, OOS only).
2. **Drawdown** (running peak minus current equity, as percent).
3. **Per-trade PnL histogram** — tells you if a handful of outlier trades are carrying the result.
4. **Monthly returns heatmap** — surfaces seasonality and "only works in 2020" strategies.

`matplotlib` + `seaborn` is plenty. Save PNGs to `reports/<date>/`, they're cheap.

## 9. A/B comparison

When comparing config A vs. B, run both on the **same bars, same folds, same seed**, or you're comparing noise. Report the diff in each metric with a significance check:

```python
from scipy.stats import ttest_rel
t, p = ttest_rel(trades_A, trades_B)
print(f"A vs B: mean diff={np.mean(trades_A) - np.mean(trades_B):.2f}  p={p:.3f}")
```

`p > 0.1` means the "improvement" is noise. Don't ship it.

## 10. Common backtest lies

- **Look-ahead leakage** → features use `t+1` data. Fix: always `.shift(1)` before comparing to labels; audit each feature.
- **Survivorship bias** (less common for single-symbol forex but real for equities) → data missing delisted tickers.
- **Spread/slippage ignored** → backtest enters at bar close, live enters at market + spread. Add a fixed `spread_cost` per trade.
- **Position sizing constant** while backtesting percent-equity live → different strategy. Backtest must match live sizing.
- **Weekend gaps** counted as drawdown → optional; depends on whether live system holds weekends. Usually skip bars where `bar.index.dayofweek >= 5`.
- **Trained on labels that used future data** → always double-check the label definition drops the horizon tail.

## 11. Reproducibility

Save with every model:

- `model.pkl` (joblib or native LightGBM save)
- `features.json` — ordered list of feature names the model expects
- `config.json` — params, horizon, k_atr, threshold, symbol, TF
- `train_metrics.json` — final train/val loss, best iteration
- `backtest_oos.json` — OOS metrics

At inference time, **load `features.json` and assert the column order** matches the live DataFrame, or a silent misalignment will wreck predictions:

```python
assert list(X_live.columns) == features_json["columns"], "feature order mismatch"
```

## 12. GitHub references

- `freqtrade/freqtrade` — battle-tested backtest engine with realistic slippage/fee models; heavy but educational.
- `polakowo/vectorbt` — vectorized backtesting if you need speed on 1M+ bar runs.
- `mrjbq7/ta-lib` (Python bindings) — reference indicator implementations to cross-check your own.
- `LightGBM` docs — especially the "parameter tuning" page.

## Extension workflow

Adding a new feature:

1. Implement in `features.py`, return a single Series.
2. Add to `make_features` behind a config flag so you can A/B.
3. Train with and without; compare OOS Sharpe and win-rate.
4. If the feature only helps one fold, reject — that's noise.
5. If accepted, bump the model version string and include in `features.json`.

Adding a new label scheme:

1. Implement as a `label_*` function.
2. Plot class distribution across 5 folds — it should be stable.
3. Retrain the full pipeline.
4. Compare OOS metrics fold-by-fold, not on the aggregate (aggregate hides fold-specific blow-ups).
