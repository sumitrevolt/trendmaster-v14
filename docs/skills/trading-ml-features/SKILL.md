---
name: trading-ml-features
description: "Advanced feature engineering and label design for financial ML. Use when going beyond EMA/RSI/MACD into mlfinlab-style techniques: alternative bars (tick, volume, dollar), fractional differentiation, triple-barrier and meta-labeling, volatility-regime features (HMM, GARCH proxies), microstructure (spread, tick-volume, imbalance), session features, and target engineering. Based on Lopez de Prado's 'Advances in Financial Machine Learning' as implemented in hudson-and-thames/mlfinlab, plus practical FX/XAUUSD adaptations."
---

# trading-ml-features

Most retail bots use EMA, RSI, MACD, maybe ADX. That's table-stakes and the edge is arbitraged out. Real statistical edge comes from features and labels designed for financial noise — the topic of Lopez de Prado's *Advances in Financial Machine Learning* and the `hudson-and-thames/mlfinlab` library.

This skill catalogues the techniques worth adding to a retail MT5 + Python bot, with honest notes on which actually move the needle on a 1-symbol retail strategy vs. which are HFT-only luxuries.

## When to use

- The current model plateaus around 55% win rate and you're out of basic-indicator ideas.
- You've read *AFML* and want to know which chapters are worth implementing for a retail use case.
- You suspect look-ahead leakage or label bias and need a rigorous labeling scheme.
- You want regime-dependent models (one for trending, one for ranging).
- You're preparing data for a walk-forward deep-learning experiment.

## 1. Alternative bars

Time bars (M5, H1, D1) are the default but statistically biased — they ignore how much *trading* actually happened. Alternative bars sample at a constant amount of activity, producing features closer to IID.

| Bar type | Sample point | When useful |
|---|---|---|
| **Tick bars** | Every N ticks | Low-cost, captures activity | HFT; less useful on H1 retail |
| **Volume bars** | Every N units of volume | Normalizes across sessions | Any TF; great for FX/crypto |
| **Dollar bars** | Every N units of quote currency | Normalizes across prices | Essential for long histories where price level changed materially |

### Implementation (dollar bars)

```python
def make_dollar_bars(ticks: pd.DataFrame, dollar_threshold: float) -> pd.DataFrame:
    """ticks columns: [ts, price, volume]"""
    ticks = ticks.copy()
    ticks["dollar"] = ticks["price"] * ticks["volume"]
    ticks["cum_dollar"] = ticks["dollar"].cumsum()
    # bar boundaries every dollar_threshold
    ticks["bar_id"] = (ticks["cum_dollar"] // dollar_threshold).astype(int)
    bars = ticks.groupby("bar_id").agg(
        ts=("ts", "last"),
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        volume=("volume", "sum"),
    ).set_index("ts")
    return bars
```

**Retail reality check:** MT5's `copy_ticks_range` returns ticks but rarely with reliable trade volume — most retail feeds report indicative bid/ask. Dollar bars with bad volume are worse than time bars. Validate volume quality first (check `volume.sum()` against known daily volumes) before building this.

`mlfinlab.data_structures` has production implementations: `get_tick_bars`, `get_volume_bars`, `get_dollar_bars`.

## 2. Fractional differentiation

Raw prices are non-stationary (they trend). Log-returns are stationary but destroy information about price *level*. Fractional differentiation (order `d ∈ [0, 1]`) finds the minimum `d` that achieves stationarity while preserving memory.

```python
from mlfinlab.features.fracdiff import frac_diff_ffd

# Fixed-window fractional differentiation
df_fd = frac_diff_ffd(price_series.to_frame("close"), d=0.4, thresh=1e-4)
```

**Rule of thumb for forex / XAUUSD H1:** `d ≈ 0.3 - 0.5` usually passes ADF stationarity while retaining > 80% correlation with raw price. `d=1` (full differencing = returns) strips nearly all level information.

**Retail reality check:** this is genuinely useful for ML that learns from multi-year data. For < 6 months of bars, log-returns are fine and frac-diff is overengineering.

## 3. Triple-barrier labeling

The most important technique in mlfinlab for retail use. Replaces the naive "up/down over next N bars" label with three barriers (TP, SL, time), labeled by which one was hit first.

```python
# From mlfinlab.labeling.labeling
from mlfinlab.labeling import get_events, add_vertical_barrier, get_bins

# 1. Define events — typically CUSUM filter or your strategy's own entry signals
t_events = entry_signal_timestamps   # from your Trend+Pullback detector

# 2. Dynamic vertical barrier = N bars out
vertical = add_vertical_barrier(t_events, close, num_hours=8)

# 3. Dynamic TP/SL as multiples of rolling volatility
target_vol = close.pct_change().ewm(span=100).std()

events = get_events(
    close=close,
    t_events=t_events,
    pt_sl=[2, 1],             # TP = 2×vol, SL = 1×vol
    target=target_vol,
    min_ret=0.001,
    num_threads=1,
    vertical_barrier_times=vertical,
)

# 4. Label: +1 / -1 / 0 by first barrier touched
labels = get_bins(events, close)  # columns: ret, bin
```

