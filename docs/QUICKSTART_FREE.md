# Quick-start: free stable webhook + email backup

**Goal:** Get a permanent webhook URL (no recurring cost) and stage email-fallback in case the webhook ever fails. Total time: ~10 minutes.

---

## Part 1 — Free stable webhook URL via ngrok-free.app  (5 minutes)

This replaces the rotating `*.trycloudflare.com` URL with one that **never changes**.

### Step 1 — Sign up for ngrok (free)

1. Open <https://dashboard.ngrok.com/signup>
2. Sign up with email — no card required.
3. Verify the confirmation email.

### Step 2 — Install the ngrok CLI

```cmd
winget install ngrok.ngrok
```

If `winget` isn't available, download from <https://ngrok.com/download> and place `ngrok.exe` in `C:\Users\Ratanshila\Documents\autmated trading\tools\` (next to `cloudflared.exe`).

### Step 3 — Add your authtoken

In the ngrok dashboard: `Your Authtoken` (left sidebar) → copy.

```cmd
ngrok config add-authtoken <PASTE_TOKEN_HERE>
```

### Step 4 — Claim your free static domain

Dashboard → **Universal Gateway → Domains → + New Domain** → pick a name, e.g. `trader-sumit.ngrok-free.app`. **Save the exact name.**

### Step 5 — Add 3 lines to `config\.env`

Open `config\.env` in Notepad and append:

```
TUNNEL_MODE=ngrok
NGROK_DOMAIN=trader-sumit.ngrok-free.app
TV_PUBLIC_URL=https://trader-sumit.ngrok-free.app
```

(Replace `trader-sumit.ngrok-free.app` with whatever name you actually claimed.)

### Step 6 — Restart the webhook

```cmd
start_tv_webhook.cmd
```

You should see at the end:

```
=== DONE — webhook + NGROK tunnel LIVE ===
  PUBLIC URL: https://trader-sumit.ngrok-free.app
  ✓ This URL is STABLE across restarts.
```

### Step 7 — Verify

```cmd
.venv\Scripts\python.exe tools\verify_tv_pipeline.py --send-test
```

Should show `[OK] Public /health` and `=== ALL CHECKS GREEN ===`.

### Step 8 — Update TradingView alerts (one-time)

Open every alert and replace the old webhook URL with the new permanent one:

```
https://trader-sumit.ngrok-free.app/tv-signal
```

That's it. From now on, restarts/auto-heals don't break alerts.

---

## Part 2 — Email backup pipeline  (3 minutes, optional)

If the webhook ever fails (TV plan downgrade, ngrok issue, network problem), email-mode picks up the slack — same downstream `write_tv_signal()` pipeline, just slower (~10–20 s end-to-end vs <1 s for webhook).

### Step 1 — Generate a Gmail App Password

1. <https://myaccount.google.com> → **Security** → **2-Step Verification**. Make sure 2-Step is **ON** (App passwords require it).
2. Same page, scroll to **App passwords** → **Select app: Mail** → **Select device: Windows Computer** → **Generate**.
3. Copy the 16-character password Google shows you (e.g. `abcd efgh ijkl mnop` — strip the spaces when pasting).

### Step 2 — Add 2 lines to `config\.env`

```
TV_EMAIL_USER=you@gmail.com
TV_EMAIL_APP_PASSWORD=abcdefghijklmnop
```

(Use your real Gmail address; paste the 16-char App Password from step 1, no spaces.)

### Step 3 — Flip the enable flag in `config\settings.py`

Find the `TV_EMAIL` block (around line 1161) and change:

```python
TV_EMAIL = {
    "enabled": False,    # ← change this
    ...
```

to:

```python
TV_EMAIL = {
    "enabled": True,
    ...
```

### Step 4 — Bring up the poller

```cmd
start_tv_email.cmd
```

The pre-flights will:
1. Check the enabled flag is `True`
2. Check both `.env` keys are set
3. Test IMAP login with your App Password (catches typos before backgrounding)
4. Start the poller detached, log to `logs\tv_email.log`

If you see `[X] PRE-FLIGHT FAIL: IMAP login failed` — most common cause is using your real Gmail password instead of the 16-char App Password. Re-do Step 1.

### Step 5 — Configure TradingView alerts to email

For each alert you want backed up: edit alert → **Notifications** → enable **Send email**. The poller picks up the email, parses symbol + direction, and routes through the same `tv_executor` as webhook signals.

> **Tip:** You can run **both** the webhook AND email poller simultaneously. The dedup window (per `(symbol, direction, timeframe)`) prevents double-fires — whichever path delivers the signal first wins.

### Step 6 — Daily verification

Both paths feed into `logs\tv_signals.jsonl`. Run the coverage matrix to confirm both are healthy:

```cmd
.venv\Scripts\python.exe tools\verify_tv_pipeline.py
```

---

## Part 3 — One-time installation of the watchdog (recommended)

Don't skip this. Without it, if the receiver or tunnel dies, you won't notice for hours.

```cmd
tools\install_tv_webhook_watchdog.cmd
```

This installs a Windows Task Scheduler job that runs every 5 min and:

* Auto-restarts the receiver/tunnel on failure
* Sends a Telegram alert if auto-restart fails
* Sends a Telegram alert if no signals received during market hours

Trigger the first run immediately to confirm it works:

```cmd
schtasks /Run /TN "TrendMaster TV Webhook Watchdog"
type logs\tv_webhook_watchdog.log
```

Last line should be `[OK] tv_webhook pipeline healthy.`

---

## Final state — what you have after this quickstart

| Layer | Status | What it does |
|---|---|---|
| Webhook receiver | LIVE | Accepts TV alerts on port 5005 |
| ngrok stable tunnel | LIVE | Permanent `*.ngrok-free.app` URL |
| TV alerts (76) | configured | All point to permanent URL |
| Watchdog | scheduled | Self-heals every 5 min |
| Email backup | staged but inactive | Flip `TV_EMAIL.enabled=True` if webhook ever fails long-term |
| News blackout | active | -60/+30 min around high-impact events |
| Brain | shadow mode | Still learns; doesn't write EA signals |
| Telegram alerts | LIVE | Watchdog + brain alerts go here |

Total recurring cost: **$0**.
