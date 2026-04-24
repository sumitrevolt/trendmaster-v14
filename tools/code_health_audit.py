"""Code health audit using the code-review-graph DB.

Reads .code-review-graph/graph.db and writes a markdown report to
docs/CODE_HEALTH_AUDIT.md.

Answers four questions about the live trading code:
  1. Which live functions have NO test coverage?
  2. Which functions look like dead code (no callers, not entry points)?
  3. What are the complexity hotspots (largest functions)?
  4. Which functions are most depended on (high-fan-in / change risk)?

"Live" = ai_trading_agents/** and tools/** (excludes tests/, archive/,
outputs/, .venv/, and script entry-files).

Run:
    python tools/code_health_audit.py
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / ".code-review-graph" / "graph.db"
REPORT = ROOT / "docs" / "CODE_HEALTH_AUDIT.md"

# Conventional entry-point / framework hook names — don't flag as dead code
# if they have no callers, they're called externally (CLI, pytest, Flask,
# MT5 callbacks, etc.).
ENTRY_POINT_NAMES = {
    "main",
    "__init__",
    "__enter__",
    "__exit__",
    "__call__",
    "__repr__",
    "__str__",
    "__eq__",
    "__hash__",
    "__lt__",
    "__getitem__",
    "__setitem__",
    "__iter__",
    "__next__",
    "__len__",
    "__contains__",
    "setUp",
    "tearDown",
    "setup_module",
    "teardown_module",
    "fixture",
    "pytest_configure",
    "pytest_collection_modifyitems",
}

LIVE_DIRS = ("ai_trading_agents", "tools")


def is_live_path(p: str | None) -> bool:
    if not p:
        return False
    # Windows paths in DB — check both separators
    norm = p.replace("\\", "/").lower()
    if "/archive/" in norm or "/.venv/" in norm or "/outputs/" in norm:
        return False
    if "/tests/" in norm or norm.endswith("/conftest.py"):
        return False
    return any(f"/{d}/" in norm for d in LIVE_DIRS)


def short_path(p: str) -> str:
    """Strip the repo-root prefix for readability."""
    p2 = p.replace("\\", "/")
    marker = "/autmated trading/"
    idx = p2.lower().find(marker.lower())
    return p2[idx + len(marker) :] if idx >= 0 else p2


def main() -> int:
    if not DB.exists():
        print(f"No graph DB at {DB}; run rebuild_graph.cmd first.")
        return 1

    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()

    # Load all Function-kind nodes in live dirs (skip Class/File/Test)
    cur.execute(
        """
        SELECT id, name, qualified_name, file_path,
               COALESCE(line_start, 0), COALESCE(line_end, 0),
               COALESCE(is_test, 0)
          FROM nodes
         WHERE kind = 'Function'
        """
    )
    all_funcs = cur.fetchall()

    live_funcs = [
        {
            "id": r[0],
            "name": r[1],
            "qn": r[2],
            "path": r[3] or "",
            "start": r[4],
            "end": r[5],
            "is_test": bool(r[6]),
            "loc": max(0, (r[5] or 0) - (r[4] or 0) + 1),
        }
        for r in all_funcs
        if is_live_path(r[3]) and not r[6]
    ]
    live_qns = {f["qn"] for f in live_funcs}

    # TESTED_BY edges keyed by target (tested func)
    cur.execute("SELECT source_qualified, target_qualified FROM edges WHERE kind='TESTED_BY'")
    tested_by: dict[str, list[str]] = {}
    for src, tgt in cur.fetchall():
        # TESTED_BY: source is the test, target is the tested function
        # (conventionally — but we handle both orderings just in case)
        tested_by.setdefault(tgt, []).append(src)

    # CALLS edges — count incoming
    cur.execute("SELECT source_qualified, target_qualified FROM edges WHERE kind='CALLS'")
    in_calls: Counter[str] = Counter()
    out_calls: Counter[str] = Counter()
    for src, tgt in cur.fetchall():
        in_calls[tgt] += 1
        out_calls[src] += 1

    # 1) Untested live functions
    untested = [f for f in live_funcs if not tested_by.get(f["qn"]) and f["name"] not in ENTRY_POINT_NAMES]

    # 2) Dead code candidates: live, not entry point, no incoming calls,
    #    not tested, not a method whose class is referenced elsewhere.
    dead = [
        f
        for f in live_funcs
        if in_calls.get(f["qn"], 0) == 0
        and not tested_by.get(f["qn"])
        and f["name"] not in ENTRY_POINT_NAMES
        # filter out dunder / private-looking framework methods
        and not (f["name"].startswith("__") and f["name"].endswith("__"))
    ]

    # 3) Complexity hotspots (by LOC)
    hotspots = sorted(live_funcs, key=lambda f: f["loc"], reverse=True)[:20]

    # 4) Highest fan-in (most called)
    fan_in = [(f, in_calls.get(f["qn"], 0)) for f in live_funcs if in_calls.get(f["qn"], 0)]
    fan_in.sort(key=lambda x: x[1], reverse=True)
    top_fanin = fan_in[:20]

    # Summary counts
    summary = {
        "total live functions": len(live_funcs),
        "untested": len(untested),
        "tested coverage": (f"{(len(live_funcs) - len(untested)) / max(1, len(live_funcs)) * 100:.1f}%"),
        "dead-code candidates": len(dead),
    }

    lines: list[str] = []
    lines.append("# TrendMaster v14 Code Health Audit")
    lines.append("")
    lines.append(
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} from "
        f"`.code-review-graph/graph.db` over `ai_trading_agents/**` and "
        f"`tools/**`._"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for k, v in summary.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    lines.append("## 1. Untested live functions")
    lines.append("")
    lines.append(
        f"Functions in live code with no `TESTED_BY` edge in the graph. "
        f"{len(untested)} total — top 25 by LOC shown below (biggest first = "
        f"highest-value tests to add)."
    )
    lines.append("")
    untested_by_loc = sorted(untested, key=lambda f: f["loc"], reverse=True)[:25]
    lines.append("| LOC | Function | File:line |")
    lines.append("|----:|----------|-----------|")
    for f in untested_by_loc:
        lines.append(f"| {f['loc']} | `{f['name']}` | `{short_path(f['path'])}`:{f['start']} |")
    lines.append("")

    lines.append("## 2. Dead-code candidates")
    lines.append("")
    lines.append(
        "Live functions with zero incoming `CALLS` edges, no tests, not on "
        "the entry-point allow-list. **Review before deleting** — some may "
        "be called dynamically (getattr, decorators, string-based dispatch, "
        "EA/MT5 callbacks) which the static parser can't see."
    )
    lines.append("")
    dead_sorted = sorted(dead, key=lambda f: (short_path(f["path"]), f["start"]))
    lines.append(f"Total: **{len(dead_sorted)}** candidates. First 25 below.")
    lines.append("")
    lines.append("| Function | File:line | LOC |")
    lines.append("|----------|-----------|----:|")
    for f in dead_sorted[:25]:
        lines.append(f"| `{f['name']}` | `{short_path(f['path'])}`:{f['start']} | {f['loc']} |")
    lines.append("")

    lines.append("## 3. Complexity hotspots (top 20 by LOC)")
    lines.append("")
    lines.append(
        "Largest live functions. Candidates for refactoring into smaller "
        "helpers. High LOC correlates with bugs and review friction."
    )
    lines.append("")
    lines.append("| LOC | Function | File:line | Tested? | Callers |")
    lines.append("|----:|----------|-----------|:-------:|-------:|")
    for f in hotspots:
        tested = "yes" if tested_by.get(f["qn"]) else "no"
        callers = in_calls.get(f["qn"], 0)
        lines.append(f"| {f['loc']} | `{f['name']}` | `{short_path(f['path'])}`:{f['start']} | {tested} | {callers} |")
    lines.append("")

    lines.append("## 4. Change-risk nodes (top 20 by fan-in)")
    lines.append("")
    lines.append(
        "Functions called by the most other functions. Changes here have "
        "the widest blast radius — worth extra review attention and thorough "
        "test coverage."
    )
    lines.append("")
    lines.append("| Callers | Function | File:line | Tested? |")
    lines.append("|-------:|----------|-----------|:-------:|")
    for f, n in top_fanin:
        tested = "yes" if tested_by.get(f["qn"]) else "no"
        lines.append(f"| {n} | `{f['name']}` | `{short_path(f['path'])}`:{f['start']} | {tested} |")
    lines.append("")

    lines.append("## Methodology notes")
    lines.append("")
    lines.append(
        "- Data source: `.code-review-graph/graph.db` (schema v9), "
        "built by `code-review-graph build` with Leiden communities "
        "via `python-igraph`."
    )
    lines.append(
        '- "Live" scope: files under `ai_trading_agents/` and `tools/`. '
        "`archive/`, `tests/`, `outputs/`, and `.venv/` are excluded."
    )
    lines.append(
        "- Entry-point allow-list: dunder methods, `main`, pytest/unittest "
        "hooks. Extend `ENTRY_POINT_NAMES` in `tools/code_health_audit.py` "
        "if your framework adds more externally-invoked names."
    )
    lines.append(
        "- **Static-only**: dynamic dispatch (getattr, decorators, "
        "registries, string-keyed handler maps, MT5 EA callbacks) is "
        "invisible to the parser. Use this report as a starting point for "
        "investigation, not as ground truth."
    )
    lines.append(
        "- Regenerate: `python tools/code_health_audit.py`. For a fresh "
        "graph first: `rebuild_graph.cmd` → then this script."
    )
    lines.append("")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {REPORT}")
    print(f"  live functions: {summary['total live functions']}")
    print(f"  untested:       {summary['untested']}")
    print(f"  dead candidates:{summary['dead-code candidates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
