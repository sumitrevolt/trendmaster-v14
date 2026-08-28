# reviewer workspace

**Cadence:** every 6 hours.

## Periodic audit (6h)

File: `docs/team/reviewer/audit_<YYYY-MM-DD>_<HH>.md`.

Each run:

1. `git log --since="6 hours ago" --pretty="%h %s"` — list commits since
   last audit.
2. For each new commit, fetch the diff: `git show <hash> --stat` then
   `git show <hash>` for the full patch.
3. Skim for:
   - Hardcoded credentials or PII (refuse)
   - `Path(__file__).resolve()` inside `ai_trading_agents/` (refuse — see
     CLAUDE.md note on the .resolve trap)
   - Tests changed/removed without justification
   - Schema changes to `brain_state.json` / `team_handoff.jsonl` (these
     are operator-approved schemas; flag any change)
   - `print()` left in production paths (use `logger`)
4. For any concern, comment on the GitHub commit/PR via `gh pr review` (if
   the commit is in a PR) or open a `agent-escalation` issue.

Write the audit file with:

```
# Audit <YYYY-MM-DD HH:MM IST>
Commits reviewed: <N>
Concerns raised: <N>
GitHub comments left: <list of links>

## Per-commit notes
- <hash> <one-line summary>: <verdict OK | flagged>
  - <if flagged: why and link to issue/PR comment>
```

After writing, append `review` event with severity `info` or `warn`
based on findings.

## On-demand: PR review

When operator opens a PR and applies `label:needs-review`, the next 6h
cron picks it up first. Use `gh pr review --comment` (never
`--approve`).

## Don'ts

- Don't `gh pr merge` or `gh pr review --approve`. Operator-only.
- Don't reformat code. Use comments only. The author can fix.
- Don't audit commits older than 7 days unless explicitly asked.
