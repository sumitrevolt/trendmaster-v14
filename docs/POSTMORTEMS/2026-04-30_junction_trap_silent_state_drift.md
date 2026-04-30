# 2026-04-30 — Junction trap: silent state drift to C:\logs\

## TL;DR

The brain (PID 6848, started 15:43:57 IST) was writing `brain_state.json`,
`events.jsonl`, and `brain.lock` to `C:\logs\` for ~90 minutes instead of
the project's `logs/` folder. cwd was correct (`C:\Users\Ratanshila\Documents\autmated trading`).
The Python logger and shell stdout redirect went to the right place. Only the
`Path(__file__).parent.parent` callers in `state_store.py`, `event_log.py`,
and `process_lock.py` drifted — `__file__` for these modules came back as
`C:\TrendMaster_aita_canonical\<module>.py` (canonical target of the
`ai_trading_agents/` junction), so `parent.parent` landed on `C:\`.

This is a *new* manifestation of the .resolve() trap — no `.resolve()` was
called, but Windows still handed back the canonical path. Cause appears to
be how the kernel cached the path for the import-time handle, possibly
influenced by `tools\restore_junction.cmd` running just before brain start.

## Symptoms

- `diagnose_zero_trades.py` reported OK based on log freshness.
- `logs/brain_state.json` (project root) was 90+ min stale, frozen at
  `restart_count=45`, last_saved_at = 09:41:10 UTC.
- The running brain had `restart_count=1` in its in-memory state — every
  restart was effectively losing the cumulative restart counter.
- No `Could not persist brain state` warnings in the log; saves were
  succeeding, just to the wrong file.
- `C:\logs\brain_state.json` was being written every ~5s with realistic
  data (`start_of_day_equity=546.55`, live confidences).
- `cross_asset_join.py` was log-spamming `EIA_API_KEY not configured` on
  every tick × every symbol, masking actual gate-veto events.

## Diagnostic timeline

| Step | Finding |
|---|---|
| File mtime check | `C:\logs\brain_state.json` mtime moves every 5s; project-root version frozen 90 min |
| Process check | Brain PID 6848, parent chain → `start_brain_clean.cmd` from `start_trading_bot.bat` |
| `psutil.Process(6848).cwd()` | `C:\Users\Ratanshila\Documents\autmated trading` ✓ — cwd was NOT the cause |
| sys.path inspection | Clean. No canonical pollution. |
| `.pth` audit | Clean. No `TrendMaster_aita_canonical` references. |
| `.pyc` `co_filename` | Both pyc caches (junction view + canonical view) had correct `co_filename` |
| Fresh-launch probe | Reproduced the brain's launch with `python -u ai_trading_agents\trend_master_brain.py` from project root → `__file__` came back ABSOLUTE and CORRECT, did not reproduce the trap |
| Conclusion | Trap is intermittent, depends on Windows path cache state at exact moment of import. CLAUDE.md's `Path(__file__).parent.parent` rule is *necessary but not sufficient*. |

## Fix

Added junction-trap recovery to all three writers:

```python
_HERE = Path(__file__).parent
_ROOT = _HERE.parent
# Validate by looking for config/settings.py — a known project invariant.
# If absent, the trap fired; fall back to cwd which the brain launcher
# always sets to project root via `cd /d`.
if not (_ROOT / "config" / "settings.py").exists():
    _ROOT = Path.cwd()
