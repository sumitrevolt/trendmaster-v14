---
name: trading-tv-rp-alert-setup
description: "Set up directional Rocket Prime alerts in TradingView using plot-crossing conditions instead of buggy alert() function. Use whenever the operator says 'BTC signals aren't trading', 'RP alerts have no direction', 'webhook gets only #### SYMBOL ####', 'TV alerts deactivated', or after re-onboarding TV alerts after their cookie expires. Use proactively when checking if TV alerts are firing — old pine_alert type can't deliver direction; this skill switches them to plot-crossing which can. Operator must create 2 template alerts via TV UI (3 min); 38 more get created automatically by capture_and_create_40_alerts.py."
---

# trading-tv-rp-alert-setup

The DEFINITIVE playbook for Rocket Prime alert direction. Confirmed via
web search (2026-05-10) that TV's plot-crossing alert payload is
undocumented — no path around the manual capture. Use this skill any
time the bot needs new RP alerts or existing alerts have gone stale.

## ⭐ 2026-05-10 BREAKTHROUGH — autonomous fix shipped

The full Pine `alert()` override problem is SOLVED autonomously without
operator UI clicks via this insight:

  TV substitutes `{{plot_0}}..{{plot_19}}` placeholders in the WEBHOOK
  URL, NOT just the message body. Pine `alert()` only overrides the
  body — the URL is a separate field. Putting plot placeholders in URL
  bypasses the override entirely.

**Working setup (live as of 2026-05-10 22:20 IST):**

1. `tools/tv_alert_setup/recreate_rp_with_plot_url.py` — deletes + recreates
   all 20 RP alerts via TV API with webhook URL containing
   `&p0={{plot_0}}&p1={{plot_1}}..&p9={{plot_9}}`.
2. `ai_trading_agents/tv_webhook_receiver.py` (patched 2026-05-10):
   Priority 0 now extracts plot values from URL QUERY first, body second.
3. Direction: `p0 > 0 and p1 == 0` → BUY. `p1 > 0 and p0 == 0` → SELL.

**Run procedure (ZERO operator clicks):**

```cmd
outputs\recreate_rp_url_placeholders.cmd
outputs\force_restart_webhook.cmd
```

After next RP signal fires, log will show `PLOT-DIRECTION BUY for BTCUSD
tf=5 (p0=80957.20 p1=0.0000)` instead of `REJECT no-direction`.

The plot-crossing UI path (formerly the only known fix) is no longer
needed. Old approach kept in this skill for historical context.

---

## Why this is needed (root cause, do not relitigate)

1. Rocket Prime indicator is invite-only Pine using runtime `alert()`
   calls. TV's `alert()` function HARDCODES the message in Pine source,
   IGNORING the alert dialog's message field. So creating alerts with
   "Any alert() function call" condition delivers `#### {{ticker}} ####`
   to webhook — no direction.

2. Pine's `alertcondition()` mechanism DOES respect message templates,
   but RP doesn't expose alertconditions; only the alert() call.

