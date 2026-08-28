---
name: trading-rocket-prime-direction
description: Diagnose and fix direction routing for Rocket Prime indicator signals. Use when operator says "BUY signal aaya par SELL trade hua", "wrong direction", "indicator says X but trade is opposite", or when investigating why tv_strategy=rocket_prime_inferred trades go opposite to chart visual.
---

# Rocket Prime direction routing

## The fundamental problem

Rocket Prime Engine (Pine ID `PUB;56f0fb74de7f4eed9325b987428b727e`) is an INDICATOR (not a Strategy script). Its `alert()` function emits identical text on EVERY fire:

```
#### XAUUSD ####
```

There is NO "Buy" or "Sell" word in the body. The TV alert dropdown only exposes "Any alert() function call" condition (verified 2026-05-07 via UI inspection). This means:

- Webhook receiver can't text-parse direction
- `{{strategy.order.action}}` placeholder doesn't work (only for strategies)
- Single TV alert fires on every Rocket Prime signal regardless of direction

## The 3-tier solution (deployed 2026-05-07)

`tv_webhook_receiver.py` text-mode parser tries direction sources in this order:

### Priority 0 — Plot value extraction (PRIMARY)

Pine indicators expose plots via `{{plot_0}}` ... `{{plot_19}}` placeholders. We pack 10 plot values into the alert message field:

```
RP|{{ticker}}|tf={{interval}}|p0={{plot_0}}|p1={{plot_1}}|...|p9={{plot_9}}|c={{close}}
```

When TV fires the alert, placeholders resolve to numerical values. Receiver regex-extracts `pN=<value>` pairs. Heuristic:

- `p0 != 0` and `p1 == 0` → BUY (`tv_strategy=rocket_prime_plot0`)
- `p1 != 0` and `p0 == 0` → SELL (`tv_strategy=rocket_prime_plot1`)
- Both zero or both non-zero → fall through

Confidence: 0.90 (high — direct from indicator, no inference).

### Priority 1 — URL `&direction=buy|sell` (override)

If alert URL has explicit `&direction=buy` or `&direction=sell`:
- Trust it directly (`tv_strategy=rocket_prime_url_direction`)
- Confidence 0.95 (highest — operator-set)

### Priority 2 — Local price/RSI inference (FALLBACK)

If above two fail, fall back to `direction_inference.py` mean-reversion guess. **Often wrong direction** for trend-following indicators like Rocket Prime. Logged as `tv_strategy=rocket_prime_inferred` with conf 0.55-0.85.

## Diagnostic playbook

### Verify routing source per signal

```cmd
:: Last 10 signals with their direction source
.venv\Scripts\python.exe -c "from pathlib import Path; import json; [print(f'{r.get(\"ts\")} {r.get(\"symbol\"):8} {r.get(\"direction\"):4} src={r.get(\"tv_strategy\")}') for r in (json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines()[-10:]) if r.get('event')=='write_ok']"
```

Healthy distribution after a few hours of trading:
- Most signals: `rocket_prime_plot0` / `rocket_prime_plot1` (PRIMARY, working)
- Few/none: `rocket_prime_inferred` (FALLBACK, alarm bell — plots not parsing)

### Plot value forensic log

Every signal that hits Priority 0 logic appends to `logs/tv_plot_values.jsonl`:

```
{"ts":1778132000,"symbol":"XAUUSD","tf":"M15","plots":{"0":1.0,"1":0.0,...},"body_preview":"RP|XAUUSD|..."}
```

Use this to correlate plot indices to direction. After 5-10 signals, you'll see the pattern:
- BUY events: which plot is non-zero
- SELL events: which other plot

### When BUY/SELL plot indices don't match the heuristic

If observation shows e.g. `p2` is BUY signal and `p3` is SELL (instead of p0/p1), edit `ai_trading_agents/tv_webhook_receiver.py` Priority 0 block to swap `plot_values.get(0)` -> `plot_values.get(2)` etc. Then restart webhook.

## Recreating alerts with plot template

`tools/tv_alert_setup/recreate_top5_instant.py` already sets the message field:

```python
payload["message"] = (
    "RP|{{ticker}}|tf={{interval}}"
    "|p0={{plot_0}}|p1={{plot_1}}|...|p9={{plot_9}}"
    "|c={{close}}|t={{timenow}}"
)
```

To recreate after editing: `tools\tv_alert_setup\delete_all_rocket_then_recreate.py` runs delete + recreate in 60s via API.

## When this skill cannot help

If Rocket Prime updates its Pine code and STOPS exposing plots that distinguish direction (e.g., a single `plot(signal_strength, ...)` that's always ≥ 0), then:
- Plot extraction yields no useful direction info
- Must fall back to inference (less reliable)
- Or switch to a different indicator with explicit direction in alert text

## Related skills

- `trading-tv-signal-quality` — broader TV pipeline monitoring
- `trading-why-inspector` — per-signal trace through gates
- `trading-shadow-validation` — A/B brain shadow vs live outcomes
