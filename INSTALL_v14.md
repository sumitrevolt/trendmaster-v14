# TrendMaster v14 — Install Log (what I already did for you)

**Date:** 2026-04-20
**Machine:** `C:\Users\Ratanshila\Documents\autmated trading`
**MT5 data_path:** `C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075`

---

## ✅ Already done — no action needed

| Step | Result |
|---|---|
| Install LightGBM | lightgbm 4.6.0 installed |
| Copy `AI_SUPERBB_v14_TrendMaster.mq5` → `MQL5\Experts\` | 36,613 bytes copied |
| Compile EA with MetaEditor64.exe | **`AI_SUPERBB_v14_TrendMaster.ex5` generated — 87,210 bytes** |
| Start Python brain in background | Running, PID in `logs\brain.pid` |
| Verify signal file refreshes | Confirmed — `trendmaster_signals.json` updates every 250 ms |
| Verify legacy `main.py` / `ai_swarm_main.py` are gated | Both exit with the "LEGACY disabled" banner |

The brain log lives at `logs\trend_master_brain.err` (Python logging writes to stderr).
The signal file lives at
`C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\trendmaster_signals.json`.

Example current contents:
```
{"direction":"NONE","confidence":0.8,"ts":1776676242,"symbol":"XAUUSD","brain":"TrendMaster_v14","model":"rule"}
```

`NONE` is correct right now — the 3-of-3 conditions are not all aligned. It will flip to BUY/SELL the moment trend + volatility + momentum line up.

---

## 📋 What only you can do (MT5 GUI steps)

These steps require manual interaction with the MT5 terminal UI — I can't drag-and-drop or click buttons for you.

### 1. Refresh the Navigator panel in MT5
- In MT5, press `Ctrl + N` (or View → Navigator).
- Right-click **Expert Advisors** → **Refresh**.
- You should see `AI_SUPERBB_v14_TrendMaster` (no red ✗ icon means compile is healthy).

### 2. Attach the EA to an XAUUSD M5 chart
- Open an **XAUUSD M5** chart (File → New Chart → XAUUSD → M5).
- Drag `AI_SUPERBB_v14_TrendMaster` from Navigator onto the chart.
- In the input-parameters dialog, set:
  - `InpMagic = 20260420`
  - `InpRiskPct = 1.0`
  - `InpUseAIGate = true`
  - `InpAIRequired = false` _(start advisory; flip to true after ~40 trades)_
  - Leave everything else at defaults.
- Click **OK**.

### 3. Enable AutoTrading
- Top toolbar → click the **AutoTrading** button (becomes green).
- In the EA's chart header, within a minute you should see a line like:
  `TrendMaster v14 | C1:OK C2:-- C3:OK | AI:BUY 0.71`.

### 4. Verify the handshake
- Check the **Experts** tab at the bottom of MT5. You should see log lines from the EA.
- If the brain log shows `direction=BUY` with conf ≥ 0.58, and the chart header shows `AI:BUY 0.XX` matching — handshake works.

---

## 🛠 Operating it day-to-day

**Start the brain:** double-click `START_TRENDMASTER_v14.bat`
**Stop the brain:**  double-click `STOP_TRENDMASTER_v14.bat`
**Re-compile EA:** open MetaEditor (F4 in MT5), open the `.mq5` file, press F7.
**Watch the brain log:** `type logs\trend_master_brain.err` (or tail it in PowerShell:
`Get-Content logs\trend_master_brain.err -Wait -Tail 20`).

---

## 🧪 Train a real ML model (optional, do when you have time)

By default the brain runs a rule-based classifier. For an actual ML edge:

1. Export M5 OHLCV to a CSV with a datetime index and columns `open,high,low,close,volume`.
2. Run: `python ai_trading_agents\trend_master_brain.py train bars.csv`
3. The trained file `trend_master_model.lgb` is saved next to the brain and picked up automatically on next start.

---

## 🚨 If something's wrong

| Symptom | First thing to check |
|---|---|
| EA chart header shows `AI:NONE 0.50` constantly | Brain is running; market just isn't trending. This is correct behaviour, not a bug. |
| EA chart header shows `AI:STALE` | Brain isn't running or signal file is >60s old. Run `START_TRENDMASTER_v14.bat`. |
| Brain log says `mt5.initialize() failed` | MT5 terminal must be running and logged in before starting the brain. |
| EA `C1/C2/C3 -- -- --` | EA hasn't processed a bar yet. Wait for the next M5 close. |
| EA not placing trades but gates say OK | Check MT5's toolbar AutoTrading light is green, and the magic number matches `InpMagic=20260420`. |
