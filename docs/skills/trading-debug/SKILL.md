---
name: trading-debug
description: "Project-specific debugging runbook for the TrendMaster stack. Use when something is wrong and you need a structured symptom→cause→fix path: no trades firing, too many trades, wrong direction, broken handles, brain-EA desync, dashboard 500, signal file stale, MT5 session drops, AutoTrading off, orders rejected. Covers the 20 most common failure modes with exact diagnostic commands and fixes."
---

# trading-debug

When the stack breaks at 2am, you don't want to reason from first principles. This skill is a structured runbook — symptom → diagnostic command → cause → fix — for the most common failure modes in this project.

**Principle:** always diagnose top-down along the funnel. Most bugs reduce to: where did the signal/trade die? Find that stage, then dig in.

## The funnel

```
Bars from MT5
   → Python brain pulls bars
      → Brain computes features
         → Brain computes ML + agent votes
            → Brain writes trendmaster_signals.json
               → EA reads signal file
                  → EA computes its own local confirmations
                     → EA HTF gate
                        → EA AI gate
                           → EA SendOrder → broker
```

Most bugs manifest as "no trades"; the fix is finding the earliest stage where the flow dies.

## 1. "No trades firing"

Run the health-check probe first:

```powershell
C:\Users\Ratanshila\check_brain.bat
```

Interpret outputs:

| Output | Stage at fault | Fix |
|---|---|---|
| `dashboard: DOWN` | Brain or dashboard not running | Run `restart_brain_only.bat` |
| `signal age_sec: missing` | Brain never wrote signal file | Check `brain.err`; path mismatch likely |
| `signal age_sec > 30` | Brain alive but hung / error loop | Tail `brain.err`; restart |
| `signal age_sec OK, direction: NONE` always | Brain deciding not to trade | Go to §1a |
| `signal OK, direction: BUY/SELL` but no trade | EA-side filter blocking | Go to §1b |

### 1a. Brain always returns NONE

Check the debug sidecar:

```powershell
type "C:\...\MQL5\Files\trendmaster_signals.debug.json"
```

Look at `skipped_reason`:

- `agent_dir_zero` → agents don't unanimously agree. Which one? Check `agents.votes` in the signal file — the one with `vote: 0` is the blocker.
- `ml_confidence_too_low` → ML model uncertain; lower `min_ml_confidence` in settings or retrain.
- `bars_missing` → `copy_rates_from_pos` returning None; MT5 session dropped or symbol spelled wrong.
- `mt5_not_connected` → MT5 terminal closed or AutoTrading off.

### 1b. Brain says trade but EA ignores

Read today's MT5 log:

```powershell
powershell -Command "Get-Content 'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\<hash>\MQL5\Logs\<YYYYMMDD>.log' -Encoding Unicode -Tail 200 | Select-String 'TrendMaster'"
```

Look for `DBG` lines:

| Log line | Cause | Fix |
|---|---|---|
| `HTF gate BLOCK: <reason>` | H4/H1/M30 disagree with signal | Agents and HTF gate not aligned; check input params match between brain and EA |
| `spread X > cap Y, skip` | Spread above cap | Temporarily raise `InpMaxSpreadPoints` or wait for tighter market |
| `confirmations X/3` (X<3) | Local EA indicators disagree | Indicator handle might be invalid — check `OnInit` log |
| `signal stale age=X` | EA clock > brain write time by > limit | Clock skew; sync times |
| `InpMagic mismatch on position` | Another EA interfering | Check no other EAs running |
| `trade_allowed=false` | AutoTrading button off | Click the AutoTrading icon (green) in MT5 toolbar |
| `TRADE_RETCODE_INVALID_STOPS` | SL/TP inside broker stop level | See §7 |
| Nothing at all | EA not attached / wrong chart | See §2 |

## 2. EA not attached to chart / no logs at all

```powershell
C:\Users\Ratanshila\check_ea.ps1
```

