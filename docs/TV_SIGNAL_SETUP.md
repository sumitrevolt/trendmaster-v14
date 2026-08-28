# TradingView signal mode — setup runbook

**Status:** added 2026-05-01. Replaces brain-driven entries with TradingView
alerts as the sole source of truth for direction. Brain runs in shadow mode
(logs predictions only) so future learning has the full prediction stream
paired against TV-driven outcomes.

**Why this exists:** 6 weeks of live trading with the rule + ML stack
produced 1 trade (ETHUSD 2026-04-17, -$0.69). Operator chose to delegate the
entry decision to TradingView and let the brain become a learner instead of
a decider.

---

## What got built

| Component | Path | Role |
|---|---|---|
| Executor | `ai_trading_agents/tv_executor.py` | translates TV alert → EA signal JSON in same format brain used |
| Webhook receiver | `ai_trading_agents/tv_webhook_receiver.py` | stdlib HTTP server on `127.0.0.1:5005`, no new deps |
| Brain shadow short-circuit | `trend_master_brain.py::write_signal` | when TV mode on, brain logs to `logs/brain_shadow_predictions.jsonl` instead of writing the EA file |
| Settings block | `config/settings.py::TV_SIGNAL` | flags |
| Launcher | `start_tv_webhook.cmd` | pre-flight + detached start + health check |
| Audit logs | `logs/tv_signals.jsonl`, `logs/tv_webhook.log` | every TV → EA hop and HTTP request |

The EA itself is **unchanged**. It still reads `trendmaster_signals_<SYMBOL>.json`
from the MT5 Files directory; tv_executor writes that file with `direction`,
`confidence`, `sl_atr_mult`, `tp_atr_mult`, and `require_all_3=False` (so the
EA's 3-of-3 quorum doesn't veto a TV signal).

---

## One-time setup

### Step 1 — generate a webhook secret

```cmd
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(24))"
```

Copy that 48-char hex string. Open `config\.env` and add:

```
TV_WEBHOOK_SECRET=<paste here>
TV_WEBHOOK_HOST=127.0.0.1
TV_WEBHOOK_PORT=5005
```

`HOST=127.0.0.1` is the safe default — only the local machine can reach it
directly. The tunnel (next step) bridges the public TV alert servers to it.

### Step 2 — install a tunnel

TradingView's webhook IPs need to reach your laptop. Pick one:

**Option A — ngrok (easiest, free tier OK)**

```cmd
:: Download from ngrok.com, then:
ngrok config add-authtoken <YOUR_TOKEN>
ngrok http 5005
```

Note the `https://*.ngrok-free.app` URL it prints. The free tier rotates the
URL each restart, so prefer the paid plan or Cloudflare for a stable URL.

**Option B — Cloudflare Tunnel (free, stable URL)**

```cmd
:: Download cloudflared.exe from cloudflare.com, then:
cloudflared tunnel login
cloudflared tunnel create trendmaster-tv
cloudflared tunnel route dns trendmaster-tv tv.<yourdomain>.com
cloudflared tunnel run --url http://localhost:5005 trendmaster-tv
```

You now have a stable `https://tv.<yourdomain>.com` URL.

### Step 3 — start the webhook

```cmd
start_tv_webhook.cmd
```

You should see:

```
[OK] PRE-FLIGHT: webhook receiver imports cleanly.
[OK] health: {"status":"ok","ts":...}
=== DONE — webhook live. ===
```

If that fails, tail `logs\tv_webhook.err` for the traceback.

### Step 4 — sanity-test with curl

Substitute `<SECRET>` with what you put in `.env`:

```cmd
curl -X POST http://127.0.0.1:5005/tv-signal ^
  -H "Content-Type: application/json" ^
  -d "{\"secret\":\"<SECRET>\",\"symbol\":\"XAUUSD\",\"direction\":\"buy\"}"
```

Expected response:

```json
{"status":"ok","symbol":"XAUUSD","direction":"BUY","confidence":0.95,"ts":...}
```

Verify the EA signal file got written — check `logs\tv_signals.jsonl`:

```cmd
powershell -Command "Get-Content logs\tv_signals.jsonl -Tail 1"
```

Should show one `event:write_ok` line.

### Step 5 — configure the TradingView alert

In TradingView, open your strategy or indicator → "Add Alert" (alarm-clock
icon). Set:

