# debugger workspace

**Cadence:** every 1 hour, **gated**: only acts if `logs/trend_master_brain.err`
size > 0 OR a fresh `_draft_*.md` exists in `docs/POSTMORTEMS/`.

## Hourly triage

File: `docs/team/debugger/triage_<YYYY-MM-DD>_<HH>.md`. Skip the run (no
file, no handoff entry) when nothing to triage.

When triggered:

1. Read the last 200 lines of `logs/trend_master_brain.err`.
2. Group identical stack traces (last frame + exception type) and count
   occurrences.
3. For each group:
   - Pull the relevant code via `code-review-graph` MCP:
     `semantic_search_nodes` on the offending function name.
   - Identify likely root cause (1-3 sentences).
   - Propose a minimal patch (diff sketch — file + line range + change).
4. Cross-check against open `agent-escalation` issues to avoid duplicates.

Write the triage file with:

```
# Triage <ts>
brain.err size: <bytes> | new lines since last run: <N>

## Stack groups
### Group 1: <ExceptionType> at <last_frame> — N occurrences
<3-line code snippet>
Root cause: <hypothesis>
Proposed patch: <file:line> — <change>
Confidence: low | medium | high

### Group 2: ...

## Recommendation
- [ ] Open PR for Group 1 (high confidence)
- [ ] Defer Group 2 to architect (needs design call)
```

After writing, append `triage` event. Open GitHub issue with
`label:agent-task:debugger` for any group with confidence != high.

For high-confidence single-line fixes, the debugger MAY open a draft PR
(never merge). For multi-file fixes, hand off to architect via
`requires_operator` event.

## Don'ts

- Don't restart the brain. That's operator-only (CLAUDE.md operator
  invariant).
- Don't `git push` to main. Always PR.
- Don't muffle the error (try/except + pass). Fix the root cause or
  surface it.
- If brain.err is empty AND no fresh postmortem draft, exit silently
  without creating a triage file.