**Why this beats naive labels:**

- Dynamic barriers scale with volatility — tight in calm markets, wide in volatile ones. A fixed-N-bar label mixes high-vol and low-vol noise.
- Time barrier forces resolution — no "held forever" edge cases.
- Labels mean what they look like: +1 = actually hit TP before SL, in the strategy's horizon.

**Retail reality check:** this is *the* upgrade. Even without the rest of mlfinlab, switching your label scheme to triple-barrier typically adds 3-8% to OOS win rate because the labels are cleaner.

## 4. Meta-labeling

A two-model cascade:
1. **Primary model** decides side (long/short) — often a simple rule or existing strategy.
2. **Meta model** decides whether to take the primary model's signal (binary: trade / don't).

The meta model is trained only on the primary's signals, labeled by whether each one reached TP before SL (triple-barrier). The meta model learns *when to trust* the primary — filters out regimes where the primary is unreliable.

```python
# Primary: your existing strategy emits side
primary_signals = strategy.predict_side(features)   # +1 / -1 / 0

# Labels (from triple-barrier on primary's trades only)
meta_labels = get_bins(events_for_primary_signals, close)["bin"]  # 1 / 0

# Meta model: features same as primary (or richer) + primary's side
meta_features = pd.concat([features, primary_signals.rename("side")], axis=1)
meta_clf = lgb.LGBMClassifier(...).fit(meta_features, meta_labels)
```

At inference:
```python
side = primary_model.predict(features_now)
if side != 0 and meta_clf.predict_proba(features_now)[0, 1] > 0.55:
    trade(side)
else:
    skip()
```

**Retail reality check:** genuinely moves the needle. The agent-bus in this project's `multi_agent.py` is conceptually a rule-based meta-labeler — each agent filters the others. A trained meta-labeler on top of your best rule strategy is often the fastest path to +10% PF.

## 5. Volatility regime features

Markets have regimes: calm, trending, crisis. A feature that captures regime lets the model learn conditional behavior.

### Rolling realized volatility quantile

```python
vol = close.pct_change().rolling(100).std()
regime = pd.qcut(vol, q=4, labels=[0, 1, 2, 3])   # 0 = calm, 3 = crisis
```

Simple, works, model-friendly.

### GARCH-based volatility

```python
from arch import arch_model
rets = close.pct_change().dropna() * 100
am = arch_model(rets, vol="Garch", p=1, q=1, dist="t")
res = am.fit(disp="off")
forecast_vol = res.forecast(horizon=1).variance.iloc[-1, 0] ** 0.5
```

GARCH-forecast vol as a feature is predictive for *risk sizing*, less so for direction. Use as a position-size modulator.

### Hidden Markov regime model

```python
from hmmlearn.hmm import GaussianHMM
X = rets.values.reshape(-1, 1)
hmm = GaussianHMM(n_components=3, covariance_type="diag").fit(X)
states = hmm.predict(X)   # 0 / 1 / 2 = inferred regime
```

HMM-inferred states are a clean feature. Three or four states cover most financial regimes. Fit on ≥ 2 years of data, or the regime labels are noise.

**Combine regime + strategy:** separate models per regime, or a single model with regime as a feature. The latter is simpler; the former wins when regime behavior is very different.

## 6. Microstructure features

Even without tick data, a few microstructure proxies are cheap and informative.

- **Spread percentile** — `SYMBOL_SPREAD` / rolling mean over 1000 bars. Alerts when liquidity is poor.
- **Tick volume z-score** — `(tick_vol - mean_100) / std_100`. Spikes indicate activity changes.
- **Candle body / range ratio** — `|close-open| / (high-low)`. High = directional candle; low = indecision.
- **Upper / lower wick ratios** — `(high - max(open, close)) / (high - low)`. Captures rejection.
- **Bar range / ATR** — `(high-low) / ATR14`. > 2 means "big bar" — often exhaustion or news.

### Example batch

```python
def microstructure_features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    rng  = (df["high"] - df["low"]).replace(0, np.nan)
    body = (df["close"] - df["open"]).abs()
    f["body_pct"]    = body / rng
    f["upper_wick"]  = (df["high"] - df[["open","close"]].max(axis=1)) / rng
    f["lower_wick"]  = (df[["open","close"]].min(axis=1) - df["low"]) / rng
    f["bar_vs_atr"]  = rng / atr(df["high"], df["low"], df["close"], 14)
    f["tickvol_z"]   = (df["tick_volume"] - df["tick_volume"].rolling(100).mean()) \
                       / df["tick_volume"].rolling(100).std()
    return f.fillna(0)
```

**Retail reality check:** these are cheap wins. Wick ratios and body percent consistently show up in feature-importance rankings. Tick-volume is broker-dependent on retail MT5 — useful if consistent, discard if not.

## 7. Session features

Markets behave differently across sessions. Encode this so the model doesn't have to learn it implicitly.