* **Condition:** your strategy/indicator + the trigger you want (e.g. "Order
  fills only" for strategies, or "Once Per Bar Close" for indicators)
* **Webhook URL** (Notifications tab): your ngrok / Cloudflare URL +
  `/tv-signal`. e.g. `https://tv.example.com/tv-signal`
* **Message:** paste **one** of the templates below

#### Template A — Pine **strategy** alert (recommended)

```json
{
  "secret":"YOUR_SECRET",
  "symbol":"{{ticker}}",
  "direction":"{{strategy.order.action}}",
  "price":{{close}},
  "tv_strategy":"{{strategy.order.comment}}",
  "tv_alert_ts":{{timenow}}
}
```

`{{strategy.order.action}}` resolves to `buy` or `sell`. The executor
normalises both directions.

#### Template B — plain **indicator** alert (one alert per direction)

Create two alerts on the same indicator — one for BUY, one for SELL — and
hardcode the direction in each:

```json
{"secret":"YOUR_SECRET","symbol":"{{ticker}}","direction":"buy","price":{{close}},"tv_alert_ts":{{timenow}}}
```

```json
{"secret":"YOUR_SECRET","symbol":"{{ticker}}","direction":"sell","price":{{close}},"tv_alert_ts":{{timenow}}}
```

#### Template C — close / flatten

To force the EA back to flat on a TV exit signal:

```json
{"secret":"YOUR_SECRET","symbol":"{{ticker}}","direction":"close"}
```

`close`, `flat`, `none`, `exit` all map to direction `NONE` which the EA
reads as "no entry permission".

---

## Symbol mapping — TradingView vs OctaFX-Demo

The executor whitelists the 19 broker symbols. Your TV alert must send
**broker** symbols (the names that appear in MT5 Market Watch), not TV's
display names. Common gotchas:

| TradingView default | OctaFX-Demo / our whitelist |
|---|---|
| `XAUUSD`, `GOLD`, `OANDA:XAUUSD` | use `XAUUSD` |
| `XAGUSD`, `SILVER` | `XAGUSD` |
| `BTCUSD`, `BITSTAMP:BTCUSD` | `BTCUSD` |
| `ETHUSD` | `ETHUSD` |
| `USOIL`, `WTICOUSD`, `XTIUSD` | `XTIUSD` |
| `UKOIL`, `BRENT` | `XBRUSD` |
| `NATGAS`, `XNGUSD` | `XNGUSD` |
| `EURUSD` … | use the exact 6-letter pair |

The simplest approach: in your TV chart, **change the symbol shown in the
ticker** to match the broker symbol exactly, then `{{ticker}}` will resolve
correctly. Otherwise add a Pine variable that overrides the symbol string
sent to the webhook.

If a TV alert hits with a non-whitelisted symbol, the receiver responds
`422 {"error":"rejected","detail":"symbol_not_whitelisted: <name>"}` and
nothing is written.

---

## Activation (the actual flip)

1. Edit `config\settings.py`:

   ```python
   TV_SIGNAL = {
       "enabled": True,         # ← was False
       "shadow_brain": True,
       ...
   }
   ```

2. Restart the brain so the shadow mode kicks in:

   ```cmd
   start_brain_clean.cmd
   ```

3. Verify shadow mode is live:

   ```cmd
   powershell -Command "Get-Content logs\trend_master_brain.out -Tail 5"
   ```
   The brain should still log `tick_once` lines but `logs\brain_shadow_predictions.jsonl`
   should accumulate one record per tick instead of `trendmaster_signals_*.json`
   files getting touched.

4. Wait for a real TV alert. When one fires:
   * `logs\tv_webhook.log` — `TV→EA OK symbol=XAUUSD dir=BUY ...`
   * `logs\tv_signals.jsonl` — one `event:write_ok` record
   * The EA picks up the signal on its next tick and trades per its risk +
     order-management code (per-team cap=2, RISK.risk_pct=0.5%, ATR-based
     SL/TP from team_params.py).

---

## Monitoring

```cmd
:: Tail webhook activity
powershell -Command "Get-Content logs\tv_webhook.log -Wait -Tail 10"

:: Tail every TV→EA hop (audit)
powershell -Command "Get-Content logs\tv_signals.jsonl -Wait -Tail 5"

:: What would the brain have done? (shadow predictions)
powershell -Command "Get-Content logs\brain_shadow_predictions.jsonl -Wait -Tail 5"

:: Live trade tracker (independent of TV — this is broker reality)
.venv\Scripts\python.exe tools\diagnose_zero_trades.py
```

---

## Rollback

If TV signals are misbehaving, flip back to brain mode:

1. `config\settings.py` → `TV_SIGNAL["enabled"] = False`
2. `start_brain_clean.cmd`
3. Optionally stop the webhook: kill the `TV_Webhook - LIVE` window or
   `taskkill /F /FI "WINDOWTITLE eq TV_Webhook - LIVE"`

The brain resumes writing the EA signal JSON and the EA is none the wiser
about which side of the flag it's on — same file, same format.

---

## Free-plan / Essential-trial path — Gmail IMAP poller

If your TradingView plan does NOT include webhook URL (Free / Essential
without webhook), use this path. Latency ~10–20 s instead of webhook's
~1 s, but works on any TV plan that supports email alerts.

### Step 1 — Gmail App Password

1. https://myaccount.google.com/security
2. Enable **2-Step Verification** (mandatory before App Passwords appear)
3. Search the page for **App passwords** → click
4. App name: `TrendMaster` → **Create**
5. Copy the 16-character string (NOT your real Gmail password)

### Step 2 — paste into config\.env

The placeholder lines were already added by the setup. Replace
`PASTE_16_CHAR_APP_PASSWORD_HERE` with the password from Step 1:

```
TV_EMAIL_USER=you@gmail.com
TV_EMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx     ← paste here, no spaces
TV_EMAIL_IMAP_HOST=imap.gmail.com
TV_EMAIL_IMAP_PORT=993
```

### Step 3 — flip the flags in config\settings.py

```python
TV_SIGNAL = {
    "enabled": True,            # was False
    "shadow_brain": True,
    ...
}
TV_EMAIL = {
    "enabled": True,            # was False
    ...
}
```

### Step 4 — start the poller

```cmd
start_tv_email.cmd
```

Pre-flight will fail loudly if creds are wrong; if it succeeds you'll see
`[OK] IMAP login + INBOX select succeeded`.

### Step 5 — restart the brain (so shadow mode kicks in)

```cmd
start_brain_clean.cmd
```

### Step 6 — configure the TV alert

Same as the webhook path, except in the alert dialog you do **NOT** check
the Webhook URL box. Instead:

* **Notifications** → check **Send email** ✓
* **Message** field → leave it as the indicator's default (e.g.
  `Rocket Prime Engine (Normal): Any alert() function call ({{ticker}})`)
  — the poller's parser handles "Buy/Sell Observation @" and similar
  patterns from indicator hardcoded text. It pulls the symbol from the
  email's Subject (`Alert: <indicator> on <SYMBOL>, <interval>`).

