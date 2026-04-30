# Postmortem - ai_trading_agents/ restoration + 13-skill bundle install

**Date**: 2026-04-25
**Severity**: SEV-2 (no live $ loss; live brain held by in-memory imports;
                    one restart from total-failure)
**Authors**: Sumit (with Claude assistance)
**Status**: Resolved

## TL;DR

While installing two new skill bundles (Round 1: trendmaster-quant-bundle,
Round 2: trendmaster-ops-excellence; 13 skills total), an end-to-end audit
revealed that `ai_trading_agents/` had been gutted to 2 .py files. The other
~37 modules existed only in `archive/legacy_python/` as canonical + Defender-
quarantine duplicate (`_1`, `_2`) copies. The live brain was running on
modules cached in its already-running Python process; any restart would have
failed at import time, forcing a full incident recovery during market hours.
Restoration completed without loss.

## Timeline (UTC)

- 06:34   Round 1 skill-install task begins; copies 8 skill folders into
          `docs/skills/`. Skills install fine; pycache leakage cleaned.
- 07:24   Round 2 skill-install completes; 13 new skills total in
          `docs/skills/`; both .plugin files written to repo root.
- 08:00   Comprehensive audit dispatched. Audit attempts to run 5 of the new
          helpers; finds:
            * Real bug: corr.py `resample("1H")` -> pandas 3.0 deprecation.
            * Real bug: file-name drift (`logs/deals.csv` vs `logs/trades.csv`,
              `logs/event_log.jsonl` vs `logs/events.jsonl`).
            * Cosmetic: cp1252 mojibake on em-dash / arrow chars.
            * CATASTROPHIC: `ai_trading_agents/` only contains
              `__init__.py` and `trend_master_brain.py`; ~37 modules
              imported by the brain are missing.
            * 32 pytest collection errors, all rooted in the same gutted
              package.
- 08:10   Root cause confirmed: the 2026-04-24 Defender quarantine event
          (logged in CLAUDE.md and project_v14_round11_zero_trades_fix
          memory) moved files to `archive/legacy_python/` and Defender
          quarantine-restore created `_1` and `_2` byte-identical duplicates.
          The post-quarantine restoration of canonical (no-suffix) files
          back to `ai_trading_agents/` was never completed.
- 08:12   Restoration script written and run via PowerShell. 37 canonical
          modules copied from `archive/legacy_python/<mod>.py` to
          `ai_trading_agents/<mod>.py`. None overwrite existing files.
- 08:14   Smoke import test: 35/37 OK; brain top-level import OK.
          The 2 failures (`geopolitical_agent`, `institutional_agents`)
          need `aiohttp` and are not on the live brain import path.
- 08:18   Sweep script fixed `1H` -> `1h` in tb_labeler.py, ASCII-folded
          em-dash and arrow chars across 14 helpers, aligned filenames
          (`deals.csv`->`trades.csv`, `event_log.jsonl`->`events.jsonl`),
          inserted UTF-8 stdout reconfiguration preamble.
- 08:20   Created missing dirs (`data/cross_asset/`, `ml_models/_candidates/`,
          `ml_models/_archive/`, `logs/correlation_history/` etc.), seeded
          `logs/heartbeat.txt`, `logs/drift_alerts.jsonl`,
          `logs/signal_history.jsonl`, copied `cross_asset_join.py` into
          `ai_trading_agents/`, created `docs/POSTMORTEMS/INDEX.md`.
- 08:25   Re-verification: 9 representative skill helpers run cleanly with
          sensible output. brain top-level import still green.

## Root cause

Two failures stacked:

1. The 2026-04-24 Defender quarantine moved the `ai_trading_agents/` modules
   to `archive/legacy_python/`. Quarantine-restore created `_1`, `_2`
   byte-identical duplicates as a Defender artifact (Windows behavior).
2. The cleanup that should have copied the canonical `<mod>.py` files
   (no `_1`/`_2`) back into `ai_trading_agents/` was missed during the
   incident recovery. The brain stayed alive on cached imports, masking
   the gap.

This was invisible until something restarted the brain - which the new
trading-brain-restart skill explicitly does as part of its workflow.

## P&L impact

| Window | Realised | Unrealised | R-multiple |
|---|---|---|---|
| At detection | $0 | $0 | 0R (no open positions) |
| At resolution | $0 | $0 | 0R |
| Counterfactual (if first restart had occurred during gap) | -$? | broker-side | full incident triage cost |

No live financial loss. The counterfactual is non-trivial: a restart would
have failed at import, brain process would die, MT5 connection would go
stale, scheduled tasks would log heartbeat-loss alarms. Recovery during
market hours (with positions open) would mean either manual close-out via
broker UI (per trading-broker-failover Mode B) or restoration-then-restart
(15-30 minutes minimum).

## Position state at detection

