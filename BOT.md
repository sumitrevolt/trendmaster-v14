# TrendMaster TV-Bot — quick reference

Single-page operator guide. Three commands, one webhook URL, all 35 pairs.

## What this bot does

```
TradingView alert (any pair)
        ↓ HTTPS POST
Cloudflare quick tunnel
        ↓
Webhook receiver (127.0.0.1:5005)
        ↓ writes per-symbol JSON
MT5 Files dir
        ↓ EA reads
MT5 EA places trade with risk gates
```

One TradingView **Webhook URL** handles every pair via the `{{ticker}}`
substitution — you don't need a separate URL per pair.

## Three commands

| Command         | What it does                                      |
|-----------------|---------------------------------------------------|
| `start_bot.cmd` | Starts receiver + tunnel, prints the webhook URL  |
| `status.cmd`    | Shows what's running, current URL, last 5 signals |
| `stop_bot.cmd`  | Cleanly stops both the receiver and the tunnel    |

## First-time setup (already done — for reference)

1. `config\.env` has these set:
   ```
   TV_WEBHOOK_SECRET=<48-char hex>
   TV_WEBHOOK_HOST=127.0.0.1
   TV_WEBHOOK_PORT=5005
   MT5_FILES_DIR=C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\<id>\MQL5\Files
   ```
2. `config\settings.py` has `TV_SIGNAL.enabled = True`.
3. `tools\cloudflared.exe` is auto-downloaded on first run.

## Daily workflow

1. Run `start_bot.cmd` → it prints the webhook URL like:
   ```
   https://random-words.trycloudflare.com/tv-signal?secret=...&symbol={{ticker}}
   ```
2. In TradingView, paste that URL into your alert(s):
   - **Webhook URL** field → the URL above
   - **Message** field → leave whatever your indicator gives by default
   - For Rocket Prime Engine specifically, the receiver parses
     `Buy Observation @ X` / `Sell Observation @ X` automatically
3. Save the alert. Wait for fires.
4. Live monitoring: open another terminal and run `status.cmd` any time.

**Important:** Cloudflare *quick* tunnel URLs change every restart. If
you stop and restart the bot, paste the new URL into your TV alerts
again. For a stable URL, upgrade to a Cloudflare-account named tunnel
(see `docs/TV_SIGNAL_SETUP.md` Option B).

## What the receiver accepts

Both formats work — the receiver tries JSON first, falls back to text:

**JSON body** (if your indicator lets you customise the message):
```json
{
  "secret":"<from .env>",
  "symbol":"{{ticker}}",
  "direction":"buy",
  "price":{{close}}
}
```

**Plain text body** (default for paid invite-only indicators that don't
let you customise the message — receiver pulls symbol from the URL's
`?symbol={{ticker}}` and direction from keywords like
"Buy Observation" / "Sell Observation" / "buy" / "sell"):
```
Buy Observation @ 4636.680
Ref SL    @ 4621.176
Ref Lvl 1 @ 4642.882
```

## Endpoints (for testing/debug)

* `GET  /health`     → liveness probe
* `GET  /status`     → uptime + metrics (requests, writes, dups, rejects)
* `POST /tv-signal`  → the actual signal endpoint

## Built-in protections

* **Symbol whitelist** — 35 pairs in `team_params.SYMBOL_TO_TEAM`. Any
  other symbol → 422 reject.
* **Authentication** — `secret` must match `.env`; sent in URL query
  (`?secret=...`) for plain-text bodies, or in JSON body.
* **Dedup** — same `(symbol, direction)` within 20s is treated as one
  signal (TV occasionally re-fires; indicator double-triggers).
* **Stale guard** — alerts older than 60s (when `tv_alert_ts` provided)
  are rejected.
* **EA-side risk gates** — per-team max-open=2, risk-per-trade 0.5%,
  ATR-based SL/TP from `team_params.py`. EA enforces, webhook only
  signals direction.

## Logs (under `logs/`)

| File                     | Content                                        |
|--------------------------|------------------------------------------------|
| `tv_webhook.log`         | Receiver app log (binds, requests, errors)     |
| `tv_signals.jsonl`       | Every successful TV → EA hop (audit trail)     |
| `cloudflared.err`        | Tunnel log (URL, reconnects)                   |
| `webhook_url.txt`        | Current public webhook URL (one line)          |

Tail signals live:
```cmd
powershell -Command "Get-Content logs\tv_signals.jsonl -Wait -Tail 5"
```

## What about the brain?

The legacy ML brain (`trend_master_brain.py` and the rest of
`ai_trading_agents/`) is **not running** in TV-mode. TradingView is the
single source of truth for entries; the brain's
`write_signal()` is short-circuited via `TV_SIGNAL.enabled = True` in
`settings.py` so even if it does run it won't write to the EA file.

To re-enable brain (e.g. for shadow learning), flip
`TV_SIGNAL.shadow_brain = True` in `settings.py` and run
`start_brain_clean.cmd`. See `docs/TV_SIGNAL_SETUP.md` for the full
shadow-mode workflow.
