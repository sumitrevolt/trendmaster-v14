# TrendMaster AI Organization — Charter

**Effective:** 2026-04-30  
**Operator:** Sumit (sumitrevolt)  
**Repo:** [sumitrevolt/trendmaster-v14](https://github.com/sumitrevolt/trendmaster-v14)  
**Runtime:** OpenClaw 2026.4.11 + Claude Code 2.1.121

This document is the org chart for the AI agents that run TrendMaster v14
day-to-day. Every agent's prompt should read this first to know its lane.
Agents read this as part of OpenClaw's bootstrap context (CLAUDE.md
re-exports it).

## Why this exists

Until 2026-04-30 the seven OpenClaw agents (trader / reviewer / architect /
debugger / researcher / writer / main) were configured but mostly idle —
only `trader` had a 30-minute heartbeat cron and a daily morning brief.
The operator was firefighting brain crashes alone. Per Sumit's 2026-04-30
ask ("think like a billionaire act like engineer create team"), the agents
are now organized as a real engineering team with explicit roles, cadences,
output formats, and escalation paths.

## Roles

| Role | Agent | Model | Cadence | Primary output |
|---|---|---|---|---|
| **Operator Liaison** | `main` | github-copilot/gpt-4o | on-demand | direct chat with Sumit |
| **On-Call / Operations** | `trader` | github-copilot/gpt-4o | every 30 min | `logs/team_handoff.jsonl` heartbeat |
| **Daily Brief** | `trader` | github-copilot/gpt-4o | daily 08:30 IST | `docs/team/trader/morning_<date>.md` |
| **Engineering Lead** | `architect` | github-copilot/gpt-4o | weekly Sun 09:00 IST | `docs/team/architect/weekly_<date>.md` ADR / proposal |
| **Quant Researcher** | `researcher` | google/gemini-2.5-pro | weekly Sat 10:00 IST | `docs/team/researcher/weekly_<date>.md` |
| **QA / Code Reviewer** | `reviewer` | github-copilot/gpt-4o | every 6 hours | `docs/team/reviewer/audit_<date>.md` |
| **SRE / Debugger** | `debugger` | github-copilot/gpt-4o | every 1 hour (gated on brain.err size > 0) | `docs/team/debugger/triage_<date>.md` |
| **Tech Writer / Postmortem** | `writer` | github-copilot/claude-haiku-4.5 | daily 23:00 IST + on CRITICAL | `docs/team/writer/digest_<date>.md` and `docs/POSTMORTEMS/<date>_*.md` |

The operator is **not** an agent. Sumit is the human-in-the-loop. Anything
the agents can't decide alone should be escalated via a `requires_operator`
event in the handoff log (see Coordination Protocol below).

## Coordination Protocol

### `logs/team_handoff.jsonl` — the team's Slack channel

Every agent writes one or more JSON-lines to this file at the end of its
run. It's the only channel for cross-agent visibility. **Schema:**

```json
{
  "ts": "2026-04-30T18:30:00+05:30",
  "agent": "trader",
  "event": "heartbeat" | "morning_brief" | "weekly_proposal" | "review" |
           "triage" | "research" | "digest" | "postmortem_draft" |
           "requires_operator" | "blocked",
  "summary": "<one sentence>",
  "outputs": ["docs/team/trader/morning_2026-04-30.md"],
  "links": {"github_issue": null, "github_pr": null},
  "severity": "info" | "warn" | "error" | "critical"
}
```

Validate with `tools/team_handoff.py validate` before append; query with
`tools/team_handoff.py recent --agent trader --hours 24`. The writer agent
rolls up the previous 24h into a daily digest.

### Workspaces

Each agent owns a directory under `docs/team/<role>/`:

- `docs/team/trader/` — heartbeats, morning briefs
- `docs/team/architect/` — weekly proposals, ADRs
- `docs/team/researcher/` — literature reviews, feature ideas
- `docs/team/reviewer/` — PR audits, security findings, ruff fixes
- `docs/team/debugger/` — triage reports, fix proposals
- `docs/team/writer/` — daily digests, postmortem drafts
- `docs/team/main/` — operator chat transcripts (rare; mostly volatile)

