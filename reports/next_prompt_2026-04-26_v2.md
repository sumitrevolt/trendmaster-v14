# TrendMaster Next-Prompt — 2026-04-26 (v2)

**Headline:** Phase B2-research — train a *shadow* model with the new COT+EIA features, walkforward against baseline, output a numerical PROMOTE/DROP verdict — without touching the live `FEATURE_COLS`, the live model file, or any inference path. Bundle a preflight fix for the broken daily walkforward schtask into the same prompt because the lab tool is the gating dependency.

## Recommended prompt

```
Implement Phase B2-research of TrendMaster's smart-money flow integration:
shadow walkforward only, no live brain change.

Context: Phase B1 (commit 862077b) added ai_trading_agents/cross_asset_join.py
with fetch_cot_weekly + fetch_eia_ng_storage + align_to_h1, all gated behind
include_smartmoney=False. No code in the brain currently consumes them.
Phase A2 (reports/influencer_correlation_phaseA2_2026-04-26.md) found 7
EDGE-class CFTC COT contracts (GC, SI, 6E, 6J, 6C, CL, BTC) plus EIA NG
storage delta as the alpha-bearing pairs.

This prompt does NOT touch trend_master_brain.py FEATURE_COLS, infer_ml,
the live trend_master_model.lgb, ml_align.py, or any gate. Phase B2-deploy
(actually changing live behavior) is a separate prompt that follows ONLY
if this research session reports PROMOTE.

Step 0 — preflight (~10 min): the daily walkforward schtask
("TrendMaster Walkforward Lab") has not produced a new file since
2026-04-25_1150.json — verified at 2026-04-26 11:39 UTC. Diagnose:

  - Run `schtasks /query /tn "TrendMaster Walkforward Lab" /fo LIST /v` and
    paste the LastResult / NextRunTime / LastRunTime into the report.
  - Run `python tools/walkforward_lab.py --symbol all` once manually and
    confirm it completes without exception. If it errors, that's
    probably why the schtask "ran" but produced no output. Capture the
    traceback.
  - If the issue is fixable in <15 min (path, missing dep, cmd-wrapper
    quoting), fix it and document. If not, write a one-line
    recommendation in the report and move on. Do NOT block Step 1 on
    this — Step 1 can use the lab tool directly even if the schtask is
    bust.

Step 1 — shadow feature column extension (~20 min):

  - Create a new module ai_trading_agents/feature_cols_v2.py (or a
    constant inside an existing R&D file — your call, but keep it
    SEPARATE from the canonical FEATURE_COLS list in trend_master_brain.py).
    Define:
      FEATURE_COLS_V2 = FEATURE_COLS + [
          "GC_spec_delta_z", "SI_spec_delta_z",
          "6E_spec_delta_z", "6J_spec_delta_z",
          "6C_spec_delta_z", "CL_spec_delta_z",
          "BTC_spec_delta_z",
          "ng_storage_delta_z",
      ]
  - In the same module, expose a build_features_v2(df_h1) wrapper that
    calls the existing build_features() then joins via
    cross_asset_join.align_to_h1(df, include_smartmoney=True).
  - This module is NEVER imported by trend_master_brain.py. Verify with
    a `grep -r "feature_cols_v2" ai_trading_agents/trend_master_brain.py`
    that returns empty.

Step 2 — extend tools/walkforward_lab.py (~30 min):

  - Add a CLI flag --feature-set {v1,v2} (default v1 = unchanged
    behavior).
  - When --feature-set v2: call build_features_v2 instead of
    build_features. Train models with the larger feature set. Save the
    walkforward output to a new path
    reports/walkforward/2026-04-26_v2_<symbol>.json so it doesn't
    collide with the v1 baseline.
  - For each symbol, write both v1 and v2 walkforward results (same
    folds, same hyper-params, same seed) so the only difference is
    feature set. This is the controlled experiment.

Step 3 — produce numerical comparison report (~15 min):

  - Write reports/phaseB2_research_<UTC-DATE>.md with:
    - Per-symbol: v1 expectancy_R, v2 expectancy_R, delta, win-rate
      delta, max-DD delta, OOS purged-CV acc delta. Use a markdown
      table.
    - Per-team aggregate (METALS / FOREX / CRYPTO / COMMODITIES):
      mean delta and number of symbols where v2 strictly improved.
    - Verdict per team: PROMOTE if mean delta-expectancy ≥ +0.05 AND
      ≥ 60% of symbols improved AND OOS-acc delta ≥ +0.005;
      RESEARCH MORE if delta is mixed; DROP if v2 is worse on average.
    - Overall recommendation (single line).
    - Caveats: cross_asset_join uses live network, so the cot/eia
      caches must be populated first. If your test environment has no
      network, populate cache from canned synthetic data and flag the
      result as illustrative only.

Step 4 — commit (~5 min):

  - Stage only: ai_trading_agents/feature_cols_v2.py (new),
    tools/walkforward_lab.py (modified), reports/phaseB2_research_*.md,
    reports/walkforward/2026-04-26_v2_*.json, plus any preflight fixes.
  - DO NOT stage: trend_master_brain.py, ml_align.py, profit_filters.py,
    any *.lgb, logs/*, brain_memory.json, brain_state.json.
  - Commit message: "feat(research): Phase B2-research walkforward
    comparison v1 vs v2 (COT+EIA) — see report for verdict"
  - If the research verdict is PROMOTE: also draft (don't send) the
    Phase B2-deploy prompt for the operator's approval, save to
    reports/next_prompt_phase_b2_deploy.md.

Hard rules:
  1. ZERO edits inside ai_trading_agents/ except the new
     feature_cols_v2.py module. Verify with git diff --stat before
     commit.
  2. Junction-aware: any new file inside ai_trading_agents/ MUST use
     Path(__file__).parent.parent (NEVER .resolve()). Tests can use
     .resolve().
  3. If walkforward_lab.py errors out and the fix is non-trivial,
     STOP and report. Don't paper over it with try/except.
  4. Do not retrain trend_master_model.lgb. Shadow models stay in
     reports/walkforward/ artifacts.
  5. Pre-commit must pass. The new check_junction.py hook will run.
  6. Time budget 90 min. If Step 2 isn't done in 45 min, simplify the
     CLI plumbing or commit Step 1 alone with a TODO.
```

