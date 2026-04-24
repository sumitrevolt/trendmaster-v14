# Migrating TrendMaster v14 off OneDrive-synced Documents\

## Why

The project currently lives at
`C:\Users\Ratanshila\Documents\autmated trading\`. Windows syncs
`Documents\` to OneDrive by default. OneDrive caches stale snapshots
and occasionally replays them — silently deleting live Python modules
from `ai_trading_agents/` and `main.py` from disk.

The running brain is unaffected (modules are loaded in memory), but
every CLI call (`python main.py perf`, `pytest`, pre-commit) fails
until `git restore` is rerun.

**The permanent fix is to move the project out of OneDrive scope.**
`C:\Dev\` or `C:\Projects\` are good choices — they're outside every
known Windows-sync path.

## When to do it

**Not during a live session.** Do this when you've planned a brain
restart anyway — end-of-trading-day, scheduled maintenance, or a
Round/version cutover. Takes ~10 minutes including verification.

## Step-by-step

### 1. Prepare (still at old path)

```powershell
cd "C:\Users\Ratanshila\Documents\autmated trading"

# Snapshot current state to logs + commit anything pending.
python main.py rotate
git status --short
git add -A
git diff --cached --stat
git commit -m "chore: pre-OneDrive-migration snapshot"
git push origin main
```

### 2. Take the brain down

```powershell
# Preferred (graceful — flushes state, closes MT5 connection, etc.):
STOP_TRENDMASTER_v14.bat

# Verify:
Get-Process python,terminal64 -ErrorAction SilentlyContinue
# should show no python.exe with main.py or trend_master_brain.py in
# the command line; MT5 can stay running or be closed — your call.
```

### 3. Clone fresh at new path

**Don't `Move-Item`** — OneDrive would try to "un-move" it back. Clone
fresh from GitHub instead.

```powershell
mkdir C:\Dev -Force
cd C:\Dev
git clone https://github.com/sumitrevolt/trendmaster-v14.git
cd trendmaster-v14
```

### 4. Recreate local-only state that isn't in git

These are all `.gitignore`'d so they don't exist in the fresh clone:

- Virtual environment: `py -3.11 -m venv .venv ; .venv\Scripts\pip install -r requirements.txt`
- Environment files: copy `config\.env.example` → `config\.env` and
  `ai_trading_agents\.env.example` → `ai_trading_agents\.env`, fill in
  the Telegram bot token and broker creds from your password manager.
- State JSON files (`agent_memory.json`, `brain_memory.json`,
  `trendmaster_signals.json`, etc.) are per-run — the brain
  regenerates them on first tick, no copy needed.
- ML models in `ai_trading_agents/ml_models/*.pkl` — copy from the
  old dir if you want to keep the last trained weights, otherwise
  run `python main.py train` after the first session of fresh data.
- Graph DB: run `rebuild_graph.cmd` to populate `.code-review-graph/`.

### 5. Update pointers

- **MT5 Expert Advisor**: the EA reads the signal JSON from a full
  path baked into its config. In MT5, open each chart's attached
  `AI_SUPERBB_v14_TrendMaster.mq5` EA, update the `SignalPath` input
  from `C:\Users\Ratanshila\Documents\autmated trading\...` to
  `C:\Dev\trendmaster-v14\...`. Reattach or recompile.
- **Windows Task Scheduler**: update the action path for
  `TrendMaster Code Graph Rebuild` (our daily 03:00 task):
  ```powershell
  schtasks /Delete /TN "TrendMaster Code Graph Rebuild" /F
  cd C:\Dev\trendmaster-v14
  tools\install_scheduled_rebuild.cmd
  ```
- **Desktop shortcut**: `Sumit AI Trading System.lnk` points at the
  old `START_TRENDMASTER_v14.bat`. Right-click → Properties → fix
  the Target and Start-in paths.
- **code-review-graph registry**: re-register the new path.
  ```powershell
  code-review-graph register --alias trendmaster-v14 C:\Dev\trendmaster-v14
  ```

### 6. Start fresh

```powershell
cd C:\Dev\trendmaster-v14
START_TRENDMASTER_v14.bat
```

Watch `logs\trend_master_brain.log` for the first tick summary within
30 s. If you see symbol-scan entries, you're good.

### 7. Delete the old folder (optional, later)

Once the new path has been trading successfully for a day or two,
delete the old OneDrive folder so you don't accidentally launch from
it again:

```powershell
Remove-Item "C:\Users\Ratanshila\Documents\autmated trading" -Recurse -Force
```

## Roll-back plan

If anything breaks at the new path, the old folder is still there
(you didn't delete it in step 7). Point the EA signal path back,
run `START_TRENDMASTER_v14.bat` from `C:\Users\Ratanshila\Documents\autmated trading\`,
and you're back to today's working state. No data loss — the new
clone can be nuked.

## Why not just pin files in OneDrive?

Tried it (`attrib +p -u` recursively). OneDrive still syncs its
cached state over pinned files. The only reliable fix is to get out
of the sync path entirely.
