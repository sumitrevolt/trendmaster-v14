# architect workspace

**Cadence:** Sun 09:00 IST.

## Weekly proposal (Sunday)

File: `docs/team/architect/weekly_<YYYY-MM-DD>.md`.

Each Sunday the architect reviews:

- The week's `logs/team_handoff.jsonl` (use `tools/team_handoff.py digest --hours 168`)
- `reports/daily/*.md` from the past 7 days
- New entries in `docs/POSTMORTEMS/`
- Open GitHub issues with `label:agent-task:architect`

…and produces ONE of these output types:

1. **Architecture Decision Record (ADR)** — when proposing a structural
   change. Format:
   ```
   # ADR-NNN: <decision>
   Date: YYYY-MM-DD
   Status: Proposed (operator approval pending)
   Context: <why now, what triggered>
   Decision: <what>
   Consequences: <pros/cons/risk>
   Alternatives considered: <bullets>
   ```
   Open a draft GitHub PR with the ADR file + `label:adr` and link from
   the handoff log entry.

2. **Strategy proposal** — when proposing a new feature, indicator, or
   gate change. Format:
   ```
   # Proposal: <name>
   Hypothesis: <one sentence>
   Mechanism: <how it works in the existing brain pipeline>
   Backtest plan: <how to validate via tools/walkforward_lab.py>
   Risk to reject: <conditions under which we kill the proposal>
   Diff sketch: <bullet list of code locations to touch>
   ```
   Don't write code. Write the spec. The debugger or operator implements.

3. **No-op week** — if nothing structural is needed, the file is one
   sentence: "No structural changes proposed; system is stable per the
   week's digest." Followed by a brief justification (3 bullets).

After writing, append a `weekly_proposal` event to the handoff log.

## Don'ts

- Don't propose changes that haven't been seen as a recurring pain in the
  handoff log or postmortems. Drive from data, not vibes.
- Don't propose >2 things in one week. Ship one decision well.
- Don't approve PRs. Operator-only.
