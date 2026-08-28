---
name: trading-cost-attribution
description: Decompose TrendMaster v14's weekly P&L into spread cost, commission, slippage, and pure alpha — answers the only question that matters for a live bot: is the alpha real, or is it being eaten by costs? Use when the user asks "P&L decomposition", "cost attribution", "where did my P&L go", "is my alpha real", "spread cost vs alpha", or after any week with worse-than-expected returns.
---

# Trading Cost Attribution

A weekly +$30 net could be +$80 alpha minus $50 spread, or +$35 alpha minus $5 spread. Those two stories suggest opposite next moves. This skill produces the decomposition.

## When to invoke

- Weekly review (Sunday before market open is canonical).
- After any week where net P&L diverges from backtest expectations by >1σ.
- Before any decision to widen TP/SL or trim trade frequency.
- Quarterly cost-vs-alpha trend review.

## The decomposition

```
Net P&L = Gross alpha − spread cost − commission − realized slippage − financing/swap
```

Each term computed from `brain_memory.json::trade_history[]` joined with `logs/trades.csv` and `logs/signal_history.jsonl` (same data sources as `trading-tca-daily`).

**Definitions:**
- **Gross alpha** — what the trade would have made at mid-price with zero slip, computed as `(close_at_exit − entry_intent_px) × side × notional`.
- **Spread cost** — half-spread paid at entry + half-spread paid at exit, summed over all trades.
- **Commission** — broker schedule (OctaFX-Demo: ~$3 / lot round-turn for FX, varies for metals/crypto).
- **Realized slippage** — `(fill_px − intent_px) × side × notional`. Different from spread cost; this is execution-quality cost.
- **Financing/swap** — overnight rollover charges; from MT5 deal history `type == swap`.

## Output

```
Cost Attribution — Week of 2026-04-19 to 2026-04-25
====================================================

Net P&L:                        +$48.20

Decomposition:
  Gross alpha (mid-price PnL): +$162.40
  Spread cost:                  -$74.20    (45.7% of gross alpha)  <-- HIGH
  Commission:                   -$28.10
  Realized slippage:            -$11.90
  Financing/swap:                +$0.00

  Reconciliation check:        +$48.20  (matches net within $0.10)

Per-team:
  METALS    gross +$84   spread -$22   slip -$3   net +$59  (alpha-dominant)
  FOREX     gross +$71   spread -$31   slip -$5   net +$35  (balanced)
  CRYPTO    gross +$8    spread -$15   slip -$3   net -$10  (cost-dominant)  <-- ALERT
  COMMOD    gross -$1    spread -$6    slip -$1   net -$8

Per-symbol top cost-eaters (spread+slip / gross alpha):
  XRPUSD   spread+slip = 240% of gross alpha   <-- TOXIC PAIR
  USDCAD   spread+slip = 88% of gross alpha    <-- watch
  XAUUSD   spread+slip = 19% of gross alpha    healthy

Trend vs trailing 4 weeks:
  Net P&L:        +$48 vs $52 avg     (-7%)
  Gross alpha:    +$162 vs $145 avg   (+12%)  <-- alpha rising
  Total cost:     -$114 vs $93 avg    (+22%)  <-- cost rising faster than alpha
  Net margin:     30% vs 36% avg      (-6pp)

Recommendations:
  - CRYPTO net is negative for the 2nd week running with cost > alpha.
    Consider running trading-walkforward-promotion to validate current model;
    if it fails ECE gate, drop CRYPTO trade frequency or skip until retrained.
  - XRPUSD shows 240% cost-to-alpha ratio. Recommend adding to the
    per-symbol skip list until spread regime improves (use trading-spread-regime
    in trading-tca-daily for context).
  - Total cost up 22% week-over-week with same trade count = spreads widened.
    Cross-reference with trading-tca-daily to confirm session-level drift.
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-cost-attribution\attribution.py --week current
```

Pass `--week 2026-W17` for a specific ISO week. Pass `--per-symbol` to print every symbol, not just the top cost-eaters. Pass `--lookback 12` to compute the trailing-12-week trend.

## Critical guardrails

- **Demo broker caveat** — OctaFX-Demo cost numbers are approximate. Use this report for *relative* cost ranking across symbols and *trend* over time, not for absolute targets.
- **Don't recommend "trade more aggressively to dilute fixed costs".** Cost-per-trade is fixed; trading more only multiplies it.
- **A negative-net symbol is not automatically a skip.** If gross alpha is positive and cost is high, the right answer might be tighter SL or wider TP — both increase R:R without raising risk. The skill says "consider", not "do".
- **Always reconcile decomposition to net P&L within $0.10.** A reconciliation gap means a missing cost component (most often: financing/swap on weekend-held positions).

## Helper script

`attribution.py` next to this SKILL.md.

## References

- BIS FX execution algos report (decomposition methodology).
- LSEG TCA framework — spread/slippage separation conventions.
- OctaFX commission schedule (verify against latest broker doc).
