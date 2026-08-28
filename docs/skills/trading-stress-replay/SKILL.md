---
name: trading-stress-replay
description: Replay four canonical FX/metals stress scenarios (SNB-2015 EUR/CHF unpegging, COVID-Mar-2020 vol spike, Brexit-2016 GBP gap, Aug-2015 CNY devaluation) against the current TrendMaster v14 open book and report a survive/blow verdict per scenario. Use when the user asks for "stress test", "stress replay", "would we survive", "tail risk", "VaR isn't enough", or before any change to position-cap, leverage, or per-team max-open.
---

# Trading Stress Replay

Apply a deterministic library of four canonical FX/metals shocks to the current open book and report whether the account survives each. Complements `ai_trading_agents/portfolio_risk.py` (historical/parametric/Cornish-Fisher VaR) by exercising scenarios that a 500-day rolling window does not contain.

## When to invoke

- Operator asks for "stress test", "tail risk", "would we survive X".
- Before any change to: per-team max-open, per-symbol cap, leverage, daily-DD breaker.
- Weekly review at session rollover.
- After a real-world market event in any major asset class — re-run to confirm the book still passes the historical scenarios.

## Scenarios

| Tag | Date | Shock | Symbols affected (mostly) |
|---|---|---|---|
| `snb_2015` | 2015-01-15 | EUR/CHF unpegged → -19% in 20 minutes | EURUSD, CHF crosses, XAUUSD spike |
| `covid_mar_2020` | 2020-03-09 to 2020-03-19 | Vol regime shift, USD scarcity, oil -30% | All majors, XAUUSD, XTIUSD, BTCUSD |
| `brexit_2016` | 2016-06-24 | GBP -10% gap-down on referendum result | GBPUSD, EURGBP, FTSE-correlated |
| `cny_aug_2015` | 2015-08-11 | CNY surprise devaluation, AUDUSD -3% | AUDUSD, NZDUSD, copper-correlated |

Each scenario is encoded as a JSON file in `${CLAUDE_PLUGIN_ROOT}/skills/trading-stress-replay/scenarios/` with per-symbol `pct_move`, `vol_multiplier`, and `spread_multiplier` deltas.

## Inputs

Read from the live brain state:

- `logs/brain_state.json` — open positions per symbol (symbol, side, lots, entry_px, sl_px).
- `config/risk.yaml` — `account_equity`, `daily_loss_limit`, `max_drawdown_pct`.

If brain has no open positions, emit a synthetic "what if you had max-open per team across all 4 teams" scenario instead.

## Output

Print to stdout AND save the run to `logs/stress_runs/<run_ts>.json`:

```
Stress Replay — 2026-04-25 11:23 UTC
====================================
Account equity: $5,420.00
Daily loss limit: $135.50  Max DD allowed: $812.00

Open positions: 6
  XAUUSD long  0.10 lots @ 2342.50  SL 2335.20
  EURUSD long  0.20 lots @ 1.0682   SL 1.0651
  GBPUSD short 0.15 lots @ 1.2421   SL 1.2462
  ...

Scenario verdicts
-----------------
[SURVIVE]  snb_2015         worst_pl=-$340  vs DD limit $812   (42% of limit consumed)
[SURVIVE]  cny_aug_2015     worst_pl=-$280  vs DD limit $812   (34% consumed)
[BLOW]     covid_mar_2020   worst_pl=-$1,210 vs DD limit $812   (149% — would breach DD breaker, gets force-flat'd)
[SURVIVE]  brexit_2016      worst_pl=-$610  vs DD limit $812   (75% consumed — close call)

Worst single line in worst scenario:
  covid_mar_2020 → BTCUSD -$420 (vol_mult=4.5x, no SL hit because gap)

Recommendations:
  - covid_mar_2020 would force-flat the book. Confirm DD breaker actually triggers
    and isn't paused (state.trading_paused == False).
  - brexit_2016 at 75% is uncomfortable. Consider trimming GBPUSD position size
    or tightening SL to <30 pips on GBP pairs.
  - Repeat after any change to per-team max-open.
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-stress-replay\scenarios.py --all
```

Pass `--scenario snb_2015` to run one. Pass `--synthetic-max-book` to evaluate a hypothetical 8-position book (max-open per team × 4 teams) instead of the live state.

## Critical guardrails

- **Never auto-execute a flat-the-book in response to a "BLOW" verdict.** Print the verdict, but the operator decides whether to act.
- **Honor `state.trading_paused`** — if the brain is already paused, mention it in the report so verdicts are read in context.
- **Don't conflate "BLOW" with "must reduce position"** — sometimes the right answer is "DD breaker is doing its job, no action needed".

## Helper script

`scenarios.py` next to this SKILL.md, plus the scenario JSON files in `scenarios/`.

## References

- Quantpedia VaR intro, BIS CGFS18 stress survey, FXCM SNB account.
- `references/scenario-construction.md` — how the four scenarios were calibrated from public OHLC data.
