# Round 5 deployment runbook

_Scope: Round 5 daily-cadence features — per-team cap, session boost, re-entry, pyramid, TP-ladder mirror. Requires EA recompile + Python brain restart. Anchors to `INSTALL_v14.md`; does not replace it._

**Last reviewed:** 2026-04-24

---

## Summary

Five features ship together. Four default to `enabled = True` in `config/settings.py`; one (`RISK.max_open_per_team = 2`) is a hard binding limit. No database migrations, no API changes, no breaking config shifts. Risk is concentrated in two places: (a) EA recompilation must succeed before the brain picks up new signals with pyramid / partial-TP semantics, (b) the re-entry permit state persists across restarts, so a bad permit can survive a brain restart.

## Features and where they live

| # | Feature          | Flag (config/settings.py)              | Python module                              | EA side                       |
|--:|------------------|----------------------------------------|--------------------------------------------|-------------------------------|
| 1 | SESSION_BOOST    | `SESSION_BOOST.enabled = True`         | config-only, applied in brain confidence gate | n/a                       |
| 2 | REENTRY          | `REENTRY.enabled = True`               | `ai_trading_agents/reentry_tracker.py`     | honours `reentry=True` flag in signal JSON |
| 3 | PYRAMID          | metadata mirror only in Python         | n/a (Python), EA enforces                  | `InpUsePyramid`, `InpPyramidR`, `InpPyramidSizePct`, `InpPyramidNeedTrend` |
| 4 | PARTIAL_TP_LADDER| metadata mirror only in Python         | n/a (Python), EA enforces                  | `InpPartial1Pct=0.40`, `InpPartial2Pct=0.30` |
| 5 | PER_TEAM_CAP     | `RISK.max_open_per_team = 2`           | `ai_trading_agents/risk_manager.py`        | n/a                           |

## Rollback triggers (read first)

Abort deployment and revert immediately if any of the below occurs during rollout:

- Any reentry test fails on the full suite (not just `tests/test_reentry_tracker.py`)
- EA compile produces an error or a different `.ex5` byte size without a matching `.mq5` diff
- After brain restart, `/pnl` or `/why` Telegram commands don't respond within 30 seconds
- Any open position at the moment of restart is mid-partial-TP level

## Pre-flight (T-60 to T-15 minutes)

1. **Market window check.** Deploy outside active trading hours. Preferred window: Saturday UTC or Friday ≥ 22:00 UTC.
2. **Snapshot state.**
   ```
   copy logs\brain_state.json logs\brain_state.backup.json
   copy MQL5\Experts\AI_SUPERBB_v14_TrendMaster.ex5 MQL5\Experts\AI_SUPERBB_v14_TrendMaster.ex5.bak
   git rev-parse HEAD > logs\last_known_good.sha
   ```
3. **Confirm no positions mid-partial-TP.** Inspect `logs/brain_state.json`. If any open position is past +1R, wait for resolution or flatten manually before proceeding.
4. **Run full test suite.**
   ```
   pytest tests/ -v --tb=short
   ```
   If anything fails, **stop**. Do not cherry-pick around failures.
5. **Validate Python config syntax.**
   ```
   python -m py_compile config\settings.py ai_trading_agents\reentry_tracker.py
   ```
6. **Verify the 11 reentry tests still pass in isolation.**
   ```
   pytest tests/test_reentry_tracker.py -v
   ```
7. **(Recommended) Run ea_parity once against the current baseline.** If it flags divergence before the deploy, investigate before changing anything.
   ```
   python tools\ea_parity_nightly.py
   ```

## Deploy (T-0)

Order matters. Do not parallelise steps.

### Step 1 — Stop the brain

```
STOP_TRENDMASTER_v14.bat
```

Wait 10 seconds. Verify no `python.exe` in `tasklist` under this repo's venv.

### Step 2 — Recompile the EA

