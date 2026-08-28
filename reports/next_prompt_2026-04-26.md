# TrendMaster Next-Prompt — 2026-04-26

**Headline:** Implement Phase B1 — extend `cross_asset_join.py` to fetch the 7 EDGE-class CFTC COT contracts + EIA NG storage delta as a *parallel* feature family (no FEATURE_COLS edit yet, no retrain) so the data plumbing is in place before we touch the brain's inference path.

## Recommended prompt

```
Implement Phase B1 of TrendMaster's smart-money flow integration: data plumbing
only, no brain inference change.

Context: Phase A2 found 8 EDGE-class source-symbol pairs (see
reports/influencer_correlation_phaseA2_2026-04-26.md). The 7 CFTC COT contracts
(GC, SI, 6E, 6J, 6C, CL, BTC) and EIA Nat-Gas storage delta have stable in/out-of-
sample edge against the corresponding TrendMaster symbols. We are NOT yet wiring
these into infer_ml or FEATURE_COLS — that's Phase B2 after walkforward
validation.

Scope of THIS session (Phase B1 only):

1. Extend ai_trading_agents/cross_asset_join.py with two new fetchers:
   - fetch_cot_weekly() — pulls CFTC Socrata legacy_fut endpoint
     (https://publicreporting.cftc.gov/resource/6dca-aqww.json) for the 7
     contracts, computes spec_delta_z = z-score of (long_managed -
     short_managed) over 52-week rolling window. Returns DataFrame indexed by
     report_date_as_yyyy_mm_dd, columns one per contract.
   - fetch_eia_ng_storage() — pulls EIA Open Data API v2 weekly NG storage
     series, computes storage_delta_z = z-score of week-over-week storage Δ
     over 52-week window. Returns DataFrame indexed by period.
   Cache responses to data/external/cot_weekly_cache.parquet and
   data/external/eia_ng_cache.parquet. Refresh stale-by-7-day rule.

2. Extend cross_asset_join.align_to_h1(symbol_h1_df) so it can OPTIONALLY
   forward-fill the COT/EIA series into the H1 frame on a new keyword arg
   include_smartmoney=False (default False to avoid changing existing behavior).

3. Write tests at tests/test_cross_asset_join_smartmoney.py covering: fresh
   fetch, cache hit, schema-drift detection (raise on missing columns),
   forward-fill correctness across a Friday 15:30 ET boundary, weekend gap
   handling.

4. DO NOT touch:
   - trend_master_brain.py (FEATURE_COLS, build_features, infer_ml, infer_rule)
   - ml_align.py
   - profit_filters.py
   - any model file (.lgb)
   - logs/brain_state.json or any other live state

5. DO NOT change MIN_CONF, gate logic, spread_guard policy, or any operator
   invariants from MEMORY.md.

6. Run pre-commit. Run pytest only on the new test file. Reply with: lines of
   code added, tests passing, the cached parquet sizes, and a short sketch of
   the Phase B2 prompt (FEATURE_COLS extension + backtest) that would follow
   this work.

Rule of the project: this module lives inside the ai_trading_agents/ junction —
NEVER use Path(__file__).resolve() inside it. Use Path(__file__).parent.parent.

Time budget: 90 minutes of agent work. If a fetcher fails on Socrata rate
limits, log and continue with cache; do not retry-forever.
```

## Why this one

Phase A2 produced numerical edge (8 EDGE pairs, OOS-validated). The natural follow-through is feature integration, but doing it in one shot — fetcher + FEATURE_COLS edit + ml_align change + retrain — is too much surface area for one session and risks a silent inference regression (the 47-day zero-trades incident was exactly that pattern). Splitting Phase B into B1 (data plumbing, isolated) and B2 (FEATURE_COLS + retrain + backtest) keeps each diff reviewable and reversible. B1 is purely additive — the new module exists, but nothing in the brain reads from it yet, so nothing breaks if B1 ships and B2 stalls. This beats triple-barrier (Open R&D #1) on feasibility, beats the walkforward schtask audit on leverage, and beats frac-diff (#2) on signal-to-effort ratio because Phase A2 already proved COT delivers usable alpha.

## Scorecard

| Candidate | Leverage | Feasibility | Urgency | Total | Notes |
|---|---|---|---|---|---|
| **Phase B1 — COT/EIA data plumbing (winner)** | 5 | 5 | 4 | 14 | Direct from Phase A2; isolated; reversible |
| Phase B (B1+B2 in one shot) | 5 | 2 | 4 | 11 | Too much surface area; FEATURE_COLS + retrain in one diff is the failure pattern that produced the 47-day silent outage |
| Triple-barrier labeling (Open R&D #1) | 5 | 2 | 3 | 10 | Foundational but multi-week; defer until B1+B2 ship |
| Frac-diff + Hurst features (Open R&D #2) | 4 | 3 | 2 | 9 | Lower marginal than COT given Phase A2 numbers |
| Walkforward schtask audit | 2 | 5 | 3 | 10 | Daily walkforward missed today; cheap to fix but low leverage |
| Restart-cluster postmortem (32 restarts) | 3 | 4 | 2 | 9 | Brain stable 14h now; not urgent |
| Decommission `trend_master_model.lgb` | 3 | 5 | 2 | 10 | Already routed around by ml_align; mostly hygiene |

## Also considered (not recommended now)

- **Phase B as a single-shot integration** — ranked second on Leverage but lost on Feasibility. The 47-day zero-trades incident (`docs/POSTMORTEMS/2026-04-24_zero_trades.md`) was exactly the failure mode of "feature + retrain + deploy in one diff." Splitting wins.
- **Walkforward schtask audit** — daily walkforward at 08:00 IST didn't fire today. Worth a 30-min poke after Phase B1 ships, not before.
- **CRYPTO ML overfit follow-up** — `tools/validate_crypto_ml.py` already documented the INSUFFICIENT_DATA verdict; rename of `trend_master_model.lgb` is operator decision (CLAUDE.md), not Claude's call.

## State snapshot used

- Brain: MODEL_UNIFORM, uptime 14.45h, restart_count=32, last_saved 2026-04-26T06:05:09Z
- Last full RD digest: 2026-04-26T05:05Z — recommendation was "monitor; nothing to do" (weekend)
- Latest reports: `phaseA2_2026-04-26.md` (08:59), `phaseA1_feasibility_2026-04-26.md` (07:44)
- Last commit: 74a00a9 "Adapt R&D digest to hourly cadence" — no brain code progress in several commits
- Open postmortem actions: 2026-04-25 god-mode consolidation + 2026-04-25 phantom-deletion (both have closed action items; no new opens)
- Walkforward: today's daily run missed (last file 2026-04-25_1150.json)
