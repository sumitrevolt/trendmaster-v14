# writer workspace

**Cadence:** daily 23:00 IST + on CRITICAL alert (event-triggered).

## Daily digest (23:00 IST)

File: `docs/team/writer/digest_<YYYY-MM-DD>.md`.

Steps:

1. `tools/team_handoff.py digest --hours 24` → markdown content.
2. Append a section "Trade activity" reading `logs/brain_state.json` →
   `recent_results` filtered to today.
3. Append "Open escalations" reading `gh issue list --label agent-escalation
   --state open`.
4. Append "Tomorrow's known events" — scan `config/news_calendar.json`
   for tomorrow's tier-1 events.

Style: terse markdown. The operator scans this in 30 seconds at end of
day or 30 seconds at start of the next morning. Aim ~150 words.

After writing, append `digest` event with `outputs` pointing at the file.

## On-CRITICAL postmortem draft

Trigger: a fresh `docs/POSTMORTEMS/_draft_<ts>.md` written by
`tools/watch_pets.py` (which already does this — see CLAUDE.md "Watch-pets"
section).

Steps:

1. Read the draft. It already has trigger summary, brain.err tail, and
   TODO sections (Root cause / Timeline / Remediation / Prevention).
2. Fill in **Timeline** by querying the handoff log around the trigger
   timestamp (±30 minutes).
3. Fill in **Root cause** with the debugger's most recent triage that
   matches the stack trace, if any.
4. Leave **Remediation** and **Prevention** as TODO with question prompts
   for the operator (writer doesn't decide remediation policy).
5. Save as `docs/POSTMORTEMS/<YYYY-MM-DD>_<slug>.md` (rename, drop the
   `_draft_` prefix). Add row to `docs/POSTMORTEMS/INDEX.md`.

After writing, append `postmortem_draft` event with severity `critical`.

## Don'ts

- Don't editorialize blame. Postmortems are blameless by org policy.
- Don't write more than 250 words for a digest.
- Don't decide remediation. Ask the operator.
- Don't auto-post to Telegram or Slack — channels are operator-config'd
  and currently disabled.
