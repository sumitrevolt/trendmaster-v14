# Get EIA API key (5 min) — unlocks 33rd ML feature

## Why
The brain's V2 features include `ng_storage_delta_z` (US natural gas storage week-over-week change, z-scored). Source: U.S. Energy Information Administration's free API. Without the key, this column is all-NaN and the feature gets auto-dropped, leaving 32 of 33 effective V2 features. Adding it gives a small but free edge on commodity-correlated pairs (XAUUSD via dollar liquidity, XTIUSD/XBRUSD via energy).

## 3-step flow

1. Open the registration page (single click below) and fill the short form.
2. EIA emails you the key immediately.
3. Paste it into `config\.env` and restart the brain.

## One-click open

Double-click [`OPEN_EIA_REGISTRATION.cmd`](../OPEN_EIA_REGISTRATION.cmd) at workspace root, or visit:
- https://www.eia.gov/opendata/register.php

Form asks for: name, email, organization (put "Personal"), intended use ("personal data analysis"). Hit Register, key arrives via email within ~30 sec.

## Apply the key

Edit `config\.env` and add:
```
EIA_API_KEY=<paste_your_40_char_key_here>
```

Then restart the brain so the new key is picked up:
```
RESTART_BRAIN_NOW.cmd
```

## Verify

After restart, check brain log:
```
type logs\trend_master_brain.out | findstr "EIA"
```

Before the key:
```
[INFO] ai_trading_agents.cross_asset_join: EIA_API_KEY not configured; skipping NG storage features
```

After the key (expected):
```
[INFO] ai_trading_agents.cross_asset_join: EIA NG storage: fetched N weekly observations
```

The next time `build_features_v2` runs, you should see `8/8 smartmoney cols have data` instead of `7/8`.

## Free tier limits

EIA's free tier allows 5,000 calls/hour with no monetisation cap. The brain hits this endpoint once per H1 bar boundary (24 calls/day max) — well under the limit.
