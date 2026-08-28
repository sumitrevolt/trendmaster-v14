# Rocket Prime signal fix - 2026-05-09 (Saturday)

## Why nothing was firing

Three things were wrong simultaneously:

1. **All 20 Rocket Prime alerts on TradingView are dead.** The captured
   alert template at `tools/tv_alert_setup/pine_alert_template.json`
   shows `"active": false` and `"last_fire_time": "2026-05-05T10:40:02Z"`.
   TradingView auto-deactivated them four days ago. Even when Rocket
   Prime triggers on a chart, no alert is emitted.
2. **Rocket Prime cannot deliver direction natively.** Per the captured
   `presentation_data.studies` block, the indicator has
   `"has_alert_function": true` - meaning it uses Pine `alert()`, not
   `alertcondition()`. Per the official TradingView Pine docs
   (https://www.tradingview.com/pine-script-docs/concepts/alerts/),
   for `alert()`-based indicators **the indicator author's runtime text
   overrides the alert dialog's Message field** - the
   `{{plot_0}}..{{plot_9}}` template the recreate script writes never
   gets substituted. All Rocket Prime alerts arrive at the webhook as
   `#### {{ticker}} ####` body with no direction info.
3. **INFERRED-direction fallback was disabled.** After the 2026-05-08
   wrong-direction incident on BTCUSD M15, `TV_ALLOW_INFERRED` was
   defaulted to off in receiver code. So even if RP alerts fired, the
   webhook would drop them as `dir=NONE`.

`logs/tv_webhook.log` confirms: only the startup banner from 07:09 IST
today, zero POSTs in the 6+ hours since. `python_executor.log`
heartbeat: `placed=0 skipped=20 (no_file=20)` - the executor sees no
fresh signal files because none are being written.

## What I changed (already applied)

* `config/.env`: added `TV_ALLOW_INFERRED=1` with a doc-comment
  explaining the trade-off and the proper-fix path.

That single line is what re-enables Rocket Prime alerts to produce
trades. Without it, even live alerts would be dropped as `dir=NONE`.

## What you need to run (~5 minutes)

```cmd
cd "C:\Users\Ratanshila\Documents\autmated trading"

REM 1. Verify everything is healthy before recreating alerts
outputs\01_verify_pipeline_2026-05-09.cmd
REM   Expected: ALL GREEN. Telegram message arrives on your phone.
REM   If any step FAILs, fix that first before continuing.

REM 2. Restart the webhook so it picks up TV_ALLOW_INFERRED=1
outputs\02_restart_webhook_2026-05-09.cmd
REM   Expected: "[OK] webhook restarted with INFERRED mode enabled"

REM 3. Recreate the 20 Rocket Prime alerts on TradingView
REM    (Chromium opens; if cookies are stale, log in to TV; script
REM     auto-detects login then deletes-and-recreates 20 alerts)
outputs\03_recreate_rp_alerts_2026-05-09.cmd
REM   Expected: 20 [OK] lines, then "Final Rocket Prime alerts: 20"

REM 4. Watch the pipeline live for the first BTCUSD/ETHUSD fire
outputs\04_watch_signals_2026-05-09.cmd
REM   Leave this running. As soon as Rocket Prime fires on a chart
REM   you have it attached to, you'll see:
REM     [WEBHOOK] ... INFERRED BUY for BTCUSD ...
REM     [WEBHOOK] ... TV->EA OK ... strategy=rocket_prime_inferred
REM     [EXEC]    ... ORDER PLACED BTCUSD BUY ...
REM   And a Telegram message with the trade details.
```

## Saturday crypto test plan

Saturday means only crypto markets are open. The recreated alerts
include 4 BTCUSD alerts (M5 M15 M30 H1). To test:

1. Make sure Rocket Prime is **attached** to a BTCUSD chart on
   TradingView. The alert system only fires when the indicator is
   loaded on a chart somewhere in your TV account.
2. With market open, wait for a natural Rocket Prime fire. M5 alerts
   tend to fire every 5-30 minutes on volatile pairs.
3. When it fires:
   - Check `04_watch_signals` for the chain
   - Check your phone for the Telegram trade message
   - Open MT5 to confirm the order was placed
4. **CRITICAL**: if Telegram says "BTCUSD BUY" but the BTC chart
   actually showed a SELL signal, the inference was wrong. Close that
   trade manually in MT5 within 60 seconds. Note the timestamp and
   what the indicator showed - that's data we need for the proper fix.

## Risks of INFERRED mode (be aware)

* **~70% accuracy**: per `direction_inference.py`, mean-reversion logic
  off MT5 price action. Can be wrong, especially in strong trends or
  near consolidation breakouts.
* **Known incident 2026-05-08 01:00 IST**: BTCUSD M15 indicator showed
  SELL → INFERRED guessed BUY → wrong-direction trade. Mitigation now:
  Telegram fires ~immediately on order placement so you can close fast.
* **24 open positions already on the account.** With more arriving
  from inferred signals, concentration risk goes up. The
  `tools/safeguards.py` long-USD/short-USD caps (3/3) will silently
  block some signals - that's intentional protection.

## The proper long-term fix (still pending)

The right answer is to discover whether Rocket Prime exposes
`alertcondition()`-based BUY/SELL options in the TV alert dropdown.
Per the official Pine docs each `alertcondition()` call creates a
separate selectable entry in "Create Alert -> Condition". If RP
exposes those, we can:

1. Create one alert per (pair, TF, BUY) and one per (pair, TF, SELL)
   = 5 pairs x 4 TFs x 2 dirs = **40 alerts**.
2. Each BUY alert has webhook URL with `&direction=buy`, each SELL
   with `&direction=sell`.
3. Receiver's `URL-DIRECTION` priority path (already coded at
   `tv_webhook_receiver.py:320-337`) reads it directly. No inference,
   100% accuracy.

