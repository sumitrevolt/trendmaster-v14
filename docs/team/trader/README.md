# trader workspace

**Cadence:** 30-min heartbeat + daily 08:30 IST morning brief.

## Heartbeat (every 30 min)

The trader cron does NOT write a file every 30 min. It writes one line to
`logs/team_handoff.jsonl` with event `heartbeat`. Use the `team_handoff`
helper:

```cmd
.venv\Scripts\python.exe tools\team_handoff.py append --json "{\"agent\":\"trader\",\"event\":\"heartbeat\",\"summary\":\"<status>\",\"severity\":\"<info|warn|error|critical>\"}"
```

The status string should be either:
- `OK` when brain alive + no anomaly
- A 1-sentence description when brain dead during market hours, drawdown
  > 3 %, or `brain.err` has new lines

## Morning brief (08:30 IST daily)

File: `docs/team/trader/morning_<YYYY-MM-DD>.md`. Three sections, no more
than 5 bullets each:

1. **Overnight state** — overall watchpets verdict, brain pid uptime, last
   trade timestamp, drawdown vs limit.
2. **Yesterday's activity** — trade count, net P&L (point at the relevant
   `recent_results` entries), any drift alerts.
3. **Today's flags** — open `agent-escalation` issues on GitHub, weekend
   roll-into-Monday concerns, market events on the news calendar.

After writing the file, also append a `morning_brief` event to the handoff
log with `outputs: ["docs/team/trader/morning_<date>.md"]`.

## Style

Terse. Numbers over adjectives. Operator reads this in 30 seconds before
the trading day. No formalities.
