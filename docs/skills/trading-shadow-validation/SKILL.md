---
name: trading-shadow-validation
description: Validate brain's shadow predictions against actual TV-driven trade outcomes. Use when the operator asks "is the brain agreeing with TV signals?", "should I enable metalabel_enabled now?", "compare brain shadow vs live", "how good are the brain's shadow predictions vs reality?", or before flipping any meta-label gate from False to True.
---

# Brain shadow vs TV-live validation

## Why this skill exists

Since 2026-05-01 the brain runs in `shadow_brain=True` mode under `TV_SIGNAL.enabled=True`:
- Brain still ticks every 3 sec, runs `infer_ml`/`infer_rule`, writes to `logs/brain_shadow_predictions.jsonl`
- Brain does NOT write to MT5 signal files — only `tv_executor` (driven by webhook) does
- This is a **natural A/B test**: brain prediction at time T vs the actual outcome of any TV-driven trade entered around time T

The `metalabel_enabled` gate is OFF (`config/settings.py`) because we don't yet have data on whether the per-team meta-label model (OOF AUC 0.87-0.92 on training set) generalises to TV-source live data.

## When to invoke

- Operator asks "should I turn on `metalabel_enabled`?" — answer needs validation data
- Weekly review of brain quality vs TV signals
- After a stretch of losses, check if brain was warning against the trades
- Before flipping ANY of: `metalabel_enabled`, `metalabel_perteam_enabled`, `KELLY_SIZING.enabled`

## Core workflow

### 1. Match shadow predictions to live trades

For every closed deal in `MT5 history_deals_get(today)`:
1. Find the brain shadow prediction at deal-open-time ± 30 sec for the same symbol
2. Compare brain prediction (BUY/SELL/NONE + confidence) vs the TV-source trade direction
3. Compute metrics:
   - `agreement_rate` = trades where brain and TV agreed
   - `brain_warning_rate` = TV said BUY but brain said NONE/SELL — and the trade lost
   - `brain_confirm_value` = avg R-multiple when brain agreed minus avg R when brain disagreed

### 2. Per-team breakdown

Brain has separate models per team (METALS / FOREX / CRYPTO / COMMODITIES via `meta_label_model_*.lgb`). Validate each independently:

| Team | Live trades sample | Brain agreement % | Avg R if agree | Avg R if disagree | OOF AUC (training) |
|---|---|---|---|---|---|
| METALS (XAU) | TBD | TBD | TBD | TBD | 0.879 |
| FOREX (EUR/USD/GBP/JPY) | TBD | TBD | TBD | TBD | 0.908 |
| CRYPTO (BTC) | TBD | TBD | TBD | TBD | 0.901 |

### 3. Decision criteria for flipping `metalabel_enabled=True`

| Condition | Required for flip |
|---|---|
| Sample size | ≥ 30 closed trades over ≥ 7 trading days |
| Live agreement_rate vs brain | ≥ 0.55 (brain skip is meaningful) |
| Avg R: agree > disagree | by at least 0.20 R |
| No single-day P/L disaster | max daily loss < 5% during sample |

If all 4 hold → flip `metalabel_enabled = True` (and optionally `_perteam_enabled = True`), restart brain.

If any fails → keep gate OFF, retrain on the new data via `tools/train_v14_c1_metalabel.py`.

## Quick query commands

```cmd
:: Count shadow predictions today (sanity check brain is alive)
.venv\Scripts\python.exe -c "from pathlib import Path; import json, time; lines=Path('logs/brain_shadow_predictions.jsonl').read_text().splitlines(); cutoff=time.time()-86400; n=sum(1 for l in lines if 'mode' in l and json.loads(l).get('ts',0)>cutoff); print(f'shadow predictions last 24h: {n}')"

:: Closed trades today (TV-source)
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; from datetime import datetime, timedelta; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); deals=mt5.history_deals_get(datetime.now()-timedelta(days=1), datetime.now()) or []; closes=[d for d in deals if d.entry==1]; print(f'{len(closes)} closes today, total P/L: ${sum(d.profit for d in closes):.2f}'); mt5.shutdown()"

:: Generate the validation report (writes to reports/shadow_vs_live_<date>.json)
.venv\Scripts\python.exe tools\shadow_vs_live_report.py --days 7
```

## Project files involved

| Path | Role |
|---|---|
| `logs/brain_shadow_predictions.jsonl` | Brain's shadow predictions (62 MB+ — rotated daily) |
| `logs/tv_signals.jsonl` | TV-source signal writes (the actual trade triggers) |
| `MT5 history_deals_get` | Ground truth (R-multiples, P/L) |
| `ai_trading_agents/meta_label_model.lgb` | C1 global meta-label (loaded but gate OFF) |
| `ai_trading_agents/meta_label_model_<TEAM>.lgb` | C2 per-team (loaded but gate OFF) |
| `config/settings.py::LIVE_BRAIN::metalabel_enabled` | The gate flag |

## Anti-patterns (don't do)

- **Don't flip `metalabel_enabled=True` based on training OOF AUC alone.** Training data was 2025 historical; live regime may differ.
- **Don't compare on < 7 days.** Less than a week of TV-source data is too noisy to read agreement signals.
- **Don't use peak performance window.** A 5-day winning streak can mask the gate being net-negative on average.
- **Don't enable both `metalabel_enabled` AND `metalabel_perteam_enabled` in the same session.** Flip them one at a time, observe a week, then add the second.

## Related

- `trading-model-healthcheck` — model file integrity + feature alignment
- `trading-drift-triage` — when training/live distributions diverge
- `docs/POSTMORTEMS/2026-04-26_pre_commit_junction_breakage.md` — context on why we're so cautious about settings changes