### Step 7 — verify the round trip

```cmd
:: Trigger the alert manually from TV (alert ⋮ menu → "Trigger now")
:: Then watch the three logs:
powershell -Command "Get-Content logs\tv_email.log -Wait -Tail 20"
powershell -Command "Get-Content logs\tv_signals.jsonl -Wait -Tail 5"
type trendmaster_signals_<SYMBOL>.json
```

Expected: within ~15 s of TV firing the alert, `tv_email.log` shows
`email→EA OK ...`, `tv_signals.jsonl` gets a new `event:write_ok`,
and the per-symbol JSON file appears in MT5's `Files` directory for
the EA to consume.

### Limitations of the email path

* Latency 10–20 s — not for sub-minute scalp.
* Dedup uses `Message-ID`; if Gmail filters or duplicates an email the
  poller may still trade twice (mitigation: 60 s `max_signal_age_s` skip).
* If Gmail throttles IMAP logins (rare), poller backs off and reconnects.

To upgrade to webhook later: TradingView Pro ($14.95/mo) → uncomment the
TV_WEBHOOK_* lines in `.env`, run `start_tv_webhook.cmd` instead, and
disable `TV_EMAIL.enabled = False` to avoid double-execution.


## Future: closing the loop (brain learns from TV)

Once a few weeks of `logs\brain_shadow_predictions.jsonl` + `logs\tv_signals.jsonl`
+ broker fill data have accumulated:

1. Join the three streams on `(symbol, ts)`.
2. Triple-barrier label every TV trade (TP/SL/time → win/loss/timeout).
3. Train a meta-labeller `P_act_TV(features → trade-or-skip)` using the
   brain's existing FEATURE_COLS_V2 as features and the TV-trade outcome as
   label. This is exactly the Phase C1/C2 architecture, just with TV as the
   side-classifier instead of the brain.
4. When `P_act_TV > 0.55`, accept the TV signal; otherwise let the EA skip.

That gives the brain a real job — quality-filter the TV stream — instead of
trying to be the entry oracle itself.
