"""
Postmortem scaffolder for TrendMaster v14.

Reads brain state + event log at a named timestamp and pre-fills a postmortem
markdown file with TL;DR, timeline, position-state, P&L, rollback-safe time,
counterfactual, and action-items sections.

Pure-Python; only json + pathlib + datetime + argparse.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
PM_DIR = REPO_ROOT / "docs" / "POSTMORTEMS"
INDEX_FILE = PM_DIR / "INDEX.md"
STATE = REPO_ROOT / "logs" / "brain_state.json"
EVENTS = REPO_ROOT / "logs" / "events.jsonl"


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {}


def events_in_window(t0: datetime, t1: datetime) -> list[dict]:
    if not EVENTS.exists():
        return []
    out = []
    with EVENTS.open() as f:
        for line in f:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_str = ev.get("ts") or ev.get("timestamp")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if t0 <= ts <= t1:
                out.append({"ts": ts.isoformat(), "kind": ev.get("kind", "?"), "msg": ev.get("msg", "")})
    return out


def render_position_state(state: dict) -> str:
    open_pos = state.get("open_positions", []) or []
    if not open_pos:
        return "No open positions at detection."
    lines = []
    for p in open_pos[:12]:
        lines.append(
            f"- {p.get('symbol'):8s} {p.get('side'):5s} {p.get('lots')} lots "
            f"@ {p.get('entry_px')}  SL {p.get('sl_px') or 'none'}"
        )
    gross = sum(abs(float(p.get("lots", 0))) * float(p.get("entry_px", 0)) for p in open_pos)
    lines.append(f"\ngross exposure (notional): ${gross:,.2f}")
    return "\n".join(lines)


def render_timeline(events: list[dict]) -> str:
    if not events:
        return "- [Detection]  [fill in]\n- [Resolution]  [fill in]"
    return "\n".join(f"- {e['ts']}  {e['kind']:18s} {e['msg']}" for e in events[:50])


def slug_to_title(slug: str) -> str:
    return slug.replace("_", " ").title()


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


TEMPLATE = """\
# Postmortem - {title}

**Date**: {date}
**Severity**: SEV-? - [fill in]
**Authors**: Sumit
**Status**: Draft

## TL;DR

{summary}

## Timeline (UTC)

{timeline}

## Root cause

[Describe technical root cause. Be specific: file, function, what changed, why
the existing guardrails did not catch it.]

## P&L impact

| Window | Realised | Unrealised | R-multiple |
|---|---|---|---|
| At detection | [fill in] | [fill in] | [fill in] |
| At resolution | [fill in] | [fill in] | [fill in] |
| Counterfactual (if caught earlier) | [fill in] | - | [fill in] |

## Position state at detection

```
{positions}
```

## Rollback-safe time

Last safe rollback: [fill in - latest timestamp at which restoring state files
would NOT cause double-fills or stale orders].

We chose to: [roll forward / rollback to <ts>].

## Counterfactual P&L

If detection had occurred at [fill in earlier timestamp]:
- Time saved: [fill in]
- Same / different resolution path: [fill in]
- Estimated P&L recovery: [fill in]

## What went well

- [fill in]

## What went poorly

- [fill in]

## Action items

| # | Action | Owner | Due | Follow-up date |
|---|---|---|---|---|
| 1 | [fill in] | [owner] | [yyyy-mm-dd] | [yyyy-mm-dd] |

## Lessons

- [fill in]
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True, help="kebab_or_snake slug, e.g. crypto_team_silent_failure")
    ap.add_argument("--detection", required=True, help="Detection timestamp ISO8601, e.g. 2026-04-25T14:32:00Z")
    ap.add_argument("--resolution", default=None, help="Resolution timestamp ISO8601 (defaults to now)")
    ap.add_argument("--summary", default="[fill in one-line summary]")
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9_]+", args.slug):
        raise SystemExit("--slug must be lowercase letters / digits / underscores")

    detect = parse_iso(args.detection)
    resolve = parse_iso(args.resolution) if args.resolution else datetime.now(timezone.utc)
    date_str = detect.strftime("%Y-%m-%d")

    state = load_state()
    events = events_in_window(detect, resolve)

    body = TEMPLATE.format(
        title=slug_to_title(args.slug),
        date=date_str,
        summary=args.summary,
        timeline=render_timeline(events),
        positions=render_position_state(state),
    )

    PM_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PM_DIR / f"{date_str}_{args.slug}.md"
    if out_path.exists():
        raise SystemExit(f"Refusing to overwrite existing postmortem at {out_path}")
    out_path.write_text(body, encoding="utf-8")

    # Append to INDEX
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("# Postmortem index\n\n")
    with INDEX_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- [{date_str} - {slug_to_title(args.slug)}]({date_str}_{args.slug}.md)\n")

    print(f"Created: {out_path}")
    print("Open the file to fill in [fill in] sections; use git log to recover historical state if needed.")


if __name__ == "__main__":
    main()
