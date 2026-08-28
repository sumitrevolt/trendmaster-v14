"""
seed_team_crons.py — add the 5 missing TrendMaster AI Org cron jobs to
~/.openclaw/cron/jobs.json. Idempotent: skips jobs whose `name` already
exists.

Cron schedules:
- architect:  Sun 09:00 IST  weekly proposal
- researcher: Sat 10:00 IST  weekly research digest
- reviewer:   every 6 hours  audit pass
- debugger:   every 1 hour   triage (gated on brain.err inside agent prompt)
- writer:     daily 23:00 IST digest

Run:
    .venv\\Scripts\\python.exe tools\\seed_team_crons.py
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

JOBS_PATH = Path(os.environ.get("USERPROFILE", "")) / ".openclaw" / "cron" / "jobs.json"

NOW_MS = int(time.time() * 1000)

JOBS_TO_ADD = [
    {
        "id": "a4c7e2d8-1f3b-4a90-b6c5-architect00w1",
        "agentId": "architect",
        "name": "trendmaster-architect-weekly",
        "enabled": True,
        "schedule": {"kind": "cron", "tz": "Asia/Kolkata", "expr": "0 9 * * 0"},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": (
                "Weekly architect run. Read docs/AI_ORG_CHARTER.md (your role section) "
                "and docs/team/architect/README.md for output format. "
                "Steps: (1) `.venv\\Scripts\\python.exe tools\\team_handoff.py digest --hours 168` "
                "→ read the team's last week. (2) Read the most recent 3 files in "
                "reports/daily/ and any new docs/POSTMORTEMS/*.md from the past week. "
                "(3) `gh issue list --label agent-task:architect --state open --json title,number,body` "
                "→ pull operator-assigned tasks. (4) Decide: ADR, strategy proposal, or no-op week "
                "(see README). (5) Write the file at docs/team/architect/weekly_<YYYY-MM-DD>.md. "
                "(6) `.venv\\Scripts\\python.exe tools\\team_handoff.py append --json '{\"agent\":\"architect\",\"event\":\"weekly_proposal\",\"summary\":\"<terse summary>\",\"outputs\":[\"<path>\"],\"severity\":\"info\"}'`. "
                "Return literal word DONE."
            ),
        },
        "delivery": {"mode": "none"},
        "description": "Architect weekly run — ADRs, strategy proposals, no-op weeks.",
    },
    {
        "id": "b5d8f3e9-2a4c-4b91-c7d6-research00w2",
        "agentId": "researcher",
        "name": "trendmaster-researcher-weekly",
        "enabled": True,
        "schedule": {"kind": "cron", "tz": "Asia/Kolkata", "expr": "0 10 * * 6"},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": (
                "Weekly researcher run. Read docs/AI_ORG_CHARTER.md and "
                "docs/team/researcher/README.md for output format. "
                "Steps: (1) Pick ONE of: literature scan, walkforward analysis, or replay study. "
                "(2) Use web_search and web_fetch tools (gemini long-context) for literature scans. "
                "(3) For walkforward: run `.venv\\Scripts\\python.exe tools\\walkforward_lab.py --symbol all` "
                "and parse the report. (4) Write docs/team/researcher/weekly_<YYYY-MM-DD>.md "
                "in the README's prescribed 4-section format. (5) Append a 'research' event to handoff log. "
                "Return literal word DONE."
            ),
        },
        "delivery": {"mode": "none"},
        "description": "Researcher weekly digest — literature, walkforward, or replay.",
    },
    {
        "id": "c6e9f4f0-3b5d-4c92-d8e7-reviewer006h",
        "agentId": "reviewer",
        "name": "trendmaster-reviewer-6h",
        "enabled": True,
        "schedule": {"kind": "every", "everyMs": 6 * 3600 * 1000, "anchorMs": NOW_MS},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": (
                "6-hour reviewer audit. Read docs/AI_ORG_CHARTER.md and "
                "docs/team/reviewer/README.md. Steps: "
                "(1) `git log --since='6 hours ago' --pretty='%h %ai %s' main` for new commits. "
                "(2) For each commit, `git show <hash>` and skim for: hardcoded creds, "
                "Path(__file__).resolve() inside ai_trading_agents/ (refuse — see CLAUDE.md), "
                "tests removed, schema changes to brain_state.json or team_handoff.jsonl, "
                "stray print() in production paths. (3) Write docs/team/reviewer/audit_<YYYY-MM-DD>_<HH>.md "
                "with per-commit verdicts. (4) For any flagged commit, leave a `gh pr review --comment` "
                "or open an `agent-escalation` issue. (5) Append 'review' event to handoff log. "
                "If 0 commits since last audit, write a single-line file 'No commits since <last_audit>' "
                "and exit. Return DONE."
            ),
        },
        "delivery": {"mode": "none"},
        "description": "Reviewer 6h commit audit. Refuses to merge or approve, comments only.",
    },
    {
        "id": "d7f0a5a1-4c6e-4d93-e9f8-debugger001h",
        "agentId": "debugger",
        "name": "trendmaster-debugger-hourly",
        "enabled": True,
        "schedule": {"kind": "every", "everyMs": 3600 * 1000, "anchorMs": NOW_MS},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": (
                "Hourly debugger triage — GATED. "
                "Step 0: check `Get-Item logs\\trend_master_brain.err | Select-Object Length` and "
                "`Get-ChildItem docs\\POSTMORTEMS\\_draft_*.md`. "
                "If brain.err is 0 bytes AND no fresh draft postmortem, exit silently — DO NOT write a triage file, DO NOT append to handoff. "
                "Else: read docs/AI_ORG_CHARTER.md and docs/team/debugger/README.md. "
                "(1) Read last 200 lines of logs/trend_master_brain.err. "
                "(2) Group identical stack traces; count occurrences. "
                "(3) For each group, use code-review-graph MCP semantic_search_nodes_tool "
                "to locate offending function. Identify root cause + propose minimal patch. "
                "(4) Write docs/team/debugger/triage_<YYYY-MM-DD>_<HH>.md per the README format. "
                "(5) For confidence != high groups, `gh issue create --label agent-task:debugger`. "
                "(6) Append 'triage' event to handoff log. Return DONE (or DONE_NO_TRIAGE if exited at step 0)."
            ),
        },
        "delivery": {"mode": "none"},
        "description": "Hourly brain.err triage. Skips silently when err is empty.",
    },
    {
        "id": "e8a1b6b2-5d7f-4e94-f0a9-writerdaily0",
        "agentId": "writer",
        "name": "trendmaster-writer-daily",
        "enabled": True,
        "schedule": {"kind": "cron", "tz": "Asia/Kolkata", "expr": "0 23 * * *"},
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": (
                "Daily writer digest. Read docs/AI_ORG_CHARTER.md and docs/team/writer/README.md. "
                "Steps: (1) `.venv\\Scripts\\python.exe tools\\team_handoff.py digest --hours 24` "
                "→ markdown content. (2) Append 'Trade activity' from logs/brain_state.json recent_results "
                "filtered to today. (3) Append 'Open escalations' from "
                "`gh issue list --label agent-escalation --state open --json number,title,assignees`. "
                "(4) Append 'Tomorrow's events' from config/news_calendar.json (tier-1 only). "
                "(5) Write docs/team/writer/digest_<YYYY-MM-DD>.md (~150 words). "
                "(6) Append 'digest' event to handoff log. "
                "(7) `git checkout -B team-outputs origin/team-outputs && git add docs/team && "
                "git commit -m 'writer: daily digest <date>' && git push origin team-outputs` "
                "(continue on push failure, just log it). Return DONE."
            ),
        },
        "delivery": {"mode": "none"},
        "description": "Daily writer digest — rolls up handoff log, escalations, news.",
    },
]


def main() -> int:
    if not JOBS_PATH.exists():
        print(f"ERR: {JOBS_PATH} not found.", flush=True)
        return 1

    text = JOBS_PATH.read_text(encoding="utf-8")
    j = json.loads(text)
    existing_names = {job.get("name") for job in j.get("jobs", [])}
    print(f"[seed_team_crons] existing names: {sorted(existing_names)}")

    added = []
    for tmpl in JOBS_TO_ADD:
        if tmpl["name"] in existing_names:
            print(f"  skip {tmpl['name']} (already exists)")
            continue
        # fill the required tracking fields
        full = {
            **tmpl,
            "createdAtMs": NOW_MS,
            "updatedAtMs": NOW_MS,
            "state": {
                "nextRunAtMs": NOW_MS + 60_000,  # fire ~60s after gateway picks it up
                "lastRunAtMs": None,
                "lastRunStatus": None,
                "lastStatus": None,
                "lastDurationMs": None,
                "lastDeliveryStatus": None,
                "consecutiveErrors": 0,
                "lastErrorReason": None,
            },
        }
        j["jobs"].append(full)
        added.append(tmpl["name"])

    if not added:
        print("[seed_team_crons] nothing to add")
        return 0

    # Backup before writing
    bak = JOBS_PATH.with_suffix(".json.bak.before-team-seed-2026-04-30")
    bak.write_text(text, encoding="utf-8")
    JOBS_PATH.write_text(json.dumps(j, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[seed_team_crons] added: {added}")
    print(f"[seed_team_crons] backup: {bak}")
    print(f"[seed_team_crons] total jobs now: {len(j['jobs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
