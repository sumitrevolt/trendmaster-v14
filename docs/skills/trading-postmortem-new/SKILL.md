---
name: trading-postmortem-new
description: Scaffold a new postmortem under docs/POSTMORTEMS/ with the four trading-specific sections pre-filled from logs/brain_state.json and brain_memory.json at a named timestamp. Use when the user says "write a postmortem", "scaffold a postmortem", "post-incident review", "blameless postmortem", or after any incident — silent-failure, runaway loss, broker disconnect, halted-and-noticed-late.
---

# Trading Postmortem Scaffolder

Creates a new postmortem file under `docs/POSTMORTEMS/<date>_<slug>.md` with the four trading-specific sections pre-populated from live state at the operator-named incident timestamp. Adapts Google SRE template for live-trading context.

## When to invoke

- Operator says "write a postmortem", "post-incident review".
- After any of: silent-failure (zero trades unexpected), runaway loss (DD breach), broker disconnect >5min, model degradation noticed late, scheduled-task missed.
- Within 48h of incident resolution while context is fresh.

## The four trading-specific sections

Standard SRE postmortems have summary / impact / root-cause / action-items / timeline. Trading needs four extra:

1. **P&L impact** — realised + unrealised at incident peak, in USD and R-multiples.
2. **Position state at detection** — which symbols open, gross/net exposure, hedge offsets, SL distances.
3. **Rollback-safe time** — latest timestamp at which restoring `state_store.json` and `brain_memory.json` would NOT cause double-fills or stale orders. Critical for choosing the recovery point.
4. **Counterfactual P&L** — what would have happened if the fix had landed N hours earlier. Quantifies cost-of-delay.

Plus standard sections: TL;DR, Timeline, Root cause, What went well, What went poorly, Action items (owner+deadline+follow-up date).

## Inputs

The operator gives:

- Incident slug (e.g., `crypto_team_silent_failure`).
- Detection timestamp (e.g., `2026-04-25T14:32:00Z`).
- Resolution timestamp (optional; defaults to now).
- Brief one-line summary.

The skill then reads:

- `logs/brain_state.json` — at-or-before detection_ts (use git history if needed to recover).
- `brain_memory.json` — for the trade window.
- `logs/trend_master_brain.out` — last 200 lines around detection_ts.
- `logs/events.jsonl` — all events between detection and resolution.

## Output

Creates `docs/POSTMORTEMS/<date>_<slug>.md` with:

```markdown
# Postmortem — Crypto team silent failure

**Date**: 2026-04-25
**Severity**: SEV-2 (no $ loss, but eroded confidence in ML stack)
**Authors**: Sumit
**Status**: Draft

## TL;DR

CRYPTO team's ML model produced uniform confidence (std=0.03) for 6 hours,
suppressing all CRYPTO entries. Caught by morning model-healthcheck routine
at 09:14 local. No financial loss; opportunity cost ~3 trades.

## Timeline (UTC)

- 03:00  Brain restart picked up retrained CRYPTO model (commit a1b2c3d).
- 03:00  First inference cycle: probs returned [0.333, 0.334, 0.333] ± 0.001 across all 4 symbols.
- 09:14  trading-model-healthcheck flagged conf_std=0.03 RED on CRYPTO.
- 09:18  Operator confirmed uniform-distribution shape.
- 09:22  Degraded CRYPTO to infer_rule via ml_align guard (no commit needed — runtime override).
- 10:05  Root-caused to feature-name mismatch in retrain pipeline.
- 11:30  Hotfix landed (commit d4e5f6g); CRYPTO promoted back to ML.

## Root cause

[Describe technical root cause. For 2026-04-24-style: feature ordering changed
between training set and live brain after retrain pipeline reordered columns
without preserving feature_names_in_.]

## P&L impact

| Window | Realised | Unrealised | R-multiple |
|---|---|---|---|
| At detection | $0 | $0 | 0R (no open positions) |
| At resolution | $0 | $0 | 0R |
| Counterfactual (if caught at 03:01) | +$24 (3 trades, est) | — | +0.5R |

Conclusion: opportunity cost only. No client funds impacted.

## Position state at detection

```
gross exposure: $0  (no CRYPTO open)
other teams: METALS=2 open, FOREX=3 open, COMMODITIES=1 open
SL distance avg: 1.4 ATR
hedge offsets: none
```

## Rollback-safe time

Last safe rollback: 2026-04-25T03:00:00Z (the moment before retrain landed).
After 03:00, no new trades were entered, so any state file from 03:00 onward
is equally safe. We chose to roll forward (hotfix) rather than rollback.

## Counterfactual P&L

If trading-model-healthcheck had run at 03:30 instead of 09:14:
- Detection: +5h45m earlier
- Same resolution path (degrade → fix → re-promote)
- Estimated P&L recovery: +$20 to +$30 (3-4 CRYPTO entries)

This is the third incident where morning-only healthcheck delayed detection.
Action: schedule healthcheck every 4h (action item #3 below).

## What went well

- ml_align guard caught misalignment cleanly — fell back to infer_rule
  without raising. The guardrail itself worked exactly as designed.
- model-healthcheck skill flagged within first 1-min window of running.
- Hotfix isolated to retrain pipeline; no brain restart needed.

## What went poorly

- 6-hour detection lag because healthcheck only ran at morning routine.
- Retrain pipeline does not assert feature-name parity before saving.
  We've now added the assertion (commit e7f8a9h).

## Action items

| # | Action | Owner | Due | Follow-up date |
|---|---|---|---|---|
| 1 | Add feature-name parity assertion to retrain pipeline | Sumit | 2026-04-26 | 2026-05-03 |
| 2 | Wire model-healthcheck to scheduled task every 4h | Sumit | 2026-04-27 | 2026-05-04 |
| 3 | Add unit test reproducing the feature-mismatch failure | Sumit | 2026-04-28 | 2026-05-05 |

## Lessons

- Guardrails work, but only if monitoring frequency matches the cost-of-delay.
- Retrain pipelines are first-class production code; treat them with the same
  CI gates as the brain itself.

```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-postmortem-new\scaffold.py ^
  --slug crypto_team_silent_failure ^
  --detection 2026-04-25T14:32:00Z ^
  --summary "CRYPTO model uniform-conf shape suppressed entries for 6h"
```

The scaffold script:
1. Reads `logs/brain_state.json` (latest snapshot — use git log to recover historical).
2. Greps `logs/events.jsonl` for the detection→resolution window.
3. Pre-fills the Position State, Timeline (events log), and counterfactual sections.
4. Writes to `docs/POSTMORTEMS/<date>_<slug>.md` and opens it for editing.
5. Adds a one-line entry to `docs/POSTMORTEMS/INDEX.md`.

## Critical guardrails

- **Blameless language only.** Never name a person as "the one who broke it"; describe what the system or process allowed.
- **Pre-fill, don't fabricate.** If a value isn't in the logs, leave the field as `[fill in]`. Don't invent timestamps or P&L numbers.
- **Always include all four trading-specific sections** even if "no impact" — saying it explicitly is part of the institutional-knowledge value.

## Helper script

`scaffold.py` next to this SKILL.md. The template lives in `template.md`.

## References

- Google SRE example postmortem (sre.google/sre-book/example-postmortem).
- TrendMaster `docs/POSTMORTEMS/2026-04-24_zero_trades.md` — the 47-day silent-failure incident, structurally the model for this template.
- dastergon/postmortem-templates on GitHub.
