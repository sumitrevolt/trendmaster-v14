---
name: trading-morning-routine
description: One-command morning health check that runs all 5 diagnostic skills (model-healthcheck, correlation-monitor, drift-triage, position-reconciliation, tca-daily) in sequence and consolidates output into a single Telegram digest. Use when the user asks "morning routine", "morning check", "daily digest", "EOD summary", "give me the morning brief", or as a daily scheduled task at 09:00 local before market session.
---

# Trading Morning Routine

The 5 new diagnostic skills are individually valuable but require 5 separate invocations. This skill orchestrates them into one command that produces a consolidated brief and pages Telegram.

## When to invoke

- Daily morning routine (07:00-09:00 local before market session ramps).
- Weekly review (operator preference).
- After any unplanned brain restart.

## What it runs (in order)

1. **trading-model-healthcheck --team all** — 6-metric scorecard per team.
2. **trading-correlation-monitor** — XAU/DXY, BTC/ETH, EUR/GBP, AUD/NZD relationships.
3. **trading-drift-triage --team all** — ADWIN drift status per team.
4. **trading-position-reconciliation --no-mt5** — file-only reconcile (use --with-mt5 if MT5 connected).
5. **trading-tca-daily** — overnight fill quality.

Each skill is invoked as a subprocess; their output is captured. The skill then:

- Extracts the verdict line from each (HEALTHY/AMBER/RED, normal/decoupled, L0/L1/L2/L3, drift_detected/none, etc.).
- Builds a single 6-line Telegram message.
- Writes the full transcript to `logs/morning_routine_<date>.log`.

## Telegram output (typical)

```
TrendMaster v14 morning brief — 2026-04-25
- Model health:    METALS HEALTHY · FOREX HEALTHY · CRYPTO HEALTHY · COMMOD HEALTHY
- Correlations:    BTC/ETH 0.91 (baseline 0.89, normal)
- Drift triage:    All teams L0 — no action
- Positions:       0 open, all sources agree
- TCA overnight:   No new deals (weekend window)
- Brain uptime:    52m
Full log: logs/morning_routine_2026-04-25.log
```

## Verbose console output

```
=== TrendMaster v14 morning routine — 2026-04-25 09:14 ===

[1/5] trading-model-healthcheck --team all
  ... (full output)
  VERDICTS: METALS HEALTHY · FOREX HEALTHY · CRYPTO HEALTHY · COMMOD HEALTHY

[2/5] trading-correlation-monitor
  ... (full output)
  VERDICT: BTC/ETH 0.91 vs 0.89 (normal); no regime shifts

[3/5] trading-drift-triage --team crypto/forex/metals/commodities
  ... (full output)
  VERDICTS: All L0 (no action)

[4/5] trading-position-reconciliation --no-mt5
  ... (full output)
  VERDICT: DRIFT none — all sources agree

[5/5] trading-tca-daily --window 24h
  ... (full output)
  VERDICT: 0 deals; weekend window

=== SUMMARY ===
Overall: ALL GREEN
Telegram message sent.
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-morning-routine\routine.py
```

Pass `--no-telegram` to skip the alert (test mode). Pass `--quiet` to only print the summary line (skip per-skill output). Pass `--skill model-healthcheck` to run only one (useful for debugging).

## Schtask installation

```cmd
schtasks /create /sc DAILY /st 09:00 /rl LIMITED /f /tn "TrendMaster Morning Routine" ^
    /tr "cmd /c cd /d \"C:\Users\Ratanshila\Documents\autmated trading\" && .venv\Scripts\python.exe docs\skills\trading-morning-routine\routine.py --quiet >> logs\morning_routine.log 2>&1"
```

## Critical guardrails

- **Read-only.** This skill never mutates state; it only invokes sub-skills that are themselves read-only.
- **Per-skill timeout 60 seconds.** A hung sub-skill must not block the routine.
- **De-dup on identical content.** If two consecutive runs produce the same Telegram digest, only send once per 4 hours.
- **Honor `state.trading_paused`** — if brain paused, mention it in the digest header so verdicts are read in context.

## Helper script

`routine.py` next to this SKILL.md.
