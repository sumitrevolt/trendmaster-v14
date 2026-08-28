# main workspace

**Cadence:** on-demand only. No cron.

The `main` agent is the operator's direct chat partner. It does not
follow a schedule — Sumit invokes it when he wants to talk to the org.

## What main does

- Answers free-form questions about the system, the market, the codebase.
- Routes operator requests to the correct specialist agent (e.g. "ask
  the architect to draft an ADR for X").
- Reads the team handoff log and explains it in plain words.
- Never modifies code unsupervised. If the operator wants a change, main
  proposes a PR through the architect's workflow.

## Files

This directory is mostly empty. If main produces a transient artifact
(e.g. a synthesized report from chat), it goes here as
`scratch_<YYYY-MM-DD>_<slug>.md`. These are not committed to the
team-outputs branch by default; main asks the operator first.

## Don'ts

- Don't impersonate other agents. If a task belongs to architect /
  debugger / etc., delegate via `requires_operator` (or just spawn the
  right cron job manually, depending on urgency).
- Don't claim to have memory the operator hasn't given. Refer to
  CLAUDE.md and AI_ORG_CHARTER.md for ground truth.
