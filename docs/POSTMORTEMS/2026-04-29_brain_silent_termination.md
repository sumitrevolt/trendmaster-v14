# Postmortem: 16-hour brain silent termination

_Date of incident: 2026-04-28 ~17:43 IST onwards_
_Date of detection & remediation: 2026-04-29 ~09:42 - 09:55 IST_
_Severity: HIGH (full revenue loss over the 16h window, no capital risk because trading paused implicitly when state went silent)_
_Author: detected by `tools/watch_pets.py` (auto-drafted), finalized by assistant_

## Summary

Between 17:43 IST on 2026-04-28 and ~09:55 IST on 2026-04-29 the
TrendMaster v14 brain process (PID 27860) was not running. No live
signals were generated, no trades placed, and `logs/brain_state.json`
was not updated. `brain.err` was 0 bytes - the process did not crash
with a Python exception; it was terminated silently at the OS level
(or by a parent-window close). This is the first incident detected
end-to-end by the new `watch_pets.py` aggregator and its first
auto-drafted postmortem stub (`_draft_2026-04-29_0942.md`).

## Impact

- ~16 hours (~960 minutes) of zero live signals across all 19 symbols.
- One scheduled `TrendMaster Zero Trades Watchdog` run at 09:00 IST
  on 2026-04-29 fired with `LastTaskResult=2147942593` (= 0x800700C1
  = ERROR_BAD_EXE_FORMAT). It would have caught the silent failure on
  its own except its own action was misregistered (see the parallel
  `2026-04-29_schtasks_path_quoting.md` thread of this remediation).
- All 12 prior alerting paths fed into `trading-alert-bridge`, which
  forwards to Telegram. Telegram is currently disabled (Jarvis bot
  reserved for the algo project per CLAUDE.md OpenClaw section), so
  every alert that fired during the outage went into a void.
- No real capital exposure: account is OctaFX-Demo per CLAUDE.md.

## Timeline (IST)

