# Runtime Playbook — Claude Code × OpenClaw

This project runs two AI runtimes side by side. Both read the same
`CLAUDE.md` so there is one project memory, but each is best at a
different kind of work. This file tells you (and them) which one to
reach for.

> **TL;DR — quick decision rule**
>
> | Question | Answer | Use |
> |---|---|---|
> | Editing many files in a session, will commit? | yes | **Claude Code** |
> | Need cron / scheduled / overnight loops? | yes | **OpenClaw `trader`** |
> | Cross-machine, off-hours, no human? | yes | **OpenClaw `trader`** |
> | Want pre-commit hooks to fire? | yes | **Claude Code** |
> | Long-context full-codebase read? | yes | **OpenClaw + Gemini 2.5 Pro** |
> | Quick chat about a file? | either | doesn't matter |

## Runtime profiles

### Claude Code (Anthropic CLI / IDE)

- Brain: whatever model the editor sends (Sonnet 4 / Opus 4 typically).
- Workspace: opened folder = the project root.
- Tools: file edit/read, bash, knowledge-graph (`code-review-graph` MCP),
  pre-commit hooks, git.
- Strengths:
  - Incremental edits with full diff visibility.
  - Pre-commit fires on save → code-review-graph stays current.
  - Tight feedback loop (operator watches each tool call).
- Weaknesses:
  - Each session starts cold; no built-in cron.
  - Conversation ends when window closes; can't run overnight.

### OpenClaw `trader` agent

- Brain (current): `google/gemini-2.5-pro` (operator's Pro key).
  Switch to `github-copilot/claude-opus-4.6` once Copilot tier supports
  it — see `~/.openclaw/openclaw.json` `agents.list[trader].model`.
- Workspace: `C:\Users\Ratanshila\Documents\autmated trading` (this repo).
- Tools: 38+ including the 8 `code-review-graph__*` tools, exec,
  process, web_search, web_fetch, browser, message, cron, image_*.
- Bootstrap auto-load: `CLAUDE.md`, `AGENTS.md`, `SOUL.md`, `TOOLS.md`,
  `IDENTITY.md`, `USER.md`, `HEARTBEAT.md`. Plus any skill prompts.
- Strengths:
  - **Persistent.** Sessions survive across operator's PC sleeps.
  - **Cron.** Schedule recurring agent turns (see `~/.openclaw/cron/jobs.json`).
  - **Multi-agent.** `main` is generic; `trader` is dedicated to this repo.
  - **Channel-routed.** Reply can go to a chat channel (currently
    Telegram disabled; flip on later).
  - Long-context Gemini 2.5 Pro: 1M tokens — full codebase fits.
- Weaknesses:
  - No pre-commit hook firing inside an agent turn (commit by hand
    or via Claude Code).
  - Tool payload can hit Copilot's rejection ceiling (40K+ chars) —
    that's why Opus is currently aspirational not primary.

## Division of labor (which runtime owns what)

| Workstream | Owner | Reason |
|---|---|---|
| Strategy R&D — write new feature columns, train models, evaluate | OpenClaw `trader` | Long contexts; can chain walk-forward + cpcv overnight |
| Brain code edits in `ai_trading_agents/` (junction-aware) | **Claude Code** | Pre-commit's `check_junction.py` guards every commit |
| Pre-commit fix loops (ruff, eof-fixer) | **Claude Code** | Git hooks fire only there |
| Postmortem authoring | OpenClaw `trader` | Persistent across days; reads `INDEX.md` automatically |
| Watch-pet response — investigate CRITICAL | OpenClaw `trader` | Watch-pets writes draft postmortem; agent finalizes |
| Operational scripts (`tools/*.py`) | either | both runtimes can edit; commit via Claude Code if pre-commit needs to gate |
| Reading market news / web research | OpenClaw `trader` (Gemini) | 1M ctx fits whole news scrape; web_fetch already wired |
| MT5 / EA mql5 source edits | **Claude Code** | EA `.ex5` recompile + chart re-attach is hands-on |
| Long-running backtest sweeps | OpenClaw cron | Use `cron add --every 6h --agent trader --message "Run tools/walkforward_lab.py over symbol X"` |
| Daily digest authoring | OpenClaw cron | Scheduled at 23:55, writes `reports/daily/<date>.md` |
| Schtasks audit (which crons are healthy) | OpenClaw cron via `tools/schtasks_audit.py` | meta-monitoring of the watch-pet layer itself |

## Shared state (both runtimes read/write the same files)

| File | Purpose | Owner |
|---|---|---|
| `CLAUDE.md` | Project memory; loaded on every session of either runtime | hand-edit, append-only conventions |
| `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `IDENTITY.md`, `USER.md`, `HEARTBEAT.md` | OpenClaw bootstrap context (auto-injected into trader agent) | hand-edit |
| `RUNTIME_PLAYBOOK.md` | This file — division of labor | hand-edit |
| `logs/brain_state.json` | Live brain state | brain only |
| `logs/watchpets_state.json` | Latest watch-pet aggregate (overall + 8 checks) | `tools/watch_pets.py` |
| `logs/watchpets.jsonl` | Watch-pet history (append-only) | same |
| `logs/watchpets_alerts.jsonl` | Critical-only alerts | same |
| `reports/daily/<date>.md` | End-of-day digest (planned) | `tools/daily_summary.py` |
| `docs/POSTMORTEMS/INDEX.md` | Catalog of incidents | hand-edit on close, auto-stub on open |
| `docs/POSTMORTEMS/_draft_*.md` | Auto-drafted postmortem stubs (planned) | `tools/watch_pets.py` on CRITICAL |

## Handoff patterns

**Pattern 1 — operator-driven research handoff.** Operator runs Claude
Code for a deep refactor, gets it green, commits. Then says to
OpenClaw trader, "monitor backtest sweep on this branch nightly until
Sharpe > 1.5; alert me when found." Trader picks up, reads CLAUDE.md
+ git log, runs cron-driven walkforwards, surfaces results in
`reports/auto_research/` and a daily digest.

**Pattern 2 — incident response.** Watch-pets fires CRITICAL → writes
draft postmortem to `docs/POSTMORTEMS/_draft_YYYY-MM-DD_HHMM.md`.
Operator opens Claude Code, asks "finalize this postmortem and
update INDEX.md". Claude Code does the file edits with pre-commit
firing properly. (Or: operator pings OpenClaw trader, which can do
the same edits; commit from a separate Claude Code session.)

**Pattern 3 — feature R&D loop.** OpenClaw trader proposes a new
feature in `reports/feature_proposals/<slug>.md`. Operator reviews,
opens Claude Code to implement in `ai_trading_agents/`. Commit with
pre-commit. OpenClaw cron picks up the new commit hash, runs
walkforward overnight, posts results next morning.

## Don't

- **Don't run both runtimes editing the same file simultaneously.**
  Last-writer-wins; you'll lose work. Coordinate via TASKS.md or
  by having one own a workstream until handoff.
- **Don't commit from OpenClaw without pre-commit passing.**
  OpenClaw can call `git commit`, but the pre-commit hooks run in
  the shell environment of whoever invokes it; safer to drop the
  commit into Claude Code which is wired correctly.
- **Don't let OpenClaw cron jobs accumulate without an enable
  audit.** `~/.openclaw/cron/jobs.json` should be reviewed monthly.
  Stale jobs that auto-trigger Opus are token waste.
- **Don't expose broker credentials to either runtime as env vars
  the agent can read.** Keep `.env` for the brain process only;
  agents touch MT5 only through read-only Python helpers.
