---
name: trading-telegram-direction-helper
description: "Resolve Rocket Prime no-direction signals via Telegram inline-keyboard BUY/SELL/SKIP buttons. Use whenever the operator sees Telegram message 'BTCUSD M5 signal — direction?' with buttons, or when tv_webhook.log shows 'NO-DIRECTION → Telegram prompt sent', or when the operator says 'I need to tap a button to trade RP signals'. Also use when the bot's Telegram token gets revoked/regenerated and needs reconnection."
---

# trading-telegram-direction-helper

The DEFINITIVE solution to Rocket Prime's missing-direction problem.
After 5+ failed approaches (Method 99 URL placeholders, plot-crossing UI,
INFERRED guessing, bridge Pine, Playwright UI automation), this is what
actually works: bot prompts operator on Telegram with inline buttons,
operator taps within 20 minutes, direction is 100% accurate (operator
decides, never inferred).

## How it works

1. RP indicator fires `alert()` on TradingView
2. Webhook receiver receives signal with body `#### TICKER ####` (no direction)
3. Receiver calls `telegram_direction_helper.send_direction_prompt(symbol, tf)`
4. Telegram pushes message with [📈 BUY] [📉 SELL] [⏭ SKIP] inline keyboard
5. Pending signal record written to `logs/pending_signals.jsonl`
6. `telegram_direction_listener` (long-running) polls `getUpdates` every 0.5s
7. Operator taps button on phone
8. Listener receives `callback_query`, parses `d:b:<sig_id>` (BUY) or `d:s:<sig_id>` (SELL)
9. Listener looks up pending signal, calls `tv_executor.write_tv_signal(...)`
10. Bot writes signal JSON to MT5 file → executor places trade

Timeout: 20 min (configurable via `RP_DIRECTION_TIMEOUT_S` env var).
After timeout, signal expires silently — no trade.

## Components

| File | Purpose |
|---|---|
| `ai_trading_agents/telegram_direction_helper.py` | Sends inline-keyboard prompt + manages `pending_signals.jsonl` |
| `ai_trading_agents/tv_webhook_receiver.py` (patched) | On no-direction, calls helper instead of REJECT |
| `tools/telegram_direction_listener.py` | Long-running poll loop; resolves taps → writes signals |
| `tools/hidden_telegram_direction_listener.vbs` | Hidden launcher (no console flash) |
| `outputs/start_telegram_direction_listener.cmd` | Manual restart |
| `outputs/deploy_telegram_button_helper.cmd` | End-to-end: restart webhook + start listener |
| `logs/pending_signals.jsonl` | Persistent state of pending signals |
| `logs/telegram_direction_listener.log` | Listener's own log |
| `logs/telegram_direction_listener.last_update_id` | Telegram update offset (resume across restarts) |

## Prerequisites

- TELEGRAM_BOT_TOKEN set in `config/.env` and bot exists in Telegram
- TELEGRAM_CHAT_ID set (operator's chat with the bot)
- Operator has sent `/start` to the bot at least once (so chat_id is valid)
- Python `requests` library installed in the venv
- tv_webhook_receiver running (port 5005)

## When the bot is broken (404 from Telegram)

Symptom: `logs/telegram_direction_listener.log` floods with
`getUpdates HTTP 404 body={"ok":false,"error_code":404}`. Brain log
also shows `Telegram send failed: 404`.

This means the bot token in `config/.env` is no longer valid.
Possible causes: bot deleted, token revoked, BotFather removed it.

Fix (operator-only, ~2 min in Telegram app):

1. Open Telegram → search `@BotFather` → start chat
2. Send `/mybots`
3. **If your bot is listed:**
   - Select it → "API Token" → "Revoke current token"
   - "Generate new token"
   - Copy the new token (format: `<digits>:<base64-ish>`)
4. **If not listed (deleted):**
   - `/newbot` → choose a display name and username
   - Copy the printed token
5. Send `/start` to your bot from operator's account (confirms chat_id)
6. Edit `config/.env`:
   ```
   TELEGRAM_BOT_TOKEN=<paste new token>
   TELEGRAM_CHAT_ID=<keep existing if same operator, or update if new>
   ```
7. Verify chat_id: `python -c "import urllib.request,json; r=urllib.request.urlopen(f'https://api.telegram.org/bot<TOKEN>/getUpdates'); print(json.load(r))"`
   Look for `from.id` field — that's the chat_id.
8. Redeploy: `outputs\deploy_telegram_button_helper.cmd`

## Verifying it works

1. Verify webhook patched:
   ```cmd
   .venv\Scripts\python.exe -c "p = open(r'C:\TrendMaster_aita_canonical\tv_webhook_receiver.py').read(); assert 'NO-DIRECTION → Telegram prompt sent' in p; print('webhook patch OK')"
   ```

2. Verify listener alive:
   ```cmd
   powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*telegram_direction_listener*' }"
   ```
   Should list at least one PID.

3. Verify Telegram bot reachable:
   ```cmd
   curl -s "https://api.telegram.org/bot$env:TELEGRAM_BOT_TOKEN/getMe"
   ```
   Should return `{"ok":true,"result":{"id":...,"username":"Sumits_jarvis_bot",...}}`.
   If 404, see "When bot is broken" above.

4. End-to-end test: trigger a fake no-direction alert manually:
   ```cmd
   curl -X POST "http://127.0.0.1:5005/tv-signal?secret=<SECRET>&symbol=BTCUSD&tf=5" -d "#### BTCUSD ####"
   ```
   You should immediately receive Telegram message on phone.
   Tap BUY → check `logs/python_executor.log` for a placed trade.

## Why this approach beats all the other ones

| Approach | Outcome |
|---|---|
| INFERRED guessing | Wrong direction 2026-05-08 (real loss) — DECLINED |
| Plot-crossing UI condition | TV dropdown locked to "Any alert() function call" |
| Method 99 (URL plot placeholders) | TV doesn't substitute placeholders under `alert()` |
| Bridge Pine indicator | RP uses `label.new()` not `plot()`, no series to bind |
| Playwright UI automation | TV React selectors break, brittle |
| OCR `{{chart.image}}` | Heavy infrastructure, maintenance burden |
| **Telegram button helper** | **Operator-decided direction, 100% correct, sub-second response** |

The trade-off: operator must be reachable on Telegram. For 20 alerts/day
with 24h coverage, this is sustainable. Operator's phone vibrates,
2 taps, done. No code maintenance, no indicator dependencies, no
guessing risk.

## Caveats

- Signal expires after 20 min if operator doesn't tap. Tune via env:
  `RP_DIRECTION_TIMEOUT_S=600` (10 min) for tighter discipline.
- Listener polls Telegram every ~0.5s with 25s long-poll, so latency
  is sub-second when operator taps.
- No deduplication: if same symbol+tf fires twice within timeout, TWO
  Telegram prompts arrive. Operator's tap on each resolves
  independently. Acceptable for RP's signal cadence.
- Skip = no trade, signal discarded. Operator can re-prompt by waiting
  for next RP fire on same symbol.

## Related memory

- `method_99_rp_url_placeholder.md` — Why URL plot placeholders failed
- `feedback_no_test_signals_to_live_webhook.md` — Don't accidentally
  send synthetic prompts via the live webhook
- `project_telegram_pipeline.md` — Existing Telegram pipeline setup