Checks:
- `terminal64.exe` running
- `AI_SUPERBB_v14_TrendMaster.ex5` mtime matches latest compile
- Chart contains EA (check by looking at today's log for `OnInit` lines)

**Common causes:**

- Chart closed / not reopened after crash → reopen chart, EA re-attaches from profile.
- EA removed from chart manually → drag from Navigator back onto chart.
- `.ex5` recompiled but terminal not restarted → restart MT5.
- Wrong symbol/chart → EA needs to be on the exact symbol in its `InpSymbol` (or `_Symbol` if it uses the chart's).

## 3. Brain crashes on startup

```powershell
type C:\...\brain.err
```

Typical patterns:

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: MetaTrader5` | Wrong venv active | Verify `pythonw` is the one with the venv installed |
| `mt5 init failed: (-10003, 'Terminal: Authorization failed')` | Credentials wrong or MT5 not running | Check login/password/server, ensure MT5 is running and logged in manually first |
| `FileNotFoundError: .../MQL5/Files/...` | SIGNAL_PATH directory missing | MT5 data folder path hash differs; run `%APPDATA%\MetaQuotes\Terminal\` and update path |
| `ImportError: No module named 'lightgbm'` | Dep missing from restart env | `pip install --break-system-packages -r requirements.txt` |
| Crashes silently, empty `brain.err` | Another instance holding log file | `tasklist | findstr pythonw` — kill all, restart |

## 4. Signal file stale but brain process is alive

Brain is running but `signal age_sec > 30`:

```python
# attach debugger or add logging — find out where tick_once is hung
```

Usual suspects:

- **`mt5.copy_rates_from_pos` hanging** → MT5 session dropped mid-session. Fix with timeout + reconnect:

  ```python
  def pull_bars_guarded(self, tf, n, timeout=5):
      import threading, time
      result = [None]
      def target(): result[0] = mt5.copy_rates_from_pos(self.symbol, _TF_MAP[tf], 0, n)
      t = threading.Thread(target=target); t.start(); t.join(timeout=timeout)
      if t.is_alive():
          log.error("mt5 copy_rates hung, reconnecting")
          mt5.shutdown(); time.sleep(1); mt5_connect(...)
          return None
      return result[0]
  ```

- **ML inference slow** (model too big) → profile `tick_once`; should run in < 500ms. If > 3s, consider smaller model or caching features.
- **File system slow** (antivirus scanning every write) → add brain dir to AV exclusion list.

## 5. "Wrong direction" — trade opened opposite to expected

Almost always a sign confusion somewhere. Diagnostic order:

1. Check `signal.direction` at time-of-trade (read debug sidecar backups).
2. Check `signal.agents.dir`.
3. Check EA log for `BUY/SELL` in the send-order line.

**If `signal.direction != EA action`:** EA has its own opinion. Look at `CheckHTFGate` log — EA may have overridden based on native HTF check.

**If all three agreed on BUY but EA placed SELL:** sign bug. Look at any recent edit to `TryEntry`; check `ORDER_TYPE_BUY` vs. `ORDER_TYPE_SELL` constants.

**If signal was SELL but agent votes show +1 / +1 / +1:** sign mapping bug in `multi_agent.py` — `{+1: "BUY", -1: "SELL"}` mapping was inverted somewhere.

## 6. Too many trades — overtrading

Symptom: EA firing every few minutes on M30 chart.

Diagnostic:

```powershell
powershell -Command "Select-String -Path '...\Logs\<date>.log' -Pattern 'DBG|TRADE_RETCODE_DONE' | Measure-Object"
```

If > 50 entries/day on M30, almost certainly:

- **Cooldown not enforced** → add `InpMinSecBetweenTrades` guard in `TryEntry`.
- **Signal re-fires inside the same bar** → add "already traded this bar" check:

  ```cpp
  static datetime last_entry_bar = 0;
  datetime cur_bar = iTime(_Symbol, _Period, 0);
  if(cur_bar == last_entry_bar) return;
  // ... entry logic ...
  last_entry_bar = cur_bar;
  ```

- **InpMagic duplicated across charts** → two charts with the same EA both entering. Give each a unique Magic.
- **Confirmations too loose** → tighten ADX min, RSI window, or add a second confirmation.

## 7. Orders rejected by broker

Read the retcode in the EA log:

```cpp
DBG(StringFormat("OrderSend FAIL: retcode=%d  comment=%s",
                  result.retcode, result.comment));
```

Common retcodes:

| Retcode | Meaning | Fix |
|---|---|---|
| 10004 `REQUOTE` | Price moved, broker rejected | Retry with `deviation` widened |
| 10006 `REQUEST_REJECTED` | Generic reject | Check `comment` for specifics |
| 10013 `INVALID_REQUEST` | Malformed request | Price/volume format wrong — log the whole request |
| 10014 `INVALID_VOLUME` | Lot < min or > max or not step-aligned | Use `CalcLot` floor/step clamp |
| 10015 `INVALID_PRICE` | Price stale | Refresh `MqlTick` right before send |
| 10016 `INVALID_STOPS` | SL/TP inside `STOPS_LEVEL` | Clamp — see §7a |
| 10017 `TRADE_DISABLED` | Symbol trading disabled (weekend/holiday) | Don't trade |
| 10018 `MARKET_CLOSED` | Market closed | Add session guard |
| 10019 `NO_MONEY` | Insufficient margin | Reduce size or skip trade |
| 10021 `PRICE_OFF` | Stale price | Refresh tick |
| 10030 `INVALID_FILL` | Filling mode unsupported | See `trading-order-execution` skill |

### 7a. STOPS_LEVEL clamping

```cpp
double stops_level = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
double min_dist = MathMax(stops_level, 5 * _Point);   // at least 5 points buffer

if(request.type == ORDER_TYPE_BUY) {
    if(request.sl > 0 && bid - request.sl < min_dist) request.sl = bid - min_dist;
    if(request.tp > 0 && request.tp - ask < min_dist) request.tp = ask + min_dist;
}
```

## 8. Dashboard 500 / not loading

```powershell
C:\Users\Ratanshila\check_dash.ps1
```

If dashboard HTTP is down:

```powershell
type C:\...\dashboard.err
```

Common issues:

- **Port 8000 in use** → another service binding; `netstat -ano | findstr :8000` → kill the PID or change the port.
- **JSON parse error in `/api/state`** → signal file corrupted mid-write. Check if `os.replace` is being used (not `open(..., 'w')`-in-place).
- **404 on `/`** → dashboard's static HTML serve path wrong; verify the working directory of the pythonw invocation.

Quick restart:

```powershell
C:\Users\Ratanshila\restart_dashboard.bat
```

## 9. MT5 session drops mid-session

Symptoms: `brain.err` shows `mt5.terminal_info() returned None` repeatedly.

Causes:
- VPS network blip (most common on cheap VPS providers)
- MT5 auto-logged out after 24h if "stay logged in" wasn't checked
- Windows Update restart during trading hours

Mitigations:

```python
def ensure_connected(self):
    if mt5.terminal_info() is None:
        log.warning("mt5 disconnected, reconnecting")
        mt5.shutdown()
        time.sleep(2)
        return mt5_connect(LOGIN, PWD, SERVER, PATH)
    return True
```

Call at top of every `tick_once`. Don't crash the brain loop — reconnect and continue.

## 10. Chart visuals gone after restart

If you rely on chart drawings for visual debugging and they disappear:

- `.chr` template wasn't saved → right-click → Template → Save Template → default
- EA's `OnDeinit` didn't clean up old objects; fresh EA load collides with stale ones → add `ObjectsDeleteAll(0, InpObjectPrefix)` in `OnInit`.
- Terminal profile got corrupted → delete `profiles/default/` and re-add the EA (loses other charts).

## 11. Dashboard shows stale equity

Dashboard reads equity via separate MT5 session or via file.

- If via file (brain writes `ea_state.json`): check the brain is reading `mt5.account_info()` and writing it periodically.
- If via own MT5 session (dashboard has its own `mt5.initialize`): two processes connecting to MT5 with same credentials sometimes conflict — force one via MT5's slot concept, or poll less frequently.

## 12. Python / MT5 version mismatch

`MetaTrader5` module version must match MT5 build. Symptoms: `mt5.initialize` works but `copy_rates_from_pos` returns empty.

```python
import MetaTrader5 as mt5
print("module version", mt5.__version__)
# then in MT5: Help → About → note build number
```

Upgrade via `pip install --upgrade --break-system-packages MetaTrader5`.

## 13. Git / deployment mismatch

Symptom: code on disk says one thing, behavior suggests another.

Checks:

```powershell
git status
git log --oneline -n 5
powershell -Command "Get-FileHash 'C:\...\AI_SUPERBB_v14_TrendMaster.ex5'"
powershell -Command "(Get-Item 'C:\...\AI_SUPERBB_v14_TrendMaster.ex5').LastWriteTime"
```

If the `.ex5` is older than the latest `.mq5` edit → it wasn't recompiled. Run `compile_ea.bat`. If the `.mq5` on disk is not the one you edited, you're editing the wrong file — path confusion between source dir and MT5's `Experts/` copy.

## 14. The "one trade per year" mystery

Backtest showed 200 trades/year; live gets 2.

- **Broker feed differs from backtest feed** — check tick count and spread distribution.
- **Session/news filter nullified live but not backtest** → backtest had no news data.
- **Brain never runs live (only during dev sessions)** → set up as scheduled task / service (see `trading-deploy-monitor`).
- **AutoTrading toggled off most of the day** → symptom of unattended state-check gap.

## 15. "Worked yesterday, broken today"

Classic triage:

1. `git diff HEAD~1` — what changed?
2. `brain.err` — any new error?
3. MT5 log — any new rejections?
4. Broker announcements — did the broker change spread rules or leverage overnight?
5. Time/date-related? (DST switchover, new month)
6. Symbol name change (`XAUUSD` vs. `XAUUSD.`, or `XAUUSDm`)

If nothing obvious: roll back to yesterday's git HEAD, confirm behavior returns. Then bisect between yesterday and now.

## 16. Canary mode

Before deploying any significant change to live, run canary:

```
InpRiskPct = 0.1     // 10% of normal
InpMagic = 99999     // separate magic so trades are distinguishable
```

Let it run for 48h. Compare trades against what the production system took. Gross divergence = bug.

## 17. Log-driven debugging tips

Three logs that cover 95% of issues:

1. `brain.log` — Python side, INFO level, decisions.
2. `brain.err` — Python side, ERROR level, exceptions.
3. `<MT5>/Logs/<date>.log` — MT5 side (UTF-16 encoded!), the EA's `Print`/`DBG` statements.

Always tail all three simultaneously when reproducing:

```powershell
wt.exe new-tab powershell -Command "Get-Content brain.log -Wait -Tail 20" `; `
       new-tab powershell -Command "Get-Content brain.err -Wait -Tail 20" `; `
       new-tab powershell -Command "Get-Content <mt5log> -Wait -Tail 20 -Encoding Unicode"
```

## 18. When to escalate (i.e. ask for help)

Ask for help on forums / Discord / GitHub issue when:

- You've ruled out the top 10 causes in this skill (via the runbook above).
- You can reproduce the bug reliably — include a minimal repro.
- You've captured the relevant logs (sanitized of credentials).
- You've checked recent MT5 changelog / Python module changelog.

Don't ask before: the logs still say "see `brain.err`" and you haven't read it. 90% of bugs are in the logs.

## 19. Common bugs by file

- `trend_master_brain.py` — wrong symbol, path mismatch, feature lookahead, not handling MT5 disconnect.
- `multi_agent.py` — sign confusion on vote (+1/-1 mapping), warm-up NaN returning non-zero accidentally.
- `AI_SUPERBB_v14_TrendMaster.mq5` — handle `INVALID_HANDLE` not guarded, `OnInit` returning `INIT_FAILED` without message, buffer shift off-by-one.
- `config/settings.py` — path differs between dev and prod boxes.
- `.set` file — stale, not in sync with code.

## 20. GitHub-style incident postmortem template

After any 2h+ outage, fill this out:

```
# Incident: <title>
Date: 2026-04-22
Duration: 11:05 – 13:20 IST (2h 15m)
Severity: [sev2 — trading halted, no losses]

## Summary
One-paragraph description.

## Timeline
- 11:05: Dashboard alert fired — signal age > 60s
- 11:10: Investigated; brain running, MT5 session dropped
- ...

## Root cause
...

## What worked
- Health check script spotted it within 5m

## What didn't
- Auto-reconnect logic had a silent exception path

## Action items
- [ ] Add exception handler to ensure_connected()
- [ ] Add "mt5_connected" gauge to Prometheus
- [ ] ...
```

Commit to `docs/incidents/` so the next person sees what broke last time.

## Extension workflow

Adding a new failure mode:

1. Observe the symptom — write it down exactly as it appears.
2. Reproduce deterministically (the hard part).
3. Add to this skill under the right section with: symptom → diagnostic → cause → fix.
4. If the diagnostic requires a new tool, write it and put it in `C:\Users\Ratanshila\check_*.ps1`.
5. If the bug recurred twice, automate detection (new Prometheus metric + alert) — `trading-deploy-monitor` has the pattern.
