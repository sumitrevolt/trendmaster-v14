---
name: trading-dupe-executor-fix
description: "Diagnose and fix duplicate python_signal_executor or trailing_stop_manager processes on Windows. Use whenever the operator notices the SAME signal being placed multiple times in MT5 within seconds (e.g., AUDJPY deal_ids 733164796..733164799), the executor log shows 'lock held by another instance — exiting' repeatedly, MT5 USD-concentration cap unexpectedly exceeds the safeguards.py limit (long-USD=4/3 or short-USD=4/3), or psutil/Task Manager shows 4+ python.exe processes for a singleton component. ALSO use proactively after any laptop restart, brain restart, or watchdog change to verify singletons are intact. Use whenever someone says 'duplicate trades', 'duplicate executors', 'lock contention', 'concentration breach without obvious cause', '4 of the same trade', 'trades placed multiple times', or pastes log lines containing 'lock held by another instance'."
---

# trading-dupe-executor-fix

The "why is the same signal being executed 4×" diagnostic + remediation
playbook. Rooted in the 2026-05-09 incident where 2 redundant Windows
schtasks (`Health Watchdog` 1-min + `Process Watchdog` 2-min) both
watched the same components and both auto-respawned them after boot,
silently creating duplicate logical instances that each acted on every
TV/brain signal independently.

## When to use

- MT5 shows multiple identical positions opened within 1–2 seconds of
  each other (same symbol, same direction, deal_ids in tight cluster)
- `logs/python_executor.log` repeatedly emits
  `python_signal_executor lock held by another instance — exiting`
- `tools/safeguards.py` keeps blocking new signals with
  `long-USD positions (cap 3)` even when MT5 shows few open positions
- After any laptop restart — there's a known race between the dual
  watchdogs at boot. Verify even if nothing looks wrong.
- After someone modifies `tools/health_watchdog.py` or
  `tools/process_watchdog.py` — confirm singletons still hold.

## ⚠️ Windows venv parent+child PID gotcha

On Windows, `.venv\Scripts\pythonw.exe` is a thin Microsoft Store
launcher shim that exec's the actual `Python311\pythonw.exe` interpreter
from `%LOCALAPPDATA%\Programs\Python\Python311\`. The shim does not
exit — it stays alive alongside its child for the process lifetime.

**Result:** every logical Python script shows up as **2 PIDs** in
psutil/Task Manager. So 4 PIDs of `python_signal_executor` could mean:
- 2 logical instances (2 healthy venv pairs) → genuine duplicate
- 4 logical instances (4 separate launches) → severe duplicate
Only the ppid graph tells you which.

`outputs/verify_singleton_logical.py` groups by ppid chain and reports
LOGICAL instance count, which is what you actually care about.

When killing duplicates, kill the PARENT root with `taskkill /F /T /PID
<root>` — the `/T` flag tree-kills children automatically.

## Run the diagnostic playbook

From repo root, in this order:

### Step 1 — see what's actually running

```cmd
.venv\Scripts\python.exe outputs\verify_singleton_logical.py
```

Reports:
- Raw PID count for each component (executor + trailing-stop)
- Parent-child grouping → logical instance count
- Whether you have a duplication problem at all

If logical count == 1 for both, **stop here** — no problem to fix.

### Step 2 — find the dupe-spawner schtask

```cmd
.venv\Scripts\python.exe outputs\audit_dupe_root_cause.py
```

Output groups all 28+ TrendMaster scheduled tasks by target script.
Look for `WARN <target>: N task(s)` where N > 1 — that's the redundancy.

Historical findings (as of 2026-05-09):
- `TrendMaster Process Watchdog` was redundant with `TrendMaster Health Watchdog`
  (both watched executor + trailing + webhook + ctrader). Process is now DISABLED.
- Only one watchdog should be active per component.

### Step 3 — clean up + spawn singletons

If Step 1 showed >1 logical instance, run:

```cmd
.venv\Scripts\python.exe outputs\fix_dupe_root_cause_2026-05-09.py
```

This script:
1. Disables `TrendMaster Process Watchdog` schtask (idempotent — safe to
   re-run)
2. Sleeps 8s so any in-flight watchdog runs finish
3. Kills all `python_signal_executor` PIDs (parent root → /T cascades)
4. Waits up to 10s for PIDs to actually disappear from process list
5. Unlinks `logs/python_signal_executor.lock` (only after PIDs gone —
   prevents orphan-lock state)
6. Spawns ONE clean detached pythonw instance
7. Verifies first heartbeat appears in `logs/python_executor.log` within 60s
8. Repeats steps 3–7 for `trailing_stop_manager`
9. Sleeps 70s and re-verifies — catches any rogue respawner that beat
   the disable

Final state: 1 logical instance each. If Step 9 shows >1 again, there's
ANOTHER dupe-spawner not yet identified — go back to Step 2 with
keyword search expanded.

## Common failure modes

### "fix script reports SUCCESS but Step 1 still shows 4 PIDs"

The "4 PIDs" might be 1 logical (parent+child × 1 process actually
spawning a Python311 grandchild) — but that's unusual. More likely:
the orphan-lock bug recurred, OR a third dupe-spawner exists that
neither Process Watchdog nor manual launch triggered.

Audit with: `outputs/audit_dupe_root_cause.py` and search broader keywords.

### "PIDs keep coming back every minute"

A schtask is firing every minute. Use `schtasks /Query /fo CSV /v` and
grep for python_signal_executor to find it. Common culprits:
- `hidden_python_executor.vbs` callers
- `master_autostart.py` schtasks
- watch_pets that auto-heal via `subprocess.Popen` of executor

### "Health Watchdog isn't respawning after kill"

Look at `logs/watchdog_state.json` — if `last_action_executor` was
recent (< 5 min ago), watchdog is in cooldown. Wait it out, or edit the
state file to clear the cooldown timestamp.

## Permanent fix history (don't re-introduce regressions)

- **2026-05-09 22:03 IST:** Process Watchdog schtask DISABLED. Health
  Watchdog is sole singleton enforcer. Don't re-enable Process Watchdog
  without first modifying `tools/process_watchdog.py` to skip components
  Health covers (executor/trailing/webhook/ctrader). Leave it watching
  dashboard_server.py only.
- **2026-05-09:** `tools/health_watchdog.py check_executor()` patched.
  Kills now poll-wait up to 8s for PIDs to disappear before unlinking
  the lock. Don't revert to immediate-unlink-after-taskkill.

## Related skills + files

- `trading-zero-trades` — for "brain alive but no trades" diagnostic
  (different symptom, different cause)
- `trading-brain-restart` — when brain.out goes stale
- Memory: `reference_venv_pythonw_parent_child.md` (durable insight)
- Memory: `project_2026-05-09_dupe_executor_root_cause.md` (incident
  context)
- CLAUDE.md "⚡ 2026-05-09 DUPE-EXECUTOR FIX" section (top of file)
