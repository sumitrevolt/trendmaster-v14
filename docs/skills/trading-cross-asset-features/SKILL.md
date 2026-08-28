---
name: trading-cross-asset-features
description: Pull DXY, US10Y, VIX, and gold/oil ratios H1-aligned and merge them into TrendMaster v14 build_features. Top-3 ML ROI item per the 2026 research brief — single-pair models leave 30-40% of variance on the table for FX. Use when the user asks "add cross-asset features", "DXY", "VIX as a feature", "macro features", "is the model missing the dollar index", or wants to extend the FEATURE_COLS list.
---

# Trading Cross-Asset Features

Pull DXY, US10Y yield, VIX, and gold/oil ratio H1-aligned to TrendMaster's per-symbol bars. Cache locally so feature builds are deterministic and don't depend on flaky free APIs at inference time.

## When to invoke

- Operator asks "add cross-asset features", "DXY", "VIX as a feature".
- Before any FOREX retrain — these are the highest-magnitude features-not-yet-included.
- Quarterly cache refresh.

## What gets pulled

| Feature | Source | Why |
|---|---|---|
| `dxy_close` | Yahoo `DX-Y.NYB` (or broker `USDX` if available) | Single biggest non-pair feature for non-USD majors. |
| `dxy_ret_1h` | derived | Direction of dollar-strength move. |
| `us10y_yield` | FRED series `DGS10` (free, no key) | First-order driver of JPY pairs. |
| `us10y_d1d` | derived (daily delta) | Yield change momentum. |
| `vix_close` | Yahoo `^VIX` | Risk-on/off regime. |
| `vix_z_30d` | rolling z-score | Surprise-vs-baseline. |
| `gold_oil_ratio` | derived from your existing XAUUSD and XTIUSD CSVs | Macro stagflation indicator; cheap, no extra pull. |

All series H1-aligned by **forward-fill within session, NaN over weekend gap**. NEVER zero-fill or interpolate — those silently leak signal.

## Cache layout

```
data/cross_asset/
  dxy_h1.parquet         columns: ts, close, ret_1h
  us10y_h1.parquet       columns: ts, yield, d1d
  vix_h1.parquet         columns: ts, close, z_30d
  meta.json              {last_refresh_ts, source_versions, rows_per_series}
```

Refresh policy: `pull_macros.py` only re-pulls if `meta.json.last_refresh_ts` is older than 6 hours, OR if `--force` is passed. This keeps `build_features` cheap.

## Output integration

The skill emits a `cross_asset_join.py` helper that returns a DataFrame Claude should merge into `build_features` like:

```python
# In ai_trading_agents/trend_master_brain.py::build_features, after line ~480:
from ai_trading_agents.cross_asset_join import attach_macros
df = attach_macros(df, symbol)
# Add to FEATURE_COLS:
FEATURE_COLS += ["dxy_ret_1h", "us10y_d1d", "vix_z_30d", "gold_oil_ratio_z_30d"]
```

The integration is intentionally manual — Claude proposes the diff but does NOT auto-edit `trend_master_brain.py`. After integration, the operator must:

1. Retrain all four team models (else `ml_align` will block inference for shape mismatch — exactly the guardrail we want).
2. Re-run `tools/validate_crypto_ml.py --team all` to confirm CPCV doesn't regress.
3. Re-run `trading-model-healthcheck` after a week of live data.

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-cross-asset-features\pull_macros.py --refresh
```

Pass `--force` to ignore the 6-hour TTL. Pass `--check` to print cache freshness and row counts without pulling.

## Critical guardrails

- **Forward-fill within session, NaN over weekend.** Macro feeds skip weekends; if you forward-fill across the weekend gap you create lookahead-flavored stationarity.
- **Add `is_stale_<feature>` boolean columns** so the model can learn when a value is fresh vs imputed. Without these flags, ML treats stale values as if they were live.
- **Pull from FREE sources only** (Yahoo, FRED). Do not introduce paid feeds without operator approval.
- **Cache is read-write at `data/cross_asset/`**; never write outside that directory.
- **Don't auto-promote retrained models** — the operator's "trades on rules > trades on broken ML > no trades" invariant means a regression must trigger fallback to the previous model.

## Helper script

`pull_macros.py` next to this SKILL.md.

## References

- Quantpedia 2024 cross-asset FX studies (DXY/VIX/US10Y for major pairs).
- Robot Wealth blog 2023-2025 series on macro features.
- FRED API docs (`fred.stlouisfed.org`) for US10Y series.