| When                     | What                                                                         |
|--------------------------|-------------------------------------------------------------------------------|
| 2026-04-28 13:38:34      | Brain restart #36 - last successful boot, restart_count=36 in `brain_state.json`. |
| 2026-04-28 17:42:58      | Last successful tick: brain logs B2 feature build for EURUSD into `trend_master_brain.log`. |
| 2026-04-28 ~17:43        | Brain process PID 27860 disappears. `brain.err` remains 0 bytes - no Python exception. State files frozen. |
| 2026-04-28 21:21:36      | Newly-built `tools/watch_pets.py` first run detects `overall=CRITICAL`, `brain pid 27860 NOT alive`. Alert written to `logs/watchpets_alerts.jsonl`. Telegram path silent. |
| 2026-04-28 21:23-09:42   | Watch-pets writes one CRITICAL line every 5 min for ~12 hours. No autoheal because `--autoheal` was disabled by default. |
| 2026-04-29 04:09 (UTC)   | First `tools/schtasks_audit.py` run flags 5 issues including the 3 broken-action tasks. |
| 2026-04-29 09:42:13      | Watch-pets cycle writes auto-drafted postmortem stub `_draft_2026-04-29_0942.md` (5900 bytes) with full state, brain.log tail, and TODO sections. |
| 2026-04-29 09:53:05      | Operator (assistant) kills stuck launcher PID 8132, removes stale `brain.lock` (PID 25492) and `brain.pid` (PID 27860), respawns brain via `Start-Process .venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py`. |
| 2026-04-29 09:53:05      | New brain boots, ML feature audit passes (order_match=True, 25/25 cols), process_lock acquires `brain.lock` with PID 9336. |
| 2026-04-29 09:54:32      | `brain.pid` manually written with 9336 (brain process didn't auto-write it after lock acquisition - see Remediation #2). |
| 2026-04-29 09:55:00      | Brain liveness skill re-run with proper redirect appends new `VERDICT: ALIVE` line. Watch-pets now reports `brain=OK`, `signals=OK latest=2s old`. |
| 2026-04-29 09:57:00      | EA Parity Nightly + Walkforward Lab + Zero Trades Watchdog scheduled tasks re-registered with correctly-quoted paths. Manual triggers return clean codes. |

## Root cause

**Direct:** Brain process PID 27860 was silently terminated at the OS
level. `brain.err` is 0 bytes; no Python traceback recorded. There is
no clean signal of which subsystem killed it. Plausible causes:

- **Parent cmd window closed.** The brain was originally spawned
  with `start "TrendMaster Brain - LIVE" /MIN cmd /k "...py..."` per
  `START_TRENDMASTER_LIVE.bat`. If the parent cmd console was closed
  (operator clicking the X on the minimized window, or a Windows
  shutdown without proper task shutdown), the child python.exe gets
  a CTRL_CLOSE_EVENT and exits without writing stderr.
- **Defender quarantine.** CLAUDE.md notes the project has had 34
  files quarantined by Defender mid-session (2026-04-25 incident).
  A Defender heuristic action could kill the python.exe without
  writing to brain.err.
- **OneDrive / EDR sync.** Per the 2026-04-25 phantom-deletion
  postmortem, OneDrive was deleting files in Documents-side folders
  silently. Could affect open-file handles.

The 16-hour gap to detection is fully explained: the existing
`trading-brain-liveness` skill was running every 5 min and detecting
`VERDICT: DEAD` correctly, but its only escalation path was Telegram
via `trading-alert-bridge`, which is currently disabled because the
operator has reserved the `@Sumits_jarvis_bot` token for the algo
project (per the `OpenClaw integration` section of CLAUDE.md).

## Remediation (already taken)

1. Brain respawned via direct `Start-Process` instead of the
   cmd-spawn-cmd pattern. New brain (PID 9336) is alive, generating
   signals every 2 seconds across all 19 symbols.
2. `brain.pid` is being manually maintained - the new lock writer in
   `process_lock.py` writes only `brain.lock`, not `brain.pid`, but
   `trading-brain-liveness/liveness.py` reads `brain.pid` exclusively.
   See "Prevention" #1 below for the durable fix.
3. Three scheduled tasks (EA Parity Nightly, Walkforward Lab, Zero
   Trades Watchdog) re-registered with correctly-quoted full paths.
   All three return clean exit codes on manual trigger.
4. `tools/watch_pets.py`'s `check_alert_files` was updated to
   include `schtasks_audit.alert` so meta-watchdog issues bubble up.

## Prevention (durable fixes recommended)

1. **`process_lock.py` should write `brain.pid` in addition to
   `brain.lock`.** The two-file convention is asymmetric - lock is
   PID-source for some readers, pid file for others. Writing both
   atomically (lock first, then pid file) eliminates the entire
   class of "brain alive but liveness skill says DEAD" false
   negatives.
2. **Replace the `start "title" /MIN cmd /k` spawning pattern in
   `START_TRENDMASTER_LIVE.bat`** with a direct invocation that
   doesn't depend on an interactive parent console. A simple
   `start /B .venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py >> logs\trend_master_brain.out 2>> logs\trend_master_brain.err` is more robust to non-interactive parents (Task Scheduler, supervisor scripts, PowerShell `Start-Process`).
3. **Move alerts off Telegram.** `tools/watch_pets.py` already writes
   `logs/watchpets_alerts.jsonl` and is scheduled every 5 min. As
   long as one tool reads that file (Unified Dashboard `Actions` tab,
   for example), the operator does not depend on Telegram for visual
   notification of CRITICAL events. The auto-drafted postmortem stub
   adds a second persistent alerting channel via the file system.
4. **Enable `--autoheal` on the `TrendMaster Watch-Pets` scheduled
   task** once the operator has trusted the heuristic for a week.
   Conservative gating: brain DEAD + market hour 06-23 + cooldown
   10 min + canonical sources intact -> launch `start_brain_clean.cmd`.
   Would have brought the brain back within 10-15 min of termination
   instead of 16 hours.
5. **Add a CI check for scheduled-task action quoting.**
   `tools/schtasks_audit.py` already detects this pattern via
   `LastTaskResult=2147942593`. Promote it to a precommit-time check
   that scans for any `Get-ScheduledTask` action where `Execute`
   contains a path-with-space and `Args` is non-empty (the canonical
   broken pattern).

## Operator follow-up checklist

- [ ] (1) Patch `ai_trading_agents/process_lock.py` to also write `logs/brain.pid`
- [ ] (2) Update `START_TRENDMASTER_LIVE.bat` to use `start /B` direct python launch
- [ ] (4) Once trust is built, enable `--autoheal` on `TrendMaster Watch-Pets`
- [ ] (5) Add the action-quoting CI check (1-day task)
- [ ] Investigate Code Graph Rebuild + Events Rotator drift (separate, surfaced by audit)
- [ ] Review brain ML state - the new boot loaded `trend_master_model.lgb` cleanly, but CLAUDE.md states the model was renamed to `.b3_clean_disabled_2026-04-28`. Either someone restored it (intentional) or the rename did not persist (bug).
