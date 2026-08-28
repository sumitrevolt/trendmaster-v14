# TradingView alert setup automation

Semi-automates creating the 76 webhook alerts in TradingView (19 pairs × 4 timeframes M5/M15/H1/H4).

**Why semi-auto:** TradingView has anti-bot detection. Full automation = CAPTCHAs + temporary account locks. This script fills the form for you and pauses for you to click "Create" — the bot-detection signal of "human reviewed each alert" keeps you safe.

**Time estimate:** ~3-5 sec per alert click after setup ≈ **10 minutes total** for all 76.

---

## One-time install

```cmd
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM Install Playwright + headed Chromium (one-time, ~150 MB download)
.venv\Scripts\pip.exe install playwright
.venv\Scripts\playwright.exe install chromium
```

## Step 1 — Generate alert specs

Reads your symbols from `team_params.py` and webhook config from `config\.env`. Run once (re-run if you change symbols/TFs):

```cmd
.venv\Scripts\python.exe tools\tv_alert_setup\generate_alerts_config.py --strategy-mode
```

Options:
- `--strategy-mode` — emits 1 alert per (symbol, TF), 76 total. Use this if your TradingView indicator is a **strategy script** (it knows whether to fire BUY or SELL on its own and outputs `{{strategy.order.action}}`).
- *(default)* — emits 2 alerts per (symbol, TF), one BUY + one SELL hardcoded. **152 total.** Use this if your indicator is a plain alert-condition script that doesn't expose direction.
- `--timeframes M5,M15,H1,H4` — change TF set
- `--directions BUY,SELL` — change directions

Output: `tools\tv_alert_setup\alerts_config.json` with all entries pre-filled (correct webhook URL, secret, message body per symbol).

## Step 2 — Run the setup script

**First run only:** browser opens fresh. You log into TradingView manually + add your indicator(s) to one chart so "Create alert" has a condition to attach to. Then press Enter to begin the loop.

```cmd
.venv\Scripts\python.exe tools\tv_alert_setup\setup_tv_alerts.py
```

Per-alert flow:
1. Script navigates to chart for that (symbol, TF).
2. Hits Alt+A to open the alert dialog.
3. Fills the alert name, webhook URL, message body for you.
4. **Pauses.** You verify the dialog looks right and click **"Create"** yourself.
5. Press Enter in the script terminal → moves to next alert.
6. Type `s` + Enter to skip the current alert. Type `q` + Enter to quit.

Checkpoint file `alerts_done.json` tracks completed IDs. If the script crashes or you quit, just re-run — it resumes automatically.

## Useful flags

```cmd
REM Dry-run (print all 76 entries, no UI)
.venv\Scripts\python.exe tools\tv_alert_setup\setup_tv_alerts.py --dry-run

REM Resume after manual interrupt (skip first 24)
.venv\Scripts\python.exe tools\tv_alert_setup\setup_tv_alerts.py --start-from 24

REM Only one symbol (testing)
.venv\Scripts\python.exe tools\tv_alert_setup\setup_tv_alerts.py --filter-symbol XAUUSD

REM Only one timeframe across all symbols
.venv\Scripts\python.exe tools\tv_alert_setup\setup_tv_alerts.py --filter-tf M15

REM HIGH-RISK auto-confirm (no pause; clicks Create programmatically)
.venv\Scripts\python.exe tools\tv_alert_setup\setup_tv_alerts.py --auto-confirm
```

## When things go wrong

### TradingView UI changed and selectors don't match

Edit the `_step_*` / `_fill_*` functions in `setup_tv_alerts.py`. Each helper fails gracefully with `[warn]` so you can paste manually — script still proceeds, just less automated.

### CAPTCHA / "unusual activity"

Stop immediately. Wait ~1 hour. Reduce concurrency by adding `time.sleep()` between symbols. Avoid `--auto-confirm`.

### "Symbol not found"

Your TradingView account doesn't have access to the exchange:symbol combination the script tried. Edit `generate_alerts_config.py::_broker_exchange()` and `_broker_symbol()` to use exchanges your account supports. The default uses `OANDA:` for FX (most universal), `BINANCE:` for crypto, `TVC:` for energy.

### Browser profile got messed up

Delete `tools\tv_alert_setup\_browser_profile\` and re-run. You'll need to log in to TV again on first run.

## What the script does NOT touch

- Your real Chrome browser profile (uses an isolated profile dir)
- Your MetaTrader 5 (separate process, not browser-based)
- Any indicator code on TV (you must already have your indicator(s) on a chart)
- Any alerts you've already created (won't dedupe — TV allows multiple alerts with same name)

## Final verification

After all 76 alerts are saved, fire one from TradingView (right-click your indicator → "Test alert"). Then:

```cmd
.venv\Scripts\python.exe tools\verify_tv_pipeline.py
```

The (symbol × timeframe) coverage matrix should now show signals streaming in.
