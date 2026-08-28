"""
team_handoff.py — append-only event log for the TrendMaster AI Organization.

Schema (one line per event):
    {
      "ts": ISO-8601 with offset,
      "agent": "trader|architect|researcher|reviewer|debugger|writer|main",
      "event": "heartbeat|morning_brief|weekly_proposal|review|triage|"
               "research|digest|postmortem_draft|requires_operator|blocked",
      "summary": str (one sentence, < 240 chars),
      "outputs": [str path],
      "links": {"github_issue": int|None, "github_pr": int|None},
      "severity": "info|warn|error|critical"
    }

Why append-only: this is the team's audit trail. No retroactive edits,
no deletes. If something is wrong, append a correction event.

Subcommands:
    append      Validate + append one event (reads JSON from stdin or --json)
    validate    Validate every line in the file; prints offending lines
    recent      Print recent N hours of events, optionally filtered
    digest      Roll up the last 24h into a summary block (markdown)
    schema      Print the schema and an example
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
HANDOFF = LOGS / "team_handoff.jsonl"

VALID_AGENTS = {
    "trader", "architect", "researcher", "reviewer",
    "debugger", "writer", "main",
}
VALID_EVENTS = {
    "heartbeat", "morning_brief", "weekly_proposal", "review",
    "triage", "research", "digest", "postmortem_draft",
    "requires_operator", "blocked",
}
VALID_SEVERITIES = {"info", "warn", "error", "critical"}


def _validate(entry: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    for k in ("ts", "agent", "event", "summary"):
        if k not in entry:
            errs.append(f"missing required key '{k}'")
    if entry.get("agent") not in VALID_AGENTS:
        errs.append(f"agent {entry.get('agent')!r} not in {sorted(VALID_AGENTS)}")
    if entry.get("event") not in VALID_EVENTS:
        errs.append(f"event {entry.get('event')!r} not in {sorted(VALID_EVENTS)}")
    sev = entry.get("severity", "info")
    if sev not in VALID_SEVERITIES:
        errs.append(f"severity {sev!r} not in {sorted(VALID_SEVERITIES)}")
    summ = entry.get("summary", "")
    if not isinstance(summ, str) or len(summ) > 240:
        errs.append("summary must be str <= 240 chars")
    outs = entry.get("outputs", [])
    if not isinstance(outs, list):
        errs.append("outputs must be a list")
    return errs


def cmd_append(args: argparse.Namespace) -> int:
    data = args.json or sys.stdin.read()
    try:
        entry = json.loads(data)
    except json.JSONDecodeError as e:
        print(f"ERR: bad JSON: {e}", file=sys.stderr)
        return 2

    # Defaults
    entry.setdefault("ts", datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    entry.setdefault("severity", "info")
    entry.setdefault("outputs", [])
    entry.setdefault("links", {"github_issue": None, "github_pr": None})

    errs = _validate(entry)
    if errs:
        print("ERR: invalid entry:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    LOGS.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with HANDOFF.open("a", encoding="utf-8") as f:
        f.write(line)
    print(f"APPENDED {entry['agent']}/{entry['event']}: {entry['summary'][:80]}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    if not HANDOFF.exists():
        print(f"(empty: {HANDOFF} doesn't exist)")
        return 0
    bad = 0
    total = 0
    with HANDOFF.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                bad += 1
                print(f"line {i}: BAD JSON {e}")
                continue
            errs = _validate(entry)
            if errs:
                bad += 1
                print(f"line {i}: {entry.get('agent','?')}/{entry.get('event','?')}: {errs}")
    print(f"\n{total} entries, {bad} invalid")
    return 0 if bad == 0 else 1


def cmd_recent(args: argparse.Namespace) -> int:
    if not HANDOFF.exists():
        print("(empty)")
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    with HANDOFF.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                ts = datetime.fromisoformat(entry["ts"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (KeyError, ValueError):
                continue
            if ts < cutoff:
                continue
            if args.agent and entry.get("agent") != args.agent:
                continue
            if args.event and entry.get("event") != args.event:
                continue
            sev = entry.get("severity", "info")
            short_ts = ts.astimezone().strftime("%m-%d %H:%M")
            print(f"[{short_ts} {sev:>5}] {entry.get('agent','?'):>10}/{entry.get('event','?'):<18} {entry.get('summary','')[:120]}")
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    if not HANDOFF.exists():
        print("# Daily digest\n\n(no handoff log yet)\n")
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    by_agent: dict[str, list[dict]] = {}
    escalations: list[dict] = []
    crits: list[dict] = []
    with HANDOFF.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["ts"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if ts < cutoff:
                continue
            by_agent.setdefault(entry.get("agent", "?"), []).append(entry)
            if entry.get("event") == "requires_operator":
                escalations.append(entry)
            if entry.get("severity") == "critical":
                crits.append(entry)

    print(f"# Team digest — last {args.hours}h")
    print(f"_Generated {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}_\n")
    if escalations:
        print("## Operator escalations\n")
        for e in escalations:
            print(f"- **{e.get('agent')}**: {e.get('summary','')}")
        print()
    if crits:
        print("## Critical events\n")
        for e in crits:
            print(f"- **{e.get('agent')}**/{e.get('event')}: {e.get('summary','')}")
        print()
    print("## Activity by agent\n")
    for agent in sorted(by_agent):
        entries = by_agent[agent]
        print(f"### {agent} ({len(entries)} events)\n")
        # last 5 entries per agent
        for e in entries[-5:]:
            print(f"- _{e.get('event','?')}_: {e.get('summary','')[:120]}")
        print()
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    print(__doc__)
    print("\nExample valid entry:\n")
    example = {
        "ts": "2026-04-30T18:30:00+05:30",
        "agent": "trader",
        "event": "heartbeat",
        "summary": "Brain alive PID=2960, watchpets OK, 4 BUY signals.",
        "outputs": [],
        "links": {"github_issue": None, "github_pr": None},
        "severity": "info",
    }
    print(json.dumps(example, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="team_handoff")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("append", help="validate + append")
    pa.add_argument("--json", help="JSON string (else read stdin)")
    pa.set_defaults(func=cmd_append)

    pv = sub.add_parser("validate")
    pv.set_defaults(func=cmd_validate)

    pr = sub.add_parser("recent")
    pr.add_argument("--hours", type=float, default=24.0)
    pr.add_argument("--agent")
    pr.add_argument("--event")
    pr.set_defaults(func=cmd_recent)

    pd = sub.add_parser("digest")
    pd.add_argument("--hours", type=float, default=24.0)
    pd.set_defaults(func=cmd_digest)

    ps = sub.add_parser("schema")
    ps.set_defaults(func=cmd_schema)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
