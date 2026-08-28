# TradingView 5-pair Rocket Prime alert setup -- 2026-05-06

**Goal:** 20 alerts (5 pairs x 4 TFs) firing through `shadow-cosmos-unending.ngrok-free.dev` to MT5.

**Pairs:** XAUUSD, EURUSD, USDJPY, GBPUSD, BTCUSD
**Timeframes:** M5, M15, M30, H1
**Indicator:** Rocket Prime Engine (Normal)

---

## Step 0 -- one-time prep (already done)

- Webhook live: `https://shadow-cosmos-unending.ngrok-free.dev/health` returns 200.
- End-to-end Format-B test passed (BUY signal -> tv_signals.jsonl -> MT5 file).
- `tools/tv_alert_setup/alerts_config.json` has all 20 entries pre-built.
- See `outputs/test_format_b.cmd` to re-verify the pipe at any time.

## Step 1 -- delete the existing 21 alerts

In TV (web or Desktop):

1. Click the alarm-clock icon on the right-rail toolbar to open the **Alerts** widget.
2. At the top of the widget, click the kebab menu (`...` / 3 dots) -> **"Remove all"** -> **"Yes"**.
3. If "Remove all" isn't visible, hover each row -> click the trash icon at the right edge of the row. 21 rows = ~1 min.

Verify the panel reads "No alerts" before continuing.

## Step 2 -- create the 20 fresh alerts

For EACH (symbol x TF) row in the table below, repeat this cycle:

1. Open the chart for that symbol on the listed timeframe.
2. Make sure **Rocket Prime Engine (Normal)** is loaded on the chart.
3. Press **Alt+A** -> the Create Alert dialog opens.
4. **Condition:** `Rocket Prime Engine (Normal)` -> `Any alert() function call`
5. **Trigger:** `Once per bar close` (recommended) or `Only once`.
6. **Expiration:** uncheck `Stop alert after expiration` so it persists indefinitely (or set 1 month + renew).
7. **Notifications -> Webhook URL:** paste the URL from the table for that row.
8. **Notifications -> Message:** leave EMPTY. Rocket Prime emits its own "Buy Observation @ price" text via `alert()` -- the receiver parses direction from that. If you overwrite, direction parsing breaks.
9. **Alert name:** `TrendMaster <SYM> <TF> RocketPrime`
10. Click **Create**.

After saving, the alert list panel should show the new row at the top with the bell icon.

### The 20 webhook URLs

| # | Pair | TF | Alert name | Webhook URL |
|---|------|-----|------------|-------------|
| 1 | XAUUSD | M5  | TrendMaster XAUUSD M5 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=XAUUSD&tf=5` |
| 2 | XAUUSD | M15 | TrendMaster XAUUSD M15 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=XAUUSD&tf=15` |
| 3 | XAUUSD | M30 | TrendMaster XAUUSD M30 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=XAUUSD&tf=30` |
| 4 | XAUUSD | H1  | TrendMaster XAUUSD H1 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=XAUUSD&tf=60` |
| 5 | EURUSD | M5  | TrendMaster EURUSD M5 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=EURUSD&tf=5` |
| 6 | EURUSD | M15 | TrendMaster EURUSD M15 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=EURUSD&tf=15` |
| 7 | EURUSD | M30 | TrendMaster EURUSD M30 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=EURUSD&tf=30` |
| 8 | EURUSD | H1  | TrendMaster EURUSD H1 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=EURUSD&tf=60` |
| 9 | USDJPY | M5  | TrendMaster USDJPY M5 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=USDJPY&tf=5` |
| 10| USDJPY | M15 | TrendMaster USDJPY M15 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=USDJPY&tf=15` |
| 11| USDJPY | M30 | TrendMaster USDJPY M30 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=USDJPY&tf=30` |
| 12| USDJPY | H1  | TrendMaster USDJPY H1 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=USDJPY&tf=60` |
| 13| GBPUSD | M5  | TrendMaster GBPUSD M5 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=GBPUSD&tf=5` |
| 14| GBPUSD | M15 | TrendMaster GBPUSD M15 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=GBPUSD&tf=15` |
| 15| GBPUSD | M30 | TrendMaster GBPUSD M30 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=GBPUSD&tf=30` |
| 16| GBPUSD | H1  | TrendMaster GBPUSD H1 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=GBPUSD&tf=60` |
| 17| BTCUSD | M5  | TrendMaster BTCUSD M5 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=BTCUSD&tf=5` |
| 18| BTCUSD | M15 | TrendMaster BTCUSD M15 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=BTCUSD&tf=15` |
| 19| BTCUSD | M30 | TrendMaster BTCUSD M30 RocketPrime | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=BTCUSD&tf=30` |
| 20| BTCUSD | H1  | TrendMaster BTCUSD H1 RocketPrime  | `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=BTCUSD&tf=60` |

## Step 3 -- end-to-end verification

After all 20 are saved:

1. From any saved alert in TV, right-click -> **Test alert** (TV fires it once with current price).
2. On your PC, run:
   ```cmd
   .venv\Scripts\python.exe tools\verify_tv_pipeline.py
   ```
3. Expected output: HTTP 200 from receiver, new line in `logs/tv_signals.jsonl` with `event:"write_ok"` and `tv_strategy:"rocket_prime_text"`.
4. EA picks up the next tick and either trades or rejects per gates (news blackout, vol regime).

## Tips

- **Pin a chart layout per symbol** so you don't have to re-add Rocket Prime on each one.
- **Save your alert template** in TV (the `Save as alert` 3-dot menu on an existing alert) so subsequent rows take ~10 sec each instead of 30 sec.
- **TV Pro plan** allows 100 active alerts; 20 fits with 80 spare.
- **The ngrok URL is permanent** (`shadow-cosmos-unending.ngrok-free.dev`) -- don't worry about restarts breaking it.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Alert fires in TV but nothing in `tv_signals.jsonl` | Webhook URL has typo or wrong secret | Re-paste the URL from this doc verbatim |
| `tv_signals.jsonl` shows `"direction":null` | Message field overridden, indicator's text discarded | Edit the alert -> Message field -> clear it -> Save |
| `auth_fail` count rising in receiver `/status` | Wrong secret in URL | The current secret is `5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14` |
| MT5 doesn't trade after webhook write_ok | News blackout / spread / volatility regime gate | Check `logs/trend_master_brain.out` for the rejection reason |
| BTCUSD chart not loading | OctaFX symbol vs TV exchange mismatch | Use BINANCE:BTCUSDT in TV chart but keep `&symbol=BTCUSD` in URL (broker-side) |

## Why we abandoned the Playwright auto-setup

Two TV UI surfaces broke during automation:

1. **Alert deletion** -- TV uses dynamic class hashes (`firstItem-RsFlttSS`, etc.) and hover-revealed action buttons. Playwright's hover/right-click did not trigger the action visibility reliably; the DOM scoping caught watchlist rows as false positives.
2. **Condition dropdown** -- The `Create Alert` dialog needs the Condition pre-set to Rocket Prime + sub-condition `Any alert() function call`. The script only fills name + webhook URL; if Condition defaults to a price comparison, alerts are saved against the wrong rule and never fire from Rocket Prime signals.

Manual setup gives you full control on the Condition dropdown, which matters more than saving 5 minutes.

The infrastructure (`tools/tv_alert_setup/{generate_alerts_format_b.py, setup_tv_alerts.py, delete_alerts_v2.py, reset_and_create.py}`) and `alerts_config.json` are in place for any future fix attempt.