1. Open MT5 → Tools → MetaEditor (F4).
2. Open `AI_SUPERBB_v14_TrendMaster.mq5` from the repo root.
3. Compile (F7).
4. Expect: `0 error(s), 0 warning(s)` and a fresh `.ex5` under `MQL5\Experts\`.
5. Note new byte size: `dir MQL5\Experts\AI_SUPERBB_v14_TrendMaster.ex5`. If size is identical to the `.bak`, the compile may have silently reused the cache — re-compile after closing MetaEditor.

### Step 3 — Detach and re-attach the EA in MT5

1. Right-click the chart with the EA attached → Expert Advisors → Remove.
2. Drag `AI_SUPERBB_v14_TrendMaster` from the Navigator onto the same chart.
3. In the input dialog, verify the Round 5 inputs:
   - `InpUsePyramid = true`
   - `InpPyramidR = 1.0`
   - `InpPyramidSizePct = 0.5`
   - `InpPartial1Pct = 0.40`
   - `InpPartial2Pct = 0.30`
4. Click OK. Confirm AutoTrading is on. The smiley face in the top-right of the chart must be present.
5. Watch the Experts tab for the initial "EA initialized" line.

### Step 4 — Start the brain

```
start_brain_clean.cmd
```

This kills any leftover Python, clears `__pycache__`, deletes `brain.lock`, and launches the brain. It waits 15 seconds for boot.

### Step 5 — Smoke test (90 seconds)

- Tail `logs\trend_master_brain.out`: expect "Brain started" and heartbeats.
- Telegram `/pnl` → reply within 5 seconds.
- Telegram `/why XAUUSD` → agent votes + regime reply.
- Telegram `/drift` → DriftMonitor state. If `HALT` right after restart, **stop** and investigate before letting the brain tick further.

## Post-deploy (T+1 hour, T+1 trading day)

### T + 1 hour

- Read `logs\trend_master_brain.out` for any ERROR or Traceback.
- Read `logs\trend_master_brain.err` — should be empty.
- Inspect `logs\brain_state.json` for `reentry_permits` — expect an empty dict until a loss occurs.
- Check Experts tab in MT5 for any EA warnings about unknown inputs.

### T + 1 trading day

- Confirm `per_team` counts respect `max_open_per_team = 2`: no team should appear with `open_positions_count > 2` in daily digest.
- Verify at least one successful partial-TP fill in Experts tab (e.g., "Partial TP1 hit at +1R, closed 40%").
- If a loss occurred: confirm a reentry permit was minted (visible in `state.reentry_permits`) and the cooldown is being respected.
- Run `pytest tests/test_reentry_tracker.py -v` again — still green.
- Run `python tools/ea_parity_nightly.py` manually — first post-deploy run should NOT flag divergence unless a gate was intentionally changed. If it flags, reseed the baseline with `del reports\ea_parity_baseline.json` only after confirming every divergence is intentional.

## Rollback

If any rollback trigger fires, or if the post-deploy checks fail:

1. `STOP_TRENDMASTER_v14.bat`
2. Revert EA:
   ```
   copy /Y MQL5\Experts\AI_SUPERBB_v14_TrendMaster.ex5.bak MQL5\Experts\AI_SUPERBB_v14_TrendMaster.ex5
   ```
3. Remove and re-attach the EA from the chart to pick up the reverted `.ex5`.
4. Revert Python:
   ```
   git checkout %HEADFILE%
   ```
   where `%HEADFILE%` is the contents of `logs\last_known_good.sha` from pre-flight.
5. Restore state:
   ```
   copy /Y logs\brain_state.backup.json logs\brain_state.json
   ```
6. `start_brain_clean.cmd`
7. Re-run smoke test.
8. Post a Telegram note: "Round 5 rollback executed, cause: ..." so the decision is in the record.

## Feature-flag kill switches (if partial rollback needed)

If only one feature misbehaves, toggle in `config/settings.py` without a full revert:

- `SESSION_BOOST.enabled = False`
- `REENTRY.enabled = False`
- `RISK.max_open_per_team = 99`   (effectively disables the cap)

Pyramid and PARTIAL_TP_LADDER are EA-enforced; disabling requires an EA input change + detach/re-attach (no recompile needed for input tweaks).

## References

- `INSTALL_v14.md` — base install / operate / troubleshoot
- `docs/ENHANCEMENTS_2026-04-23.md` — Round 2/3 enhancements context
- `RISK_MODEL.md` — risk envelope, max-DD breaker, per-team cap rationale
- `tests/test_reentry_tracker.py` — 11 reentry unit tests, ground-truth behaviour

---

_Owner: Sumit. Keep this doc next to the `.ex5.bak` — if you don't have the `.bak`, you don't have a deploy plan._