```

Files patched:
- `ai_trading_agents/state_store.py:42-50`
- `ai_trading_agents/event_log.py:170-180`
- `ai_trading_agents/process_lock.py:33-40`

Also unrelated noise fix:
- `ai_trading_agents/cross_asset_join.py:572-579` — gated the
  `EIA_API_KEY not configured` log line with a module-level once-per-process
  flag. Was firing on every tick × every symbol.

## Migration steps performed

1. Copied wrong-path live state (`C:\logs\brain_state.json`) into
   `logs/state_backups/brain_state.<ts>.from_C_logs.json`.
2. Copied stale project-root state into
   `logs/state_backups/brain_state.<ts>.from_proj_logs.json`.
3. Wrote merged state to project-root `logs/brain_state.json`:
   - Live data (signals, equity, dates) from C:\logs\ version
   - Restart history `restart_count=45` from project-root version
4. Ran `start_brain_clean.cmd` — taskkill + clean relaunch.
5. Verified: new brain (PID 15024) writes to project-root every ~3s,
   `restart_count=46` (continued), 6/18 cleared MIN_CONF (up from 2/18
   pre-restart — model was MORE conservative when state was being lost,
   confirming state-loss was distorting confidence baseline).
6. Moved `C:\logs\*` → `logs/junction_trap_orphans_2026-04-30/` for
   forensics, removed empty `C:\logs\`.

## Verification post-restart

- `C:\logs\brain_state.json` mtime frozen ✓
- project-root `logs/brain_state.json` mtime updates every ~3s ✓
- `diagnose_zero_trades.py` → VERDICT OK, 6/18 cleared MIN_CONF
- EIA log lines in last 200: **0** (was hundreds/min)

## Lessons

1. **`Path(__file__).parent.parent` is not sufficient inside the
   `ai_trading_agents/` junction.** Even without `.resolve()`, `__file__`
   can come through canonical depending on cache state. The new pattern
   is: derive `_ROOT`, then **validate** with a known invariant
   (`config/settings.py`), and fall back to `cwd` if validation fails.
2. **`diagnose_zero_trades.py` is log-driven and missed this entirely.**
   It should also check that `brain_state.json`'s `last_saved_at` is
   within a few minutes of now. Adding this would have caught the drift
   on tick 1.
3. **Log spam can mask real signal.** The hundreds-per-minute EIA-missing
   line buried gate-veto events in the same severity (`INFO`). Any
   "missing config" warning should fire once per process, not per
   operation.
4. **Two state files = silent corruption.** When the brain came up
   without finding `C:\logs\brain_state.json`, it started fresh with
   `restart_count=1`, losing the cumulative 45-restart history. A
   pre-flight check that reads/validates the existing state file would
   catch a stale or wrong-path file.

## Follow-ups

All ALL of these were completed in the same session as the incident
(commits `e61340a` brain modules, `677a4be` pre-commit auto-heal):

- [x] Update `diagnose_zero_trades.py` to assert
  `now - last_saved_at < 120s`. Done in `e61340a` —
  STATE_STALE_AFTER_SECONDS=120, returns STATE_DRIFT verdict.
- [x] Audit other modules in `ai_trading_agents/` that compute paths via
  `Path(__file__).parent.parent` — applied to all 12 callers
  (`state_store`, `event_log`, `process_lock`, `cross_asset_join`,
  `feature_cols_v2`, `gate_value`, `market_calendar`, `news_feed`,
  `ops_maintenance`, `profit_filters`, `multi_market_dispatcher`,
  `trend_master_brain`).
- [x] Centralized project-root resolution in
  `ai_trading_agents/_paths.py::project_root()` (commit `e61340a`).
- [x] Auto-heal the pre-commit stash/restore junction breakage.
  `tools/check_junction.py` gained a `--heal` flag and a new
  `heal-junction` pre-commit hook runs at `[post-commit, post-checkout,
  post-merge]` stages (commit `677a4be`). Operator must run
  `pre-commit install --hook-type post-commit --hook-type post-checkout
  --hook-type post-merge` once.
- [x] Pre-commit framework's stash/restore "files modified by this hook"
  rollback re-broke the junction even when `heal-junction` ran. Fix:
  `.git/hooks/post-commit` was extended with a final-line direct call
  to `tools\restore_junction.cmd` AFTER pre-commit's hook-impl finishes,
  bypassing the framework's rollback. The .git/hooks file is local-only
  so fresh checkouts must restore this manually — see CLAUDE.md "Brain
  package maintenance".

Remaining (out of scope for the immediate fix):

- [ ] Rotate `cross_asset_join.py:fetch_*` calls to retry every N hours,
  not every tick — also reduces wasted CPU on the no-API-key path.