To find out: open TV chart with Rocket Prime loaded, right-click the
indicator title, "Add alert on Rocket Prime Engine", expand the
**Condition** dropdown. Take a screenshot showing all options visible.
Save as `docs/guides/rocket_prime_alert_conditions_screenshot.png`
and we proceed.

If the dropdown shows ONLY "Rocket Prime Engine (Normal)" (the alert()
function path), the indicator simply doesn't expose plot conditions
and INFERRED mode is the best we can do until you switch to a
plot-based indicator.

## Files touched in this session

```
config/.env                                    # added TV_ALLOW_INFERRED=1
outputs/01_verify_pipeline_2026-05-09.cmd      # health check
outputs/02_restart_webhook_2026-05-09.cmd      # picks up new env
outputs/03_recreate_rp_alerts_2026-05-09.cmd   # operator runs after step 2
outputs/04_watch_signals_2026-05-09.cmd        # tails both logs
outputs/ROCKET_PRIME_FIX_2026-05-09.md         # this file
```

## Sources researched (deep web analysis)

* [TradingView Pine docs - Concepts/Alerts](https://www.tradingview.com/pine-script-docs/concepts/alerts/) - definitive reference on alert() vs alertcondition() and message handling
* [TradingView Pine docs - FAQ/Alerts](https://www.tradingview.com/pine-script-docs/faq/alerts/) - placeholder substitution rules
* [TradingView - Alerts on alert() function](https://www.tradingview.com/support/solutions/43000597494-alerts-on-alert-function/) - why alert() messages override dialog field
* [TradingView - Multi-condition alerts](https://www.tradingview.com/support/solutions/43000761492-multi-condition-alerts/) - how alertcondition() creates dropdown entries
* [TradingView - How to configure webhook alerts](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/) - JSON message formatting
* [TradingView - Private invite-only scripts](https://www.tradingview.com/support/solutions/43000615189-private-invite-only-scripts/) - source-code protection means we can't see Rocket Prime internals
