# Postmortem - god-mode round 2 consolidation

**Date**: 2026-04-25
**Severity**: SEV-3 (no live $ loss; cleanup of accumulated tech debt)
**Authors**: Sumit (with Claude assistance)
**Status**: Resolved

## TL;DR

After the phantom-deletion incident was resolved (junction architecture
+ `.resolve()` trap fix), a clean-state audit found one P0 latent bug
plus a pile of operational debt that the earlier deletion phenomena
had been masking. All items addressed in a single sweep. Test suite
remains 100% pass (487 tests, 0 fail, 0 error). Project now has a
daily pytest CI sentinel and a hardened brain pre-flight check.

## What was found and fixed

### P0 — Latent bug

| File | Line | Issue | Fix |
|---|---|---|---|
| `tools/cleanup_project.py` | 137 | `deleted += 1` and `moved += 1` referenced module-level names without `global` declaration → `F823` undefined-local at runtime if `main()` ever ran | Added `global moved, deleted` at top of `main()` |

This script had likely been broken since it was first written; nobody
noticed because nobody ran it. Found via static-analysis pass.

### P1 — Operational risk

| Item | State before | State after |
|---|---|---|
| Stale `.git/index.lock` | 0-byte file from 12:35 today, blocks all commits | Removed (3.0 h stale) |
| `logs/events.jsonl` | 121.5 MB (127 with day's growth), `vacuum_events` was dead code | Rotated to `events.jsonl.2026-04-25`; new empty `events.jsonl` ready for live writes |
| `requirements.txt` | Missing `fastapi`, `uvicorn`, `httpx`, `websockets` — fresh-clone install of dashboard would fail | All five added with realistic version pins |
| `start_brain_clean.cmd` | No pre-flight check; restart could blindly proceed even if brain package is broken | Added pre-flight that verifies (a) `C:\TrendMaster_aita_canonical\` exists, (b) `import ai_trading_agents.trend_master_brain` succeeds. Refuses to start otherwise |
| `archive/legacy_python/` | 342 byte-identical `_1`/`_2`/`_3`/`_4` Defender quarantine residue files cluttering search/grep | 334 files moved to `archive/_to_delete_pending_review/` for operator review |

### P2 — Hygiene

| Item | Fix |
|---|---|
| `institutional_agents.py:857` W293 (whitespace on blank line) | Cleaned |
| Skill prose drift: `trading-cost-attribution/SKILL.md`, `trading-tca-daily/SKILL.md` mentioned `logs/deals.csv` (real file is `trades.csv`) | Both updated |
| Skill prose drift: `trading-postmortem-new/SKILL.md` mentioned `logs/event_log.jsonl` (real file is `events.jsonl`) | Updated |
| No daily pytest health check | New scheduled task `TrendMaster Pytest Health Check` registered, runs daily 09:05, writes to `logs/pytest_health.log`, drops `logs/pytest_health.alert` on collection error |

### P3 — Verified clean

| Check | Result |
|---|---|
| Junction `ai_trading_agents/` → `C:\TrendMaster_aita_canonical\` | Healthy (39 .py + ml_models/ + brain + __init__) |
| `.resolve()` calls in `ai_trading_agents/` | Zero (all 6 affected files fixed by user earlier) |
| Brain log uncaught exceptions in last 24h | Zero |
| pytest run after all fixes | 487 tests, all dots, no F or E |

## P&L impact

Zero. None of these issues had reached the live trading path — they
were either latent bugs (cleanup_project.py, requirements gaps),
hygiene (whitespace, prose drift), or operational tooling that was
missing rather than wrong.

## Position state at fix-time

```
brain process: PID 23940 cmd.exe (launcher) + python.exe child
open positions: per stale brain_memory.json — likely 0 (weekend)
trading_paused: unknown (state.json not inspected)
markets: closed (Saturday 2026-04-25 ~15:35 IST)
```

## Rollback-safe time

Any point. All changes were additive (added pre-flight, added
requirements lines, added schtask) or deferred-destructive (duplicates
moved to a quarantine folder, not deleted). Nothing the brain reads
at tick time was modified.

## What ONLY required operator action

The phantom-deletion incident itself (yesterday's postmortem) was
resolved by the operator with the junction approach and the
`.resolve()` trap fix. This round 2 consolidation built on that
stable foundation; no operator action required for any of round 2's
fixes.

## What went well

- Clean-state audit immediately surfaced the latent F823 in
  cleanup_project.py — exactly the kind of bug that hides until
  someone runs the script in anger.
- The 342-file Defender residue cleanup, deferred for weeks because
  the deletion phenomenon was scarier, took 6 seconds to execute once
  the deletion was off the table.
- Adding the pre-flight check to `start_brain_clean.cmd` directly
  addresses the silent-failure shape from the 2026-04-24 zero-trades
  incident; future restarts will fail loudly rather than degrade
  silently.

## What went poorly

- The W293 whitespace and the F823 latent bug should have been
  caught by ruff in pre-commit. Pre-commit was either skipped or the
  hook is broken. Worth a separate audit of whether
  `.pre-commit-config.yaml` actually runs on commit.
- 121 MB of `events.jsonl` accumulated because nobody ever wired
  `vacuum_events` into the brain's daily loop. Function-defined-not-
  called is its own anti-pattern; should be detected by a "dead
  code" linter in CI.

## Action items

| # | Action | Owner | Due | Follow-up |
|---|---|---|---|---|
| 1 | Verify pre-commit hooks actually run on commit (esp. ruff) | Sumit | 2026-05-02 | 2026-05-09 |
| 2 | Add an alert/page mechanism for `pytest_health.alert` (currently a quiet file drop) — wire to Telegram | Sumit | 2026-05-02 | 2026-05-09 |
| 3 | Wire `ops_maintenance.vacuum_events` into the brain's daily loop so events.jsonl rotation is automatic | Sumit | 2026-05-09 | 2026-05-16 |
| 4 | Review `archive/_to_delete_pending_review/` (334 files); operator hard-deletes once confirmed safe | Sumit | 2026-05-09 | 2026-05-16 |
| 5 | Install `psutil` so brain.pid liveness check works without falling back to "operator should check Task Manager" | Sumit | 2026-05-02 | 2026-05-09 |
| 6 | Audit other module-level state mutated without `global` declaration (vulture/pyflakes pass over ai_trading_agents/) | Sumit | 2026-05-09 | 2026-05-23 |

## Lessons

- Static analysis is a cheap, deterministic guard against the
  "function-only-runs-rarely-and-silently-broken" failure mode. Ship
  ruff in CI even if the codebase has historically passed without it.
- `function defined but never called` (vacuum_events) should be
  treated as a real defect, not a placeholder. If it's not called,
  either call it or delete it.
- A pre-flight check is cheaper than diagnosing a bad start. Add
  pre-flight to every script that mutates state.
- Quarantining is safer than deleting when in doubt. The 334 duplicate
  files cost ~30 KB of disk; the deferred review costs nothing
  meaningful.

## Related postmortems

- 2026-04-24_zero_trades.md — original silent-failure incident
- 2026-04-25_aita_restore_and_skill_install.md — prior restoration attempt
- 2026-04-25_phantom_deletion_incident.md — the deletion saga + resolution