## Why this one

Phase B1 shipped clean. The natural next step is "do something with the new module," but doing live `FEATURE_COLS` + retrain + deploy in one diff is exactly the failure pattern that produced the 47-day silent zero-trades incident. Phase B2-research is the *measured* version: a controlled walkforward experiment comparing v1 vs v2 features, no live state change, output is a numerical PROMOTE/DROP verdict that gates Phase B2-deploy. Bundling the walkforward schtask audit into Step 0 is leverage-positive — the schtask has been silently broken for 9+ hours (latest WF is `2026-04-25_1150.json`, current time 2026-04-26 11:39 UTC, schtask should have fired ~02:30 UTC), and Phase B2-research depends on that exact tool. Two birds, one preflight.

## Scorecard

| Candidate | Leverage | Feasibility | Urgency | Total | Notes |
|---|---|---|---|---|---|
| **Phase B2-research + walkforward preflight (winner)** | 5 | 4 | 4 | 13 | Bundles WF audit + research gate; no live brain risk |
| Daily walkforward schtask audit alone | 3 | 5 | 5 | 13 | Tied on score but covered as Step 0 of the winner |
| Phase B2 full deploy (FEATURE_COLS + retrain + ship) | 5 | 2 | 3 | 10 | High surface area; the deliberately-split half |
| Schedule COT+EIA cache refresh schtask | 3 | 5 | 2 | 10 | Premature — no consumer until B2 ships |
| Triple-barrier labeling (Open R&D #1) | 5 | 2 | 3 | 10 | Multi-week, doesn't fit one session |
| Restart cluster postmortem (32 restarts) | 3 | 4 | 2 | 9 | Brain stable 19h+ now |
| Memory/CLAUDE.md consolidation | 2 | 4 | 2 | 8 | Just got updated in 4bee6fc |

Tie-break: Phase B2-research wins over standalone WF audit because the audit is fully covered as Step 0 of B2-research, so picking B2-research delivers both at no marginal cost.

## Also considered (not recommended now)

- **Salvage Farside ETF flows via a different source** — Phase A2 dropped Farside because Cloudflare blocked the scrape; the AUM-diff proxy sign-flipped OOS. Worth one R&D session to try ETF.com, theblock.co, or yfinance institutional flows, but lower expected ROI than B2-research given COT alone gives 7 EDGE pairs.
- **Sunday open pre-flight check** — Sunday FX open is ~22:00 UTC; brain has been up 19h+ without restart. Probably fine, low effort to verify but low information value.

## State snapshot used

- Brain: MODEL_UNIFORM, uptime ~20h, restart_count=32, weekend mode (only BTCUSD/ETHUSD ticking, both conf <0.36)
- Latest commits: `4bee6fc` (junction guard), `862077b` (Phase B1)
- Latest reports (today): Phase A1, Phase A2, next_prompt v1, junction postmortem
- Walkforward: today's daily run **NOT FIRED** — latest is `2026-04-25_1150.json` from 24+ hours ago (escalates to Step 0 preflight in the prompt)
- Heartbeats since last full digest: 06:05, 07:05, 08:05, 09:04, 10:05 UTC — all `no_change verdict=MODEL_UNIFORM`
- Open postmortem actions: pre-commit/junction breakage RESOLVED in `4bee6fc` (postmortem documents the resolution, no open items)
