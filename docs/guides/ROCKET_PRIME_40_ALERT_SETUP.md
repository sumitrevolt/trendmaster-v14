# Rocket Prime 40-alert setup — proper TV chain fix

**Status:** Pending operator manual step
**Created:** 2026-05-09 00:50 IST
**Why this exists:** Rocket Prime is invite-only and uses Pine `alert()` function calls
internally. TradingView ignores the alert dialog "Message" field for `alert()`-driven
alerts and sends the indicator's hardcoded `#### {{ticker}} ####` text. The
`{{plot_0}}..{{plot_9}}` placeholders we set on the alerts via API are never
substituted. Direction info never reaches the webhook.

The fix: switch the alert CONDITION from "Any alert() function call" (which uses Pine
`alert()`) to a plot-crossing condition (which substitutes placeholders normally).
TradingView allows plot-crossing conditions on indicators that expose plots — and
Rocket Prime does, per the historical body samples in `logs/tv_plot_values.jsonl`
(p0 = BUY, p1 = SELL).

Result: 2 alerts per pair-tf instead of 1 → 5 pairs × 4 TFs × 2 dirs = **40 alerts**.

## What you need to do (one-time, ~5 min in TV UI)

The challenge is we don't know what conditions Rocket Prime exposes in TradingView's
alert dropdown. The pine_alert_template.json shows only "Rocket Prime Engine (Normal)"
which is the alert() function condition. We need to find out:

  1. Does Rocket Prime expose plot-by-plot conditions in TV's alert dropdown?
  2. If yes, what are the plot names?
  3. If no, alternative paths (see "Fallback strategies" below).

### Step 1: Check what alert conditions Rocket Prime exposes

1. Open https://www.tradingview.com/chart/ in your browser.
2. Add Rocket Prime to any chart (e.g., XAUUSD H1).
3. Right-click on the indicator title → "Add alert on Rocket Prime Engine".
4. In the alert dialog, look at the **Condition** dropdown.
5. **Take a screenshot** of the full dropdown (should be open showing all options).
6. Save as `docs/guides/rocket_prime_alert_conditions_screenshot.png` and
   share with Claude in next session.

If the dropdown shows ONLY "Any alert() function call", the indicator does NOT
expose plot conditions. Skip to "Fallback strategies".

If the dropdown shows entries like "plot 0 crossing up" / "plot 1 crossing up" /
"Buy Signal" / "Sell Signal" — perfect, proceed to step 2.

### Step 2: Manually create one BUY alert and one SELL alert

For one pair/TF (e.g., XAUUSD H1):

  - **BUY alert:**
    - Condition: pick the plot/option that fires only on BUY events
    - "Once Per Bar Close" or "Once Per Bar" (whichever Rocket Prime supports)
    - Webhook URL: `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=<TV_WEBHOOK_SECRET>&symbol=XAUUSD&tf=60&direction=buy`
    - Message: leave empty (URL has direction)
    - Save

  - **SELL alert:**
    - Same but pick the SELL plot/condition
    - URL ends with `&direction=sell`
    - Save

### Step 3: Capture both alert payloads programmatically

Run:

```cmd
cd "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe outputs\capture_rocket_prime_templates_2026-05-09.cmd
```

This launches a Playwright headed browser. **Recreate the same two alerts** while
the browser is watching. The script intercepts the POST payload, saves them as:

  - `tools/tv_alert_setup/pine_alert_buy_template.json`
  - `tools/tv_alert_setup/pine_alert_sell_template.json`

### Step 4: Auto-create the remaining 38 alerts

Run:

```cmd
.venv\Scripts\python.exe outputs\create_40_alerts_2026-05-09.cmd
```

This:

  1. Deletes the existing 20 alerts (which fire on alert() calls and don't deliver direction)
  2. Creates 40 new alerts from the buy + sell templates, substituting symbol/TF
  3. Verifies each alert has the right webhook URL with `?direction=buy|sell`

### Step 5: Wait for first signal + verify

Watch:

```cmd
powershell -Command "Get-Content 'logs\tv_webhook.log' -Tail 5 -Wait"
```

Expected new line on first Rocket Prime signal:

```
[INFO] URL-DIRECTION BUY for XAUUSD tf=60 (no inference needed)
[INFO] TV→EA OK  symbol=XAUUSD dir=BUY tf=H1 conf=0.95 ... strategy=rocket_prime_url_direction
```

Then in `python_executor.log`:

```
[INFO] ORDER PLACED XAUUSD BUY ...
```

## Fallback strategies

If step 1 reveals Rocket Prime exposes ONLY "alert() function call" (no plot conditions):

### Option A: Use INFERRED mode (warning: may give wrong direction sometimes)

Edit `config/.env` and set:

```
TV_ALLOW_INFERRED=1
```

Then restart the webhook receiver. Rocket Prime alerts will arrive as
`#### {{ticker}} ####` and the receiver will infer direction from MT5 price action
(mean-reversion logic in `direction_inference.py`). Accuracy is ~70% (per memory
entry `project_2026-05-08_inferred_mode_inversion_incident.md` — once gave wrong
direction on BTCUSD M15).

### Option B: Switch to a different indicator that exposes plots properly

Many free Pine indicators expose named plots and DON'T use `alert()` calls. If you
have a fallback indicator with similar logic, point alerts at that one instead.

### Option C: Stay on local_generator (uncomment in ALLOWED_STRATEGIES)

If Rocket Prime can't deliver direction and INFERRED mode is too risky, the
practical path is to keep `local_generator` (transparent EMA-cross + RSI50 + ATR
filter, see `tools/local_signal_generator.py:21-27`). Re-enable by uncommenting
`"local_generator"` in `tools/python_signal_executor.py:362` and re-enabling the
schtask.

## Memory entries to read first

Future Claude sessions: before re-walking this ground, read in order:

  1. `project_2026-05-09_local_generator_whitelist_killer_bug.md` — the 5-day silent failure
  2. `project_2026-05-08_tv_alert_template_no_direction.md` — original TV chain diagnosis
  3. `project_2026-05-08_inferred_mode_inversion_incident.md` — why INFERRED is risky