Each workspace has its own README explaining the deliverable format. New
agents read the README, then the latest 3 entries to establish style and
voice continuity.

### Escalation paths

When an agent encounters a situation it cannot resolve:

1. **Append `requires_operator` event** to `logs/team_handoff.jsonl` with
   the question and the relevant context.
2. **Open a GitHub issue** on `sumitrevolt/trendmaster-v14` with label
   `agent-escalation` and tag the agent's name (e.g. `agent:debugger`).
3. **Stop work** on that line item and proceed with other tasks.

The operator scans the handoff log + open `agent-escalation` issues at
session start (covered by the trader's morning brief — that brief lists
all open escalations).

### GitHub integration

Auth: project uses `gh` CLI with Sumit's keyring credentials. Token
scopes required: `gist, read:org, repo, workflow`. No PAT in env is
needed; agents shell out to `gh` directly.

What agents may do on GitHub:

- `gh issue list/create/view/comment` — research findings, escalations,
  bug triage
- `gh pr create --draft` — proposing code changes, never `--ready` without
  operator approval
- `gh pr review --comment` — reviewer agent leaves comments, never
  `--approve` (only operator approves)
- `gh issue close` — only when the agent itself opened the issue and is
  resolving it

What agents must NOT do on GitHub:

- Push directly to `main` — always via PR, always reviewed by operator
- Merge PRs — operator-only
- Modify branch protection / org settings — operator-only
- Create releases — operator-only

For autonomous agent activity that doesn't need a PR (daily brief, weekly
research, triage report), commit to a `team-outputs` branch:

```cmd
git checkout -B team-outputs origin/team-outputs
git add docs/team/<role>/<file>
git commit -m "<role>: <summary>"
git push origin team-outputs
```

The `team-outputs` branch is **append-only by convention** — agents don't
delete or rewrite, they always add new dated files.

## Cadences and triggers

### Time-based (cron, defined in `~/.openclaw/cron/jobs.json`)

| Job ID | Agent | Schedule | Purpose |
|---|---|---|---|
| `trendmaster-health-check` | trader | every 30 min | heartbeat |
| `trendmaster-morning-brief` | trader | 08:30 IST daily | morning brief |
| `trendmaster-architect-weekly` | architect | Sun 09:00 IST | strategy proposal |
| `trendmaster-researcher-weekly` | researcher | Sat 10:00 IST | research digest |
| `trendmaster-reviewer-6h` | reviewer | every 6 hours | code review pass |
| `trendmaster-debugger-hourly` | debugger | every 1 hour | brain.err triage (no-op if err empty) |
| `trendmaster-writer-daily` | writer | 23:00 IST daily | rollup of day's handoff log |

### Event-based

- **Brain produces zero trades for 24h on a weekday** → trader appends
  `requires_operator` event recommending a debug session.
- **Brain CRITICAL** (watchpets) → writer drafts a postmortem stub at
  `docs/POSTMORTEMS/_draft_<ts>.md` (this already exists per
  `tools/watch_pets.py` — agents use the existing draft as their start).
- **`brain.err` non-empty** → debugger agent's hourly cron triages the
  stack trace and proposes a fix.
- **Operator opens a `agent-task:<role>` issue on GitHub** → that role's
  next cron run picks it up (the cron prompt instructs each agent to
  scan open issues with `agent-task:<role>` label first).

## Operator's default visibility

Sumit's morning routine should be:

1. `tools\openclaw_brief.py` — live state
2. `type docs\team\trader\morning_<today>.md` — what trader prepared
3. `type docs\team\writer\digest_<yesterday>.md` — what happened overnight
4. `gh issue list --label agent-escalation` — anything blocked

That's the entire org running through three files and one issue list.

## Versioning of this charter

Edits to this charter are operator-only — agents cannot modify their own
job descriptions. If an agent thinks the charter is wrong (e.g. cadence
should change, role should split), it appends a `requires_operator` event
proposing the change and stops. Operator decides.

## Iteration log

- **2026-04-30** — Initial charter. 7 roles, 7 cron jobs, handoff log
  protocol, GitHub `team-outputs` branch convention. Sumit's call:
  "create team, billionaire-think, engineer-act."