```
0 open positions across all teams
state.trading_paused: unknown (not set in test brain_state.json)
recent trades: 1 deal in last 6 weeks (ETHUSD 2026-04-17, -$0.69)
gross exposure: $0
```

Detection occurred during a quiet window with no positions, which is the
best possible time to find this class of failure.

## Rollback-safe time

Last safe rollback: any time. Restoration was additive (copy from archive
to active path); no destructive operations. If the brain had been restarted
mid-restore and failed, the simplest recovery would be: re-run the restore
script from `archive/legacy_python/`.

## Counterfactual P&L

If the audit had not run today and the brain had been restarted any time
in the next week:

- Detection: at the moment of restart failure (likely operator-driven,
  during a config change or scheduled-task event).
- Recovery: 15-30 minutes assuming archive is consulted. Possibly hours
  if Defender quarantine root cause is rediscovered from scratch.
- Cost: if positions were open at restart time, mode-B broker-failover
  (close via web UI) would avoid loss but interrupt strategy.

Estimated cost of detect-late: opportunity cost of 1-2 trading sessions
(~$20-60 at current trade frequency) + operator time.

## What went well

- The brain's in-memory cache held imports stable; no live trading impact.
- The audit subagent correctly identified the gutted package as the
  catastrophic finding rather than a noisy false positive.
- Archive contained byte-perfect canonical copies of every needed module.
- Restoration was deterministic and verifiable via import smoke test.
- All 13 new skills' bugs (one real - pandas 3.0; many cosmetic - mojibake)
  were swept in one pass.

## What went poorly

- The 2026-04-24 Defender incident memory entry did not specify which
  files were affected or whether restoration was complete. Future
  postmortems must enumerate affected files explicitly.
- pytest collection errors (32 of them, all caused by the gutted package)
  were silent because no CI/scheduled-task ran pytest. Quarantine-class
  incidents are exactly when CI is most needed.
- The new skills' filename references (deals.csv, event_log.jsonl) drifted
  from reality (trades.csv, events.jsonl) because I authored them from the
  CLAUDE.md spec instead of from the live `logs/` directory listing.
- One of the new skills (trading-correlation-monitor) shipped with a
  pandas 3.0 deprecation that would break on every non-trivial run; should
  have been caught in the original verification pass.

## Action items

| # | Action | Owner | Due | Follow-up date |
|---|---|---|---|---|
| 1 | Add a CI/scheduled-task that runs `pytest --co -q` daily and pages on collection errors. The 32 silent failures here would have been caught. | Sumit | 2026-05-02 | 2026-05-09 |
| 2 | Add a single import-smoke test (`python -c "import ai_trading_agents.trend_master_brain"`) to start_brain_clean.cmd so a missing module is caught BEFORE state changes happen. | Sumit | 2026-04-27 | 2026-05-04 |
| 3 | Audit `archive/legacy_python/` for any other canonical modules not yet restored. Consider a one-time cleanup script that promotes canonical versions and deletes `_1`/`_2` Defender residue. | Sumit | 2026-05-02 | 2026-05-16 |
| 4 | Configure Defender exclusion explicitly for `ai_trading_agents/` AND `archive/` (so future quarantines stop creating mixed-state directories). Document in DEPLOY runbook. | Sumit | 2026-04-30 | 2026-05-07 |
| 5 | Re-author the file-name references in trading-tca-daily, trading-cost-attribution, trading-postmortem-new SKILL.md to match reality (not CLAUDE.md spec). Already done in helpers; SKILL.md still mentions old names. | Sumit | 2026-04-30 | 2026-05-07 |
| 6 | Add `aiohttp` to `requirements.txt` if `geopolitical_agent` and `institutional_agents` are still in the active brain path. If they are legacy-only, move them to `archive/legacy_python/` explicitly. | Sumit | 2026-05-09 | 2026-05-16 |
| 7 | events.jsonl is 127 MB. Add a rotation policy (e.g., daily rotate; keep 7 days). trading-schtasks-audit could own the rotation task. | Sumit | 2026-05-02 | 2026-05-09 |

## Lessons

- A live trading system that boots from disk every time is more honest than
  one whose process state is hidden by long-running daemons. An in-memory
  cache that keeps the brain alive can mask weeks of disk-state drift.
- "Trades on rules > trades on broken ML > no trades" should be extended:
  "Trades on disk-loaded brain > trades on memory-cached zombie > no trades."
  A daily forced-restart-on-fresh-disk would expose this class of failure
  in <24h instead of weeks.
- Defender quarantine creates mixed-state directories that the operator
  must explicitly clean up. A `_1`/`_2` suffix is a permanent flag for
  "needs reconciliation" - codify a check.
- New skill helpers must be smoke-tested against the actual filesystem
  layout, not the documented one. CLAUDE.md describes intent; `logs/` and
  `data/` describe reality. Reality wins.
