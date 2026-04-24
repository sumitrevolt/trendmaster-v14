---
name: trading-brain-restart
description: "Safe clean restart of the TrendMaster v14 Python brain. Use when the brain needs to be restarted after config changes, code updates, or when logs/state look stale. Wraps start_brain_clean.cmd with pre-flight checks and a post-start smoke test so half-killed processes and stale lock files don't cascade into trading errors."
---

# trading-brain-restart

Safe restart flow for `ai_trading_agents/trend_master_brain.py`. The point of this skill is to avoid the two failure modes that bite a naive restart: half-killed Python processes that still hold the MT5 connection, and stale `logs/brain.lock` files that block the new process from starting.

## When to use

- After editing `config/settings.py` or `config/.env`
- After pulling new code into `ai_trading_agents/` or `tools/`
- When `/why` or `/pnl` Telegram commands stop responding
- When `logs/trend_master_brain.err` shows `brain.lock exists`
- Before deploying Round 5 features (EA recompile + brain restart is the canonical pair)

## Pre-flight

1. Verify no trades are in a risky mid-state: inspect `logs/brain_state.json` for `open_positions`. If a position is mid-partial-TP, wait for the level to resolve or flatten manually in MT5.
2. Confirm MT5 is running and auto-connected to the broker.
3. Snapshot state:
   ```
   copy logs\brain_state.json logs\brain_state.backup.json
   ```
4. Note the current commit for rollback: `git rev-parse HEAD > logs\last_known_good.sha`.

## Restart

From repo root (`C:\Users\Ratanshila\Documents\autmated trading`):

```
start_brain_clean.cmd
```

Under the hood this does, in order:

1. `taskkill /F /IM python.exe` — kills every Python process (broker connection drops cleanly).
2. Deletes `__pycache__` in `ai_trading_agents/`, `config/`, `tools/`.
3. Deletes `logs/brain.lock`.
4. Truncates `logs/trend_master_brain.out` and `.err`.
5. Launches `.venv\Scripts\python.exe -u ai_trading_agents\trend_master_brain.py` in a new window titled "TrendMaster Brain - LIVE".
6. Captures the PID into `logs/brain.pid`.
7. Waits 15 seconds for boot.

## Smoke test (30 seconds after start)

- Tail the out log:
  ```
  powershell -c "Get-Content logs\trend_master_brain.out -Tail 50"
  ```
  Expect: "Brain started", then heartbeat ticks approximately every 5 seconds.
- Telegram `/pnl` → reply within 5 seconds.
- Telegram `/why XAUUSD` → agent votes reply within 5 seconds.
- `logs/brain.pid` exists and the PID is alive (`tasklist | findstr <pid>`).

If any of those fail: **stop**. Read `logs/trend_master_brain.err` first. Do not re-run the restart before understanding the failure.

## Gotchas (from prior incidents)

- `Stop-Process -Force <pid>` cascades to the parent terminal on Win11 24H2. Use `taskkill /F /IM python.exe` — already in the `.cmd`.
- `wmic` is deprecated on Win11 24H2. Don't add `wmic process` to the flow.
- `cmd` expands `%VAR%` at parse time, not at execution time. If you're editing the `.cmd` to add an env var, use `call set` or `setlocal enabledelayedexpansion`.
- Long paths (> 260 chars) break naive file operations. All paths used here are under the repo root and safe.

## Rollback

If the brain won't start on the new config:

1. `copy logs\brain_state.backup.json logs\brain_state.json`
2. `git checkout $(Get-Content logs\last_known_good.sha)`
3. Re-run `start_brain_clean.cmd`.
