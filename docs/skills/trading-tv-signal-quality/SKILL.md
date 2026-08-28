---
name: trading-tv-signal-quality
description: Monitor TradingView-source signal quality. Use when the operator asks "are the TV alerts firing correctly?", "why did the brain skip this signal?", "show me false signals", or when investigating per-pair / per-TF signal hit rate after a stretch of losses. TV-source mode (TV_SIGNAL.enabled=True) is the production path; the brain is shadow-only.
---

# TradingView signal quality monitor

## When to invoke

Trigger on questions about:
- TV alerts fired vs trades executed (gap → gate blocking)
- Per-pair / per-TF signal frequency
- Auto-paused alerts (TV's silent stop_reason="auto")
- `rocket_prime_text` (conf 0.95) vs `rocket_prime_inferred` (conf 0.55-0.85) ratio
- Same-second duplicates that hit dedup
- Webhook auth failures / rejected payloads

## Core data sources

| Path | What |
|---|---|
| `logs/tv_signals.jsonl` | Every webhook write_ok / dryrun / reject / gate_block |
| `logs/tv_webhook.log` | Receiver-level events (auth fail, dedup hit, parse error) |
| `https://shadow-cosmos-unending.ngrok-free.dev/status` | Live counters: requests_total, writes_ok, auth_fails, rejected, duplicates, dryruns |
| TV alerts API (via Playwright) | `pricealerts.tradingview.com/list_alerts` — active state, fire_count, last_stop_reason |
| `outputs/reactivate_inactive.py` | Healer for auto-paused alerts (also runs hourly via Task Scheduler) |
| `outputs/alerts_full_verify.py` | Coverage matrix (5 pairs × 4 TFs), URL completeness audit |

## Quality KPIs to track

```
1. signal_to_write rate    = writes_ok / requests_total            target: > 0.95
2. inferred_text_ratio     = rocket_prime_inferred / total fires   target: < 0.30 (if higher, URL params missing)
3. gate_block_rate         = (gate_block_news + gate_block_dd + gate_block_corr) / total
                                                                    target: < 0.10 (higher = signals firing during bad windows)
4. auto_pause_rate         = inactive alerts with stop=auto / 20    target: < 0.20 across a day
5. alerts_per_day_per_pair = sane range 1-15 per pair               anomaly: 0 or 30+
```

## Quick diagnostic commands

```cmd
:: One-shot health snapshot
.venv\Scripts\python.exe outputs\alerts_full_verify.py

:: Last 20 fires with strategy + TF + direction
powershell "Get-Content logs\tv_signals.jsonl -Tail 20 | ConvertFrom-Json | Select-Object @{N='time';E={[DateTimeOffset]::FromUnixTimeSeconds($_.ts).LocalDateTime}}, symbol, direction, tv_strategy, tv_timeframe, event | Format-Table"

:: Gate-block events today
powershell "Get-Content logs\tv_signals.jsonl | Select-String 'gate_block_' | Select-Object -Last 20"

:: Signals per pair, last 24h
.venv\Scripts\python.exe -c "from pathlib import Path; import json, time; lines=[json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines()]; cutoff=time.time()-86400; recent=[r for r in lines if r.get('ts',0)>cutoff and r.get('event')=='write_ok']; from collections import Counter; print(Counter(r.get('symbol') for r in recent).most_common())"
```

## Investigation playbook

**Symptom: "no trades despite signals"**
1. Check `logs/tv_signals.jsonl` for `event:"gate_block_*"` entries → identify which gate fired
2. If gate_block_news → check `config/news_calendar.json` is current (refresh weekly)
3. If gate_block_dd → check `logs/brain_state.json::start_of_day_equity` is set; if 0, brain hasn't seen midnight yet
4. If gate_block_corr → `mt5.positions_get(symbol=X)` — already 2 same-direction open
5. If quality_gate_block → look at `brain_shadow_predictions.jsonl` for `stats_avg_R` per (symbol, tf, direction)

**Symptom: "TV alerts not firing"**
1. Run `outputs/reactivate_inactive.py` — checks active count + restarts auto-paused
2. Check `logs/tv_webhook.log` for last incoming request timestamp
3. If > 90 min ago AND market open → likely TV alerts auto-stopped silently
4. Verify `webhook_url` in alerts has `&symbol=&tf=` params (recreate with `delete_all_rocket_then_recreate.py` if missing)

**Symptom: "weird signals (BUY when chart looks like SELL)"**
1. Find the offending signal in `tv_signals.jsonl` → check `tv_strategy`
2. If `rocket_prime_inferred` → receiver couldn't parse direction from body → `direction_inference.py` made a guess from MT5 price. Lower confidence (0.55-0.85). Check `logs/tv_webhook_unparsed_bodies.log`.
3. If `rocket_prime_text` → indicator emitted bad text. Open the chart on TV, check the alert message field.

## Red flags to escalate

- `auth_fails` count rising → URL secret leaked or copied wrong
- `inferred_text_ratio` > 0.5 over a day → URL `?symbol=&tf=` params missing on alerts
- Same alert fires > 50 times/day → TV has bugged into a tight loop
- `writes_ok` flat for 4+ market hours → webhook receiver process dead (watchdog should catch this in 5 min via `TrendMaster TV Webhook Watchdog`)

## Related skills

- `trading-zero-trades` — sister skill for the brain-source path
- `trading-why-inspector` — per-signal gate trace
- `trading-tca-daily` — fill-level execution analysis
