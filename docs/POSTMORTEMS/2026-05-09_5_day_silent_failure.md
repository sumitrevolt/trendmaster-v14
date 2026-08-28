# Postmortem: 5-day silent failure (no trades despite signals)

| Field | Value |
|---|---|
| Date written | 2026-05-09 |
| Incident window | 2026-05-04 → 2026-05-09 ~00:23 IST |
| Duration | ~5 days |
| Severity | High — algo-trading bot generated zero trades despite signals firing every 5-min cycle |
| Detected by | Operator manual check ("trades not happening per indicator") |
| Resolved by | Single-line patch to `tools/python_signal_executor.py` `ALLOWED_STRATEGIES` set, plus broader hardening |

---

## TL;DR

The `local_signal_generator` writes signals tagged with `tv_strategy="local_generator"`. The executor's `ALLOWED_STRATEGIES` whitelist contained six Rocket Prime variants but **not** `"local_generator"`. Line 370–371 of `python_signal_executor.py` returned `None` with **zero log entry** whenever a signal's `tv_strategy` wasn't in the set. 76 signals per cycle were dropped silently for 5 days.

Adding `"local_generator"` to the set + replacing the silent `return None` with `log.info("skip ...: reason")` produced 16 trades within 30 seconds of restart.

---

## Timeline (IST)

| Time | Event |
|---|---|
| 2026-05-04 | Operator notices signals not driving trades. Assumes ngrok issue (recently flaky). |
| 2026-05-05 | First fix attempt: ngrok config restored. Trades still don't fire. |
| 2026-05-06 | Second fix: terminal popups silenced (5 schtasks). Unrelated to signal flow but eats debugging time. |
| 2026-05-07 | Third fix: TV alert templates rewritten with `{{plot_0}}..{{plot_9}}` placeholders via `recreate_with_login.py`. Verified all 20 alerts have correct template stored. Trades STILL don't fire. |
| 2026-05-08 day | Fourth fix: deeper investigation into Rocket Prime → discovered Pine `alert()` calls override the message field. Concluded TV chain is architecturally blocked. Built local_generator as workaround signal source. |
| 2026-05-08 18:00 | local_signal_generator firing 76 signals/cycle, written to MT5 files with proper `direction=BUY/SELL`. Operator confirms via screenshots that signals are present. Executor STILL not placing trades. |
| 2026-05-08 23:00 | Operator escalates: "5 days, why isn't this fixed?" |
| 2026-05-09 00:14 | Subagent audit of executor source → finds `ALLOWED_STRATEGIES` set at `python_signal_executor.py:356` does not include `"local_generator"`. Silent `return None` at line 371 has no log. |
| 2026-05-09 00:23 | Patch applied + executor restarted. **16 ORDER PLACED entries fire in 19 seconds across 9 symbols.** FLIP reversals follow within 90s. |
| 2026-05-09 00:30+ | Hardening: startup banner, skip taxonomy in heartbeat, regression tests, SLA monitor. |

## Root cause

Single-line bug in `tools/python_signal_executor.py`:

```python
ALLOWED_STRATEGIES = {
    "rocket_prime", "rocket_prime_text", "rocket_prime_inferred",
    "rocket_prime_plot0", "rocket_prime_plot1", "rocket_prime_url_direction",
    # local_generator MISSING
}
strategy = (sig.get("tv_strategy") or "").lower().strip()
if strategy not in ALLOWED_STRATEGIES:
    return None  # silently skip — not a Rocket Prime signal
```

The `# silently skip` comment is exactly what made the bug invisible.

## Contributing factors

1. **Silent skip pattern.** `return None` with no log call. The single highest-impact anti-pattern in the codebase. The 2026-05-07 audit found a previous instance of this exact bug ("Strategy whitelist drift" memory entry) but the fix at that time only added two new Rocket Prime variants — it didn't address the silent-skip pattern itself, so when local_generator was later added, it walked into the same trap.

