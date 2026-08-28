# TradingView alert templates — all 19 TrendMaster pairs

**Last updated:** 2026-05-04
**Pipeline:** TradingView alert → `https://<tunnel>/tv-signal` → `tv_webhook_receiver.py` → `tv_executor.write_tv_signal()` → MT5 `Files\trendmaster_signals_<SYM>.json` → EA picks up next tick.

This is the only document you need to onboard a new symbol or rebuild your TradingView alerts after an account reset.

---

## 0. One-time setup

### 0a. Bring the receiver up

```cmd
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
start_tv_webhook.cmd
```

The script:
1. Pre-flights `TV_WEBHOOK_SECRET` in `config\.env` and that `ai_trading_agents.tv_webhook_receiver` imports cleanly.
2. Kills any prior receiver/tunnel.
3. Starts the receiver detached on `127.0.0.1:5005`.
4. Starts a Cloudflare quick tunnel and prints the public URL.

If you see "PUBLIC URL: https://<random>.trycloudflare.com" — that's your webhook URL. Copy it.

### 0b. Sanity-check from any browser or curl

```bash
curl https://<tunnel>.trycloudflare.com/health
# → {"status":"ok","ts":1777xxxxxx}

curl https://<tunnel>.trycloudflare.com/status
# → uptime, request count, dedup hits
```

---

## 1. The TWO alert formats

The receiver accepts both. Pick by paid plan:

### Format A — **JSON body** (TV Premium / Pro+ — full webhook URL field)

In TradingView **Create Alert → Notifications → Webhook URL** paste the *bare* URL:
```
https://<tunnel>.trycloudflare.com/tv-signal
```

In the **Message** field paste a JSON template like the per-symbol blocks below. TV substitutes `{{ticker}}`, `{{strategy.order.action}}`, `{{close}}`, `{{timenow}}` at fire time.

### Format B — **URL-secret + plain-text body** (TV Free — `alert()` mode, no message customisation)

If your indicator's message is hardcoded (e.g. Rocket Prime "Buy Observation @ price"), put the secret + symbol in the URL:

```
https://<tunnel>.trycloudflare.com/tv-signal?secret=<TV_WEBHOOK_SECRET>&symbol=XAUUSD
```

The receiver parses "Buy Observation" / "Sell Observation" / "buy" / "sell" / "long" / "short" out of the body and uses the URL `symbol` param for routing. This is the path that worked end-to-end on 2026-05-01.

---

## 2. Per-symbol JSON templates (Format A)

Each block is the **Message** field. The webhook URL is the same for every alert; what differs is the `symbol` value. **You do not need separate alerts for buy and sell** if your strategy publishes `{{strategy.order.action}}` — TV substitutes "buy" or "sell" depending on which alert fired.

For a plain indicator (not a strategy script) you'll create TWO alerts per symbol — one with `"direction":"buy"` hardcoded, one with `"direction":"sell"`.

Replace `YOUR_SECRET_HERE` with the value of `TV_WEBHOOK_SECRET` from `config\.env`.

### METALS (2)

```json
{"secret":"YOUR_SECRET_HERE","symbol":"XAUUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"XAGUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```

### FOREX (12)

```json
{"secret":"YOUR_SECRET_HERE","symbol":"EURUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"GBPUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"USDJPY","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"USDCHF","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"USDCAD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"AUDUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"NZDUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"EURJPY","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"GBPJPY","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"AUDJPY","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"CADJPY","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"EURGBP","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```

### CRYPTO (2)

```json
{"secret":"YOUR_SECRET_HERE","symbol":"BTCUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"ETHUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```

### COMMODITIES (3)

```json
{"secret":"YOUR_SECRET_HERE","symbol":"XTIUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"XBRUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```
```json
{"secret":"YOUR_SECRET_HERE","symbol":"XNGUSD","direction":"{{strategy.order.action}}","price":{{close}},"tv_strategy":"{{strategy.order.comment}}","tv_alert_ts":{{timenow}},"tv_timeframe":"{{interval}}"}
```

**Total: 19 symbols × N timeframes per symbol.**

> If you are running paid invite-only indicators that DON'T let you edit the message (Rocket Prime etc.) — use **Format B** (URL secret + plain text). One alert per (symbol × TF), the indicator's own "Buy Observation"/"Sell Observation" text is parsed by the receiver. Add the TF to the URL: `?secret=...&symbol=XAUUSD&tf=15`.

---

## 2b. Multi-timeframe setup — recommended M5 + M15 + H1 + H4 (76 alerts)