```python
def session_features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    hour = df.index.hour
    # session flags (broker time ~= GMT+2/+3)
    f["is_asia"]    = ((hour >= 0)  & (hour < 8 )).astype(int)
    f["is_london"]  = ((hour >= 8)  & (hour < 16)).astype(int)
    f["is_ny"]      = ((hour >= 13) & (hour < 22)).astype(int)
    f["is_overlap"] = ((hour >= 13) & (hour < 16)).astype(int)   # LDN+NY
    f["dow"]        = df.index.dayofweek
    # encode cyclical: keep the model aware of 23→0 hour wrap
    f["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    return f
```

Cyclical encoding (`sin`/`cos`) is more useful than raw hour when the model is a tree ensemble — trees can split on either representation but `sin/cos` preserves ordinal distance cleanly.

## 8. Target engineering

What you predict matters as much as the features.

| Target | Pros | Cons |
|---|---|---|
| **Next-bar sign** | Simple | Massive class imbalance, lots of noise |
| **Next-N-bar return** | Intuitive | Leaks autocorrelation; noisy |
| **Triple-barrier label** | Clean, strategy-aligned | Slow to compute; needs volatility estimator |
| **Trend-scanning label** (mlfinlab) | Captures trend segments | Requires tuning; overfits if misused |
| **Meta-label** | Filters primary model | Two-stage complexity |

**Default recommendation for retail MT5 ML:** triple-barrier with dynamic volatility target.

## 9. Feature importance & selection

After engineering 50+ features, cut to 10-20 that actually matter.

### Mean Decrease Impurity (MDI) — fast but biased

```python
model = lgb.LGBMClassifier(...).fit(X, y)
imp = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False)
```

MDI biases toward high-cardinality features. Useful as a first pass.

### Permutation importance (mlfinlab: `MDA` — mean decrease accuracy)

Shuffle one feature at a time, measure how OOS accuracy drops. A feature with high MDA is genuinely predictive, not just fit-by-bias.

```python
from sklearn.inspection import permutation_importance
r = permutation_importance(model, X_val, y_val, n_repeats=10, random_state=42)
mda = pd.Series(r.importances_mean, index=X_val.columns).sort_values(ascending=False)
```

Drop features below a threshold (e.g. MDA < 0.001). Refit and check OOS metrics didn't regress.

### Clustered feature importance

Correlated features dilute each other's importance. mlfinlab's `clustered_mda` groups correlated features and measures importance at the cluster level — more honest.

## 10. Leakage audit

The #1 cause of "backtest works, live fails" is label or feature leakage. Check every feature:

- Does computing feature `f(t)` require `close(t+1)` or later? If yes, leak.
- Does computing label `y(t)` use `close(t)` directly in the entry? Usually fine if entry is next-bar open.
- Does any rolling indicator use `center=True`? Leak.
- Are labels and features drawn from exactly disjoint time windows per fold (`trading-backtest` §4)? If not, leak.

A single leaking feature will inflate OOS metrics 10-20% and blow up live.

## 11. What NOT to bother implementing (opinionated)

From mlfinlab / AFML, these are HFT-specific or textbook exercises that rarely pay for a retail MT5 bot:

- **Structural breaks (CUSUM/Chow)** as features — useful as event detectors for labels (§3), not as model features directly.
- **Entropy features** (Shannon / Plug-in entropy on returns) — beautiful math, near-zero retail alpha.
- **Explosiveness tests (SADF)** — academically interesting, noisy on single-symbol forex.
- **Bet sizing via ensemble strength** (AFML ch 10) — useful if you have a calibrated ensemble; overkill for a single LightGBM.

Focus effort on: alternative bars (IF volume is clean), triple-barrier labels, meta-labeling, regime features, microstructure, session features. That's the top quartile for effort-to-alpha.

## 12. GitHub references

- `hudson-and-thames/mlfinlab` — the library. Read `mlfinlab/labeling/labeling.py` (`get_events`, `get_bins`), `mlfinlab/features/fracdiff.py`, `mlfinlab/data_structures/` for bars.
- `AI4Finance-Foundation/FinRL` — reinforcement learning on financial data; useful if you want a sanity check on how RL practitioners structure features.
- `stefan-jansen/machine-learning-for-trading` — the code companion to Stefan Jansen's book; excellent worked examples of many features in this skill.
- `tensortrade-org/tensortrade` — if you ever go to RL, this is the best-documented framework.
- `matplotlib/mplfinance` (not mlfinlab but useful) — for plotting the regime-classified features to sanity-check visually.

## Extension workflow

Adding a new feature:

1. Implement in `features/advanced.py` as a pure function taking a DataFrame, returning a Series or DataFrame.
2. Audit for leakage — shift-test (feature.shift(1) should still compute from historical data only).
3. Add to the feature builder behind a config flag so you can A/B.
4. Train two models (with/without), compare OOS via paired t-test. Reject if `p > 0.1`.
5. Check permutation importance in the kept model — if the new feature has MDA < 0.001, drop it.

Adding a new label scheme:

1. Implement. Plot class distribution across 5 folds; it should be stable.
2. Retrain and verify the model's predictive power is at least as good as triple-barrier (hard to beat for retail).
3. If the new labels require a different entry rule (e.g. trend-scanning implies you trade trend segments), align the live entry logic or you'll have train/inference mismatch.