2. **No skip taxonomy in heartbeat.** The heartbeat log line was `placed_this_round=0 skipped=N`. `N` was always >0 because every cycle saw 4+ stale signal files. The number itself looked normal — there was no breakdown showing "filtered_by_strategy=N" vs "stale=N" vs "no_file=N". Operator had no way to detect the strategy-filter killing all real signals.

3. **No regression test.** `ALLOWED_STRATEGIES` was an internal set with no external CI guard. Adding a new signal source elsewhere had no automated way to remind the developer to also add the strategy name to the executor whitelist.

4. **No SLA monitor.** The signal-to-trade chain had no end-to-end health check. Receiver said "TV→EA OK direction=BUY", MT5 file had `direction=BUY` — both looked healthy. Only end-to-end "did this signal produce an order within 90s" would have caught the gap.

5. **Wrong-end debugging.** Days 1-4 were spent on TV chain (legitimate problems but not the active blocker). The brain → MT5 chain was assumed healthy because heartbeats said so. The actual gate was at the LAST mile (executor's strategy filter).

## What went well

- Pipeline observability *infrastructure* (logs, watchdog, telegram bot) was solid — the bug was in WHAT got logged, not the logging stack itself.
- Once the executor source was actually read (Day 5), the bug was found in 8 minutes.
- Once patched, fix was verified within 30 seconds (trades fired).
- All previous "wrong-end" fixes (ngrok, popups, TV templates) were genuinely correct improvements — they reduced surface area and made today's diagnosis cleaner.

## Action items

| # | Action | Owner | Status |
|---|---|---|---|
| 1 | Add `"local_generator"` to ALLOWED_STRATEGIES | Claude | DONE 00:23 |
| 2 | Replace silent `return None` with `log.info("skip ...: reason")` in `load_signal` | Claude | DONE 00:23 |
| 3 | Startup banner that prints loaded vs disabled gates at boot | Claude | DONE 00:35 |
| 4 | Skip taxonomy in heartbeat: `no_file=N filtered=N stale=N` | Claude | DONE 00:35 |
| 5 | Hard-fail executor startup if safeguards module fails to import (override via TM_NO_SAFEGUARDS=1) | Claude | DONE 00:35 |
| 6 | Pytest `tests/test_pipeline_integrity.py` — fail CI if ALLOWED_STRATEGIES drifts from KNOWN_STRATEGIES | Claude | DONE 00:40 |
| 7 | `tools/signal_to_trade_sla.py` — every 60s, alert if signal arrived but no trade in 90s | Claude | DONE 00:45 |
| 8 | Memory entry `project_2026-05-09_local_generator_whitelist_killer_bug.md` so future Claude sessions don't re-walk the wrong end | Claude | DONE 00:48 |
| 9 | TV chain proper fix: 40-alert plot-crossing solution with `?direction=buy\|sell` URL params (deferred — requires manual plot-index capture) | Operator | DEFERRED |
| 10 | Audit remaining silent-skip sites flagged by 2026-05-09 audit (30+ found, top 5 patched) | Operator | OPEN |

## Lessons (durable)

1. **Silent skip paths are the single most expensive pattern in this codebase.** Every `return None` / `continue` / `except: pass` on a signal-handling code path is a 5-day-silent-failure-in-waiting. Standard pattern is now `log.info("skip <kind> <key>: <reason>")` followed by the early return.

2. **Heartbeat counters need taxonomy.** `skipped=N` is useless. `skipped_no_file=4 filtered=2 stale=0` is actionable. Apply this pattern to any future counter-style telemetry.

3. **Whitelists need regression tests.** Any in-code allowlist (ALLOWED_STRATEGIES, ALLOWED_SYMBOLS, etc.) should have a pytest that imports it and asserts every "known good" value is present. The test catches the next drift in seconds.

4. **End-to-end SLA checks beat per-component health.** Both the receiver and the executor reported "healthy" while the chain was broken. Only "did a signal produce a trade within N seconds" closes the gap.

5. **Read the actual code at the failure site before pivoting to adjacent areas.** Days 1-4 were spent on TV/ngrok/popup adjacent issues; the active blocker was in the executor source the whole time. Future debugging order: open the file the signal LAST passes through, then trace backwards.