Operator policy 2026-05-04: for each of the 19 pairs, create **4 alerts** — one for each of M5, M15, H1, H4. The webhook now includes `tv_timeframe` and the receiver dedupes per `(symbol, direction, timeframe)`, so an M5 BUY and an H1 BUY firing within 20s **both execute** (they're different signals). Same M5 BUY firing twice within 20s is the only thing that gets dropped.

### How to bulk-create on TradingView

For each of the 19 symbols:

1. Open the chart, set timeframe to **M5**.
2. Apply your indicator (or strategy script).
3. Click the alarm-clock icon → **Create Alert**.
4. **Condition:** your strategy entry (or indicator buy/sell signal).
5. **Webhook URL:** `https://<TUNNEL>.trycloudflare.com/tv-signal`
6. **Message:** paste the JSON template for that symbol from §2 above. Make sure `"tv_timeframe":"{{interval}}"` is present — TV will substitute `"5"` for M5, `"15"` for M15, `"60"` for H1, `"240"` for H4 at fire-time. The receiver normalises those to `M5/M15/H1/H4` before storing.
7. **Alert name:** `XAUUSD M5 trendmaster` (so it's findable in your alert list).
8. Save.
9. Switch chart to **M15** → repeat steps 3–8 (only the alert name changes).
10. Switch to **H1** → repeat. Switch to **H4** → repeat.

That's 4 alerts for that symbol. Repeat for all 19 → **76 alerts**.

> **TradingView plan check:** Plus = 100 alerts, Premium = 400. 76 fits Plus.
> **Pro tip:** Use TV's "Manage alerts" right-side panel → click ⋮ on an existing alert → **"Save as alert"** to clone with the same template, then just edit the symbol or timeframe field. Cuts setup time roughly in half.

### What the receiver does with the TF info

* **Audit log:** every line in `logs\tv_signals.jsonl` now has `tv_timeframe: "M5"` (or H1/H4/D1). Greppable for per-TF coverage.
* **Dedup:** key is `(symbol, direction, timeframe)`. M5 BUY + H1 BUY same minute = both fire. M5 BUY twice in the same second = second one dropped.
* **EA payload:** the JSON file MT5 reads now contains `"tv_timeframe":"M5"`. EA ignores it for execution (still trades on the next tick) but it's available if you want to add per-TF risk profiles later.
* **Future:** when you switch on the Phase-2 quality learner (deferred), per-TF expectancy is what it'll learn from. e.g. "M5 BUY on EURUSD has -0.15R rolling expectancy → mute that signal class."

---

## 3. Receiver behaviour cheat-sheet

| Behaviour | Where set | Default |
|---|---|---|
| Reject signals older than | `TV_SIGNAL.max_signal_age_s` | 60 s |
| Default confidence stamped on payload | `TV_SIGNAL.default_confidence` | 0.95 |
| Skip EA's 3-of-3 quorum | `TV_SIGNAL.force_skip_quorum` | True |
| Dedup window (same `symbol+direction+TF`) | `TV_WEBHOOK_DEDUP_WINDOW_S` env | 20 s (NEW 2026-05-04: now per-TF) |
| News blackout window | `PROFIT_OPTIMIZER.news_lead_minutes` / `news_lag_minutes` | **-60 / +30 min** (NEW 2026-05-04) |
| Symbol whitelist | `team_params.SYMBOL_TO_TEAM` | 19 + crosses |
| Timeframe whitelist | `tv_executor._normalise_timeframe` | M1/M3/M5/M15/M30/M45/H1-H4/D1/W1/MN1 |

---

## 4. News blackout — what it actually does now

As of **2026-05-04** the news gate is **asymmetric**:

* **Block from -60 min before** any high-impact event (covers pre-release positioning + spread blow-out)
* **Block until +30 min after** the event (covers post-release whipsaw)
* Anything outside that window: trade as normal.

Defined in `config/settings.py::PROFIT_OPTIMIZER`:
```python
"news_lead_minutes": 60,
"news_lag_minutes":  30,
"news_impact_levels": ("high",),
```

Calendar source: `config/news_calendar.json`. **Refresh weekly** from forexfactory.com or investing.com — when the file is empty/stale it fails OPEN (everything trades).

---

## 5. Full end-to-end test (no live order)

After `start_tv_webhook.cmd` finishes:

```bash
# Replace <SECRET> and <TUNNEL> with your real values
curl -X POST "https://<TUNNEL>.trycloudflare.com/tv-signal" \
     -H "Content-Type: application/json" \
     -d '{"secret":"<SECRET>","symbol":"XAUUSD","direction":"buy","price":4636.68,"tv_strategy":"manual_test","tv_alert_ts":'"$(date +%s)"'}'
```

Expected:
* HTTP 200 with `{"status":"ok","symbol":"XAUUSD","direction":"BUY", ...}`
* New line in `logs\tv_signals.jsonl` with `event:"write_ok"`
* New line in `logs\tv_webhook.log` with `TV→EA OK`
* `Files\trendmaster_signals.json` mtime updates inside MT5 data folder

If any of those three fail — check `logs\tv_webhook.err`.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 401 unauthorized | `secret` mismatch | Compare body `secret` field to `TV_WEBHOOK_SECRET` in `config\.env` |
| 422 rejected, "symbol_not_whitelisted" | symbol not in `team_params.SYMBOL_TO_TEAM` | Add it to `team_params.py`, restart brain. |
| 422 rejected, "signal_stale" | TV alert older than 60 s | TV outage / network lag. Increase `TV_SIGNAL.max_signal_age_s` if you need slack. |
| 503 secret_not_configured | env var empty | Set `TV_WEBHOOK_SECRET` in `config\.env` and restart `start_tv_webhook.cmd` |
| `connection refused on localhost:5005` in `cloudflared.err` | webhook receiver crashed | Check `logs\tv_webhook.err`. Re-run `start_tv_webhook.cmd`. |
| Trade never fires after webhook returns 200 | EA not attached / news blackout / volatility regime | Check `logs\tv_webhook.log` (write_ok present?), then EA Experts tab. News blackout is now **-60 min** wide — common false alarm. |
