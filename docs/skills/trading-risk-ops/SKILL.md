---
name: trading-risk-ops
description: "Risk management and operational tooling for an MT5 + Python trading bot. Use when adding or reviewing position sizing, daily loss kill-switch, spread/session/news filters, chart-template (.chr) surgery, restart/health scripts, and the FastAPI dashboard. Covers the layer between the EA's signal and the actual send-order call, plus the Windows ops scripts that keep the whole stack alive."
---

# trading-risk-ops

The layer between "we got a signal" and "we actually send the order", plus the Windows-side ops glue that keeps the stack running. Getting signals right is half the job; getting risk and ops right is what separates a profitable backtest from a live system that doesn't blow up.

This skill codifies patterns from `AI_SUPERBB_v14_TrendMaster.mq5`'s risk block and the `C:\Users\Ratanshila\*.bat` / `*.ps1` ops scripts in this project.

## When to use

- Adding a risk filter (new-session guard, news-embargo window, spread spike block).
- Changing lot sizing from fixed to percent-equity or Kelly-bounded.
- Writing a daily kill-switch or DD-based cooldown.
- Building restart / health / log-rotation scripts.
- Editing a `.chr` chart template (tricky — it's UTF-16 LE with BOM).
- Adding a FastAPI endpoint to the dashboard.

## 1. Position sizing — percent-equity with floor/cap

Fixed lots are fine for a demo but not for a real account. Size by percent of equity per trade, with explicit floor and cap so you never trade size 0 or blow through the broker's max volume.

```cpp
// MQL5
double CalcLot(double sl_price, double entry_price)
{
    double equity     = AccountInfoDouble(ACCOUNT_EQUITY);
    double risk_cash  = equity * InpRiskPct / 100.0;           // e.g. 0.5%
    double tick_size  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double sl_dist    = MathAbs(entry_price - sl_price);
    if(sl_dist <= 0 || tick_size <= 0 || tick_value <= 0) return 0.0;

    double lot = risk_cash / (sl_dist / tick_size * tick_value);

    // Broker rounding
    double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double mn   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double mx   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    lot = MathFloor(lot / step) * step;
    lot = MathMax(mn, MathMin(mx, lot));

    // Project guard — never trade more than InpMaxLotCap
    return MathMin(lot, InpMaxLotCap);
}
```

**Rules of thumb:**

- `InpRiskPct` in [0.25, 1.0] for a real account, [0.5, 2.0] for a demo doing strategy testing.
- `InpMaxLotCap` = 10× the lot a 1% risk trade would produce at *half* your equity. This catches math bugs that would otherwise send a monster order.
- Round **down** not to nearest — rounding up exceeds your risk ceiling on low-equity accounts.

### Kelly bound (optional)

If you have a reliable historical win-rate `p` and win-loss ratio `b`, the Kelly fraction is `f = p - (1-p)/b`. **Always quarter-Kelly** in real trading (`f/4`), and cap at 2%. The full-Kelly number from a noisy backtest is a land-mine.

## 2. Daily kill-switch

One bad day can undo a good month. The EA must stop trading *automatically* when daily PnL breaches a floor.

```cpp
datetime today_start = 0;
double   day_start_equity = 0;
bool     trading_blocked_today = false;

void DailyRiskCheck()
{
    MqlDateTime t; TimeToStruct(TimeCurrent(), t);
    datetime today = StringToTime(StringFormat("%04d.%02d.%02d 00:00", t.year, t.mon, t.day));
    if(today != today_start) {
        today_start           = today;
        day_start_equity      = AccountInfoDouble(ACCOUNT_EQUITY);
        trading_blocked_today = false;
    }
    double eq   = AccountInfoDouble(ACCOUNT_EQUITY);
    double loss = day_start_equity - eq;
    if(loss >= day_start_equity * InpMaxDailyLossPct/100.0) {
        if(!trading_blocked_today) {
            PrintFormat("DAILY KILL: loss %.2f >= %.2f%% of start equity. No new trades today.",
                        loss, InpMaxDailyLossPct);
            trading_blocked_today = true;
        }
    }
}
```

Call `DailyRiskCheck()` from `OnTimer()` and short-circuit `TryEntry()` if `trading_blocked_today`. **Do not** close open trades on kill-switch — that can lock in losses at the worst moment. Just stop opening new ones.

A companion weekly kill (`InpMaxWeeklyLossPct`) is worth adding if you trade more than a few times per day.

## 3. Spread & session filters

Two filters that prevent the majority of "why did I take that garbage trade at 3am" losses.

```cpp
bool SpreadOK()
{
    long spread_pts = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
    if(spread_pts > InpMaxSpreadPoints) {
        DBG(StringFormat("spread %d > cap %d, skip", (int)spread_pts, InpMaxSpreadPoints));
        return false;
    }
    return true;
}

bool SessionOK()
{
    MqlDateTime t; TimeToStruct(TimeCurrent(), t);
    int hour = t.hour;    // server time, usually broker-GMT+2/3
    // Example: London + NY overlap only
    return hour >= InpSessionStartHour && hour < InpSessionEndHour;
}
```

**Points vs. pips:** spread from `SYMBOL_SPREAD` is in *points*, not pips. XAUUSD = 100 points per 1.00 price move. 500 points cap on XAUUSD = 5.00 USD spread — common during news. Don't confuse units here.

### News embargo

If you have an economic-calendar feed, block entries in a window around high-impact news:

```cpp
bool NewsClear()
{
    // pseudo: you'd have a list loaded from a CSV dropped by a Python fetcher
    datetime now = TimeCurrent();
    for(int i = 0; i < news_count; i++) {
        if(MathAbs(now - news_times[i]) < InpNewsEmbargoSec)
            return false;
    }
    return true;
}
```

The Python side of this is a daily fetch from ForexFactory (or a paid API) that writes `news.csv` to `MQL5/Files/`.

## 4. Trailing & break-even

Two independent functions, called from `OnTick` on a timer-throttled path.

```cpp
void ManageOpenPositions()
{
    for(int i = PositionsTotal()-1; i >= 0; i--) {
        ulong tkt = PositionGetTicket(i);
        if(!PositionSelectByTicket(tkt)) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
        if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;

        TryBreakEven(tkt);
        TryTrail(tkt);
    }
}
```

**Break-even:** once price moves N× ATR in your favour, move SL to entry + small buffer. The buffer (e.g. 3× tick_size) covers broker slippage on modify.

**Trailing:** use `max(current_sl, price - trail_atr * ATR)` for longs. Never loosen the stop. Modify only if the new SL differs by at least `min_modify_points` — excessive modifies get your account flagged.

## 5. Chart template (`.chr`) surgery

MT5 chart templates are **UTF-16 LE with BOM**. Reading them with `open(..., encoding='utf-8')` produces garbage and breaks MT5 when it re-loads the template.

```python
# Safe read/edit/write
CHR = r"C:\Users\...\MQL5\Profiles\Templates\my_chart.chr"

with open(CHR, "r", encoding="utf-16") as f:
    text = f.read()

# Flip a single key — ALWAYS match on the full line to avoid partial matches
text = text.replace(
    "InpRiskPct=1.0|0.0|0|0|N",
    "InpRiskPct=0.5|0.0|0|0|N",
)

with open(CHR, "w", encoding="utf-16") as f:    # encoding='utf-16' writes BOM
    f.write(text)
```

**Rules:**

- Always match whole line. `InpRisk=1` matches `InpRiskPct=1.0` too.
- MT5 must be closed, or the next template reload may overwrite your edit.
- Back up the file before bulk edits. A broken `.chr` silently prevents the EA from attaching.
- Values are `<value>|<start>|<step>|<stop>|<N>` — only the first field is the live value; the rest drive the Strategy Tester sweep.

## 6. Restart / health scripts (Windows)

Every bot needs three things you can run in one click:

### 6a. `restart_brain_only.bat`

```bat
@echo off
REM Force-kill any running brain, wipe stale state, restart clean.
taskkill /F /IM pythonw.exe /T 2>nul
taskkill /F /IM python.exe  /T 2>nul
timeout /t 3 /nobreak >nul
del /q "C:\path\to\brain.pid"  2>nul
del /q "C:\path\to\brain.err"  2>nul
start "" /B pythonw C:\path\to\ai_trading_agents\trend_master_brain.py
start "" /B pythonw C:\path\to\tools\dashboard.py
echo Brain + dashboard restarted.
```

### 6b. `check_brain.bat`

```bat
@echo off
echo === processes ===
tasklist | findstr /I "pythonw terminal64"
echo === brain.err tail ===
powershell -NoProfile -Command "Get-Content 'C:\path\to\brain.err' -Tail 20"
echo === dashboard ===
powershell -NoProfile -Command "try { (Invoke-WebRequest http://localhost:8000/api/state -TimeoutSec 2).StatusCode } catch { 'DOWN' }"
echo === signal age ===
powershell -NoProfile -Command "$f='C:\path\to\MQL5\Files\trendmaster_signals.json'; if(Test-Path $f){ [math]::Round(((Get-Date) - (Get-Item $f).LastWriteTime).TotalSeconds,1) } else { 'missing' }"
```

Signal age > ~10 s means the brain is dead. This is the most useful single health signal the whole system exposes.

### 6c. `restart_all.bat`

Full stack restart (brain **and** MT5):

```bat
@echo off
taskkill /F /IM terminal64.exe /T 2>nul
taskkill /F /IM pythonw.exe   /T 2>nul
taskkill /F /IM python.exe    /T 2>nul
timeout /t 4 /nobreak >nul
start "" "C:\Program Files\OctaFX Copytrade MetaTrader 5\terminal64.exe"
timeout /t 6 /nobreak >nul
start "" /B pythonw C:\path\to\ai_trading_agents\trend_master_brain.py
start "" /B pythonw C:\path\to\tools\dashboard.py
```

**Windows gotchas:**

- `taskkill /T` kills the tree; without it orphan subprocesses linger.
- Never use `$_` or `$variable` interpolation if invoking PowerShell from a sandbox that may strip it — move the logic into a `.ps1` file and invoke with `-File`.
- `start "" /B <exe>` detaches from the batch session so the script exits promptly.

## 7. FastAPI dashboard

Minimal single-file dashboard that reads the brain's state files — no database, no auth, localhost-only.

```python
# tools/dashboard.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn, json, time, os

SIGNAL  = r"C:\path\to\MQL5\Files\trendmaster_signals.json"
DEBUG   = SIGNAL.replace(".json", ".debug.json")

app = FastAPI()

@app.get("/api/state")
def state():
    out = {"now": time.time()}
    for name, path in (("signal", SIGNAL), ("debug", DEBUG)):
        if os.path.exists(path):
            with open(path) as f:
                try: out[name] = json.load(f)
                except Exception as e: out[name] = {"error": str(e)}
            out[name + "_age_sec"] = round(time.time() - os.path.getmtime(path), 2)
        else:
            out[name] = None
    return out

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!doctype html><meta charset=utf-8><title>TrendMaster</title>
    <h3>TrendMaster dashboard</h3>
    <pre id=out>loading...</pre>
    <script>
      async function pull() {
        const r = await fetch('/api/state'); const j = await r.json();
        document.getElementById('out').textContent = JSON.stringify(j, null, 2);
      }
      pull(); setInterval(pull, 2000);
    </script>"""

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
```

Bind to `127.0.0.1`, not `0.0.0.0`. A trading bot's dashboard should never be reachable from the LAN — it leaks your balance and your positions.

## 8. Logging discipline

One log file per process, rotated daily. `utf-8` for Python, `CP_UTF8` via `FileOpen` in MQL5.

- Python: `RotatingFileHandler(brain.log, maxBytes=5_000_000, backupCount=7)`
- MQL5: `Print` goes to the Experts tab; for the file log, open with `FileOpen("ea.log", FILE_WRITE|FILE_READ|FILE_TXT|FILE_COMMON)` so the file lives under `C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\Common\Files\` and is easy to find.

**Never** log full account balance or trade IDs at INFO level if the logs might leave the machine (screenshots in bug reports, etc.). Use `DEBUG` and strip before sharing.

## 9. Common ops bugs

- **Brain running, EA seeing stale signal** → usually the brain's working directory changed and the path to `trendmaster_signals.json` is wrong. Log the absolute path on startup.
- **Orders rejected with retcode 10016 (invalid stops)** → your SL/TP is inside the `SYMBOL_TRADE_STOPS_LEVEL` minimum. Query that value and clamp.
- **MT5 AutoTrading off after restart** → EA runs but `OrderSend` silently noops. Check `TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)` in OnInit and scream if false.
- **PowerShell health check always "DOWN"** → dashboard is bound to `0.0.0.0` but firewall blocks localhost paradoxically; switch to `127.0.0.1`.
- **`.chr` file rejected silently** → BOM missing after UTF-8 save; re-save with `utf-16`.

## 10. GitHub references

- `jimtin/algorithmic_trading_bot` — clean position-sizing + trade-state machine.
- `EA31337/EA31337-libre` — enormous library; read `Trade.mqh` for modify/trail patterns worth borrowing.
- `TysonRayles/mql5-dashboard` — lightweight chart-embedded stats panel (pure MQL5 if you want to avoid Python).

## Extension workflow

Adding a new risk filter:

1. Write a `bool FilterOK()` function that returns true when entry is allowed.
2. Add to the **top** of the `TryEntry` funnel so cheap checks short-circuit before expensive ones.
3. Add a `Print`/`DBG` line that says *why* it blocked — silent filters are the worst ops experience.
4. Expose an `InpUseX` toggle so you can disable the filter without recompile.
5. Add a backtest-friendly equivalent (same logic, different source of truth for data) or the filter silently skews backtest vs. live.