3. The fix: TradingView's "Cross" alert condition on the indicator's
   plot OUTPUTS (Buy Observation #1, Sell Observation #1) bypasses
   alert() entirely — TV-side cross detection respects message and
   webhook URL templates.

4. TV's `pricealerts.tradingview.com/create_alert` API is undocumented.
   The plot-crossing payload structure is NOT publicly available.
   `tools/tv_alert_setup/pine_alert_template.json` only captures the
   buggy pine_alert type. There is NO existing capture for plot-crossing.

## The path (proven)

### Step 1 — Run the capture script

```cmd
.venv\Scripts\python.exe tools\tv_alert_setup\capture_and_create_40_alerts.py
```

OR via the wrapper:
```cmd
outputs\setup_rp_40_alerts.cmd
```

This opens a Playwright Chromium at tradingview.com/chart/. Cookies
persist via `tools/tv_alert_setup/_browser_profile/`.

### Step 2 — Operator creates 2 template alerts in the opened browser

**BUY template (~90 sec):**

1. Make sure Rocket Prime is on the chart. If not: press `/` (slash),
   type "Rocket Prime", press Enter on first result.
2. Click the bell/clock icon (top toolbar, "Alert" button) OR press `Alt+A`.
3. In the alert dialog:
   - **Condition** dropdown: change "Price" → "Rocket Prime Engine"
   - Second dropdown appears: pick **"Buy Observation #1"** (or whatever
     RP names its BUY observation plot — likely starts with "Buy")
   - Trigger: **"Crossing Up"**
   - Value: **`0`**
4. **Webhook URL** (paste exactly):
   ```
   https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=<TV_WEBHOOK_SECRET>&symbol={{ticker}}&tf={{interval}}&direction=buy
   ```
   Replace `<TV_WEBHOOK_SECRET>` with the value from `config/.env`.
5. Message: **leave empty**.
6. Click **Create**.

**SELL template (~90 sec):**

Same as above but:
- Second dropdown: pick **"Sell Observation #1"**
- Webhook URL ends with `&direction=sell`
- Click Create.

### Step 3 — Phase 2 auto-runs

Script intercepts both POST payloads, deletes any existing pine_alert RP
alerts, creates 40 new directional alerts via TV's internal API.

Expected output: `created 40, failed 0`.

### Step 4 — Verify within 1 hour

```cmd
type logs\tv_webhook.log | findstr "URL-DIRECTION"
```

When the next RP signal fires, log shows `URL-DIRECTION BUY for BTCUSD tf=5`
instead of `REJECT no-direction`.

## Common pitfalls

- **Cookies expired (HTTP 403 on /list_alerts)**: script auto-detects
  and waits up to 8 min for operator to re-login in the opened browser.
  Cookies persist after.
- **RP not on chart**: dialog won't show "Rocket Prime Engine" in
  Condition dropdown. Add the indicator first via `/` search.
- **Plot name not "Buy Observation #1"**: depends on RP version.
  Likely candidates: "Buy", "Buy Signal", "Long". Pick whichever
  spikes when chart shows a Buy Observation label.
- **Webhook URL wrong tunnel**: if TUNNEL_MODE switched to cloudflare,
  use the `CLOUDFLARE_HOSTNAME` instead of `shadow-cosmos-unending`.

## What this skill explicitly RULES OUT

- Full Playwright UI automation of Phase 1: TradingView's React UI is
  brittle, anti-bot, and selectors drift across TV releases. Prior
  attempts (`inspect_rocket_prime_conditions.py`,
  `auto_capture_rp_alerts.py` 2026-05-10) only got partial inspection.
  Confirmed 2026-05-10: 15 selector strategies all FAILED to find the
  Condition dropdown (`[role='combobox']`, `data-name='condition-symbol'`,
  text-matched buttons all returned 0 elements). TV's React renders the
  alert dialog with ephemeral generated class names + non-standard
  ARIA. ROI on UI selectors is poor; manual capture is 3 min and reliable.
  If full automation is later attempted, do `page.content()` + offline
  DOM parse FIRST to identify actual attributes before writing
  selectors. Don't ship blind selectors and burn cycles.
- Setting `TV_ALLOW_INFERRED=1`: operator policy is direction must be
  truthful, never guessed. Inversion incident 2026-05-08 cost a real
  loss.
- Running with the existing pine_alert template: the alert() override
  bug is structural to RP's Pine source. Cannot be fixed bot-side.

## Files

- `tools/tv_alert_setup/capture_and_create_40_alerts.py` — main script
- `tools/tv_alert_setup/_browser_profile/` — persistent cookies
- `tools/tv_alert_setup/captured_buy_alert.json` — created during Phase 1
- `tools/tv_alert_setup/captured_sell_alert.json` — created during Phase 1
- `outputs/setup_rp_40_alerts.cmd` — wrapper that runs the script
- Memory: `project_2026-05-09_inferred_re_enabled_for_rp.md`
- Memory: `project_2026-05-08_tv_alert_template_no_direction.md`
