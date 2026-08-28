---
name: trading-next-prompt
description: Project-aware prompt engineer for TrendMaster v14. Reads current brain state + open R&D priorities + recent reports + postmortems + heartbeat log, then recommends the single highest-leverage next prompt for Sumit to send. On-demand only, recommendation-only — does NOT execute the recommended action. Use when Sumit asks "next prompt kya hoga", "what should we do next", "/trading-next-prompt", "prompt suggest karo", "ab kya kaam hai" (when looking for a real next-action, not a status check), or when starting a fresh session with no clear agenda.
---

# Trading Next-Prompt Engineer

A meta-skill. Given the current state of TrendMaster v14, it picks the single most leverage-positive next prompt for Sumit to send to Claude — written, ready to paste, with a one-paragraph rationale.

This is not a status report. The output is **a prompt**.

## When to invoke

- Start of a fresh Claude session, no clear agenda. Sumit wants "what should I work on right now?"
- After completing a phase (e.g., Phase A2 done, what's Phase B?).
- When stuck choosing between three things on the open R&D list.
- When `git log` says nothing useful has shipped in 24+ hours and Sumit needs a nudge.

## When NOT to invoke

- During an active incident — use `trading-incident-response` instead.
- When Sumit already has a specific task in mind — just do that task.
- For status checks — use `trading-morning-routine` or read the latest hourly RD_LOG digest.

## Inputs (auto-discovered, no arguments)

Read these files in order. If any fails, note it in the rationale rather than aborting:

1. **`CLAUDE.md`** (project root) — current state snapshot, open R&D priorities (#1, #2, #3 list), invariants, gotchas. The "Open R&D priorities" section is the primary action backlog.
2. **`MEMORY.md`** (in user memory dir, path under `C:\Users\Ratanshila\AppData\Roaming\Claude\local-agent-mode-sessions\.../memory/`) — durable context across sessions.
3. **`logs/brain_state.json`** — live brain state. ALWAYS read via Windows path with the `Read` tool, NOT via the Linux mount (mount truncates this file at col 1923, documented gotcha).
4. **`docs/RD_LOG/hourly/`** — newest 1-2 markdown digests. Last full digest's "Recommendation" line is a strong signal about what the loop already knows.
5. **`docs/RD_LOG/hourly/_heartbeat.log`** — last 5-10 lines tell you whether the brain is in MODEL_UNIFORM, INSUFFICIENT_STATE, OK, etc. for several hours running.
6. **`docs/POSTMORTEMS/INDEX.md`** — any open action items from past incidents.
7. **`reports/`** — sort by mtime. The 3 newest files that haven't been acted on are the most likely sources of "next thing to do."
8. **`git log -20 --oneline`** — last 20 commits. If the most recent are R&D digests + heartbeats only (no real code commits), the project is idling and a code-shipping prompt is high-leverage.
9. **Scheduled tasks status** — `schtasks /query /tn "TrendMaster *" /fo LIST` (best effort, skip if not on Windows). Missed runs surface real issues.

## Scoring rubric

Score each candidate next-action on three axes, 1-5 each. Pick the highest total.

| Axis | What it measures | 1 = bad | 5 = great |
|---|---|---|---|
| **Leverage** | Will this materially advance the project? | Cosmetic / docs-only | Unlocks new alpha, fixes a real outage, ships measurable value |
| **Feasibility** | Can Claude finish it in one session (≤90 min agent work)? | Multi-week effort, needs human gate every step | Single agent run, deterministic deliverable |
| **Urgency** | Is delaying it costing something? | Optional polish, no time pressure | Bot is broken, money on the line, deadline today |

Do NOT just pick from the CLAUDE.md "Open R&D priorities" list mechanically. Real high-leverage prompts often come from:

- A failed scheduled task that needs a fix.
- A postmortem action item that's been open too long.
- A report from a prior session that produced findings but no follow-through (e.g., Phase A2 → Phase B integration).
- A gotcha that's bitten Sumit twice and deserves a permanent fix (e.g., the `.resolve()` trap, the Linux-mount truncation).
- An invariant violation from MEMORY.md feedback (e.g., spread guard re-enabled by mistake).

## Procedure

1. **Discover state** — read all 9 inputs above. Time-box at 5 minutes; if a file isn't reachable, skip and note the gap.
2. **Generate 3-5 candidate prompts.** Each candidate is a self-contained instruction Sumit could paste into Claude tomorrow morning. They should differ in scope (quick vs deep), team (METALS vs FOREX vs CRYPTO vs COMMODITIES), and risk (read-only research vs writing to brain code).
3. **Score each** on Leverage / Feasibility / Urgency. Show the scorecard in the output.
4. **Pick the winner.** If two candidates tie, prefer the one with higher Urgency.
5. **Write the recommended prompt.** It must be:
   - Self-contained (no "you know the project" hand-waving).
   - Concrete file paths and acceptance criteria.
   - Time budget specified.
   - Hard rules listed (read-only? brain-write OK? what's off-limits?).
   - Ready to paste verbatim.
6. **Save to `reports/next_prompt_<UTC-DATE>.md`** with:
   - Headline (one sentence — what the prompt does).
   - Top recommendation (the prompt itself, fenced).
   - Scorecard table (all 3-5 candidates with scores).
   - Rationale (~150 words — why this one beats the others).
   - "Also considered" — short note on what the runner-up would have been.
7. **Reply to Sumit** with a 4-bullet summary:
   - One-sentence headline.
   - The prompt itself (fenced, copy-pasteable).
   - Why this one (≤30 words).
   - Where the file is (computer:// link).

## Hard rules

- **Recommend only — do NOT execute.** This skill writes one markdown file. It does NOT spawn agents to do the recommended work. Sumit decides when and whether to run it.
- **Read-only against the brain and live state.** No edits to `ai_trading_agents/`, no edits to `logs/brain_state.json`, no schtasks changes, no commits.
- **Honor invariants from MEMORY.md.** If a candidate prompt would violate a known operator rule (e.g., re-enable spread_guard, lower MIN_CONF below 0.50, restart on a hunch), drop it from the candidate list with a note.
- **Don't recommend prompts that need human-only actions.** "Restart the brain" is fine to recommend (Sumit can do it). "Approve a wire transfer" is not.
- **Stay under 600 words in the output file.** Sumit reads this on a phone sometimes.

## Output format (markdown template)

```markdown
# TrendMaster Next-Prompt — <UTC-DATE>

**Headline:** <one sentence>

## Recommended prompt

\`\`\`
<the prompt, ready to paste>
\`\`\`

## Why this one

<150-word rationale>

## Scorecard

| Candidate | Leverage | Feasibility | Urgency | Total | Notes |
|---|---|---|---|---|---|
| **<winner>** | x/5 | x/5 | x/5 | xx/15 | <one-line> |
| <runner-up> | x/5 | x/5 | x/5 | xx/15 | <one-line> |
| <other-1>   | x/5 | x/5 | x/5 | xx/15 | <one-line> |
| <other-2>   | x/5 | x/5 | x/5 | xx/15 | <one-line> |

## Also considered (not recommended now)

- <runner-up summary in one line — why deferred>
- <other items in 1-line each>

## State snapshot used

- Brain: <verdict + uptime + restart_count>
- Last full RD digest: <UTC time> — <recommendation>
- Latest report: <filename + mtime>
- Last commit: <hash + subject>
- Open postmortem actions: <count>
```

## Example output

> **Headline:** Promote the 7 EDGE-class CFTC COT contracts into `cross_asset_join.py` as a `cot_<contract>_spec_delta_z` feature family — the highest-conviction integration on the table after Phase A2.
>
> **Recommended prompt:**
> ```
> Implement Phase B of TrendMaster's smart-money flow integration. Read
> reports/influencer_correlation_phaseA2_2026-04-26.md to confirm the
> 7 EDGE-class CFTC COT contracts. Extend ai_trading_agents/cross_asset_join.py
> to fetch CFTC Socrata weekly COT for [GC, SI, 6E, 6J, 6C, CL, BTC],
> compute spec_delta_z (52-week z-score of net Managed Money positioning),
> forward-fill weekly→H1, and add 7 columns to FEATURE_COLS in
> trend_master_brain.py. Update ml_align.py and the alignment guard. Run
> tools/walkforward_lab.py --symbol all and write a before/after report at
> reports/phaseB_cot_walkforward_<date>.md. Hard rules: do NOT modify gate
> logic, do NOT lower MIN_CONF, do NOT enable spread_guard, do NOT re-train
> any model. This is feature plumbing only — model retrain is Phase C.
> ```
>
> **Why this one:** Phase A2 found 8 EDGE pairs with stable OOS edges; the work is one-session-sized; the brain is in MODEL_UNIFORM and adding a real signal is the most likely path back to deployable confidence. Beats triple-barrier (#1) and frac-diff (#2) on feasibility since it's plumbing, not labeling/feature-engineering.
>
> **Scorecard:**
>
> | Candidate | L | F | U | Total |
> |---|---|---|---|---|
> | **Phase B COT integration** | 5 | 4 | 4 | 13 |
> | Triple-barrier labeling | 5 | 2 | 3 | 10 |
> | Walkforward schtask audit | 2 | 5 | 3 | 10 |
> | Frac-diff + Hurst features | 4 | 3 | 2 | 9 |

## Notes for future maintainers

- This skill is intentionally meta. If we add another R&D phase (Phase C, D, etc.), update this skill's example to show the new highest-leverage candidate.
- Don't bake the candidate list into Python — keep it as Claude judgment. The whole point is to use the model's read of project state, not a fixed checklist.
- If a candidate keeps winning across 3+ runs and never gets executed, that's a signal to either reduce the prompt's scope or add a postmortem about why it's not getting prioritized.
