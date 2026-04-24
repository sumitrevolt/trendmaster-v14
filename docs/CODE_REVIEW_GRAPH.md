# Code Review Graph

The repo is indexed by `code-review-graph` (installed at
`C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\Scripts\code-review-graph.exe`,
version 2.3.2) into a SQLite DB at `.code-review-graph/graph.db`. The
DB powers the MCP tools documented in `CLAUDE.md`
(`detect_changes`, `query_graph`, `semantic_search_nodes`,
`get_impact_radius`, `get_affected_flows`, etc.) used by Claude Code
sessions to explore the codebase structurally instead of via
grep/glob.

## How it's kept fresh

Two mechanisms:

1. **Auto-update on edit (git only).** `.claude/settings.json` has a
   `PostToolUse` hook that runs `tools\crg_hook.cmd` after every
   `Edit`, `Write`, or `Bash` tool use in Claude Code. The wrapper
   checks for `.git/` and only runs `code-review-graph update
   --skip-flows` if git is present — `update` uses `git diff` under
   the hood and errors without a repo. **This project has no `.git`
   today, so the hook currently exits 0 silently** (no spam, no
   updates). The moment you `git init`, incremental updates activate
   automatically with zero config changes.

2. **Manual full rebuild.** Run `rebuild_graph.cmd` after a
   significant refactor or before working with flow-dependent queries.
   That script runs `code-review-graph build` with full postprocess
   and prints `status`. Takes ~8 s. Until this repo has git, this is
   the *only* way to refresh the graph.

Check current state any time with `graph_status.cmd` (or
`python tools/graph_status.py`).

### Recommended: `git init`

This project is a production trading system with 11+ numbered
iteration rounds recorded in auto-memory, yet has no git history.
Running `git init` would:

- Activate incremental graph updates after every Claude Code tool use
  (sub-second instead of 8 s full rebuild).
- Enable `code-review-graph detect-changes` for PR-style impact analysis.
- Give you actual version control over the live trading code.

The existing `.gitignore` is already well-tuned for this. If you do
initialize, no code-review-graph config changes are needed.

## Ignore rules: `.code-review-graphignore`

The tool reads a gitignore-style `.code-review-graphignore` at the repo
root (see `code_review_graph.incremental._load_ignore_patterns`). The
built-in defaults already cover `.venv/`, `__pycache__/`,
`.code-review-graph/`, `*.db`, `*.lock`, `node_modules/`, `build/`,
`dist/`, and more.

This project adds:

```
archive/**
pytest-cache-files-*/**
```

`archive/` was **~40% of all nodes (659 / 1,672)** before exclusion —
legacy Python (`legacy_python/`) and older `src/` code not imported by
the live v14 stack. Including it inflated `get_impact_radius` and
`query_graph pattern=callers_of` results with calls from dead code,
muddied community partitioning, and slowed every graph update by ~40%.

## Current shape (post-exclusion, 2026-04-24)

- **141 files**, **1,015 nodes**, **9,054 edges**, **87 flows**,
  **5 communities**
- Node mix: 525 Functions, 280 Tests, 141 Files, 69 Classes
- Edge mix: 6,424 CALLS, 1,092 TESTED_BY, 874 CONTAINS, 661
  IMPORTS_FROM, 2 INHERITS, 1 REFERENCES
- archive/: 0 files, 0 nodes (was 38 files / 659 nodes)
- ai_trading_agents/: 35 files / 370 nodes (intact)
- tools/: 40 files / 236 nodes (intact)
- tests/: 39 files / 363 nodes (intact)

## Repo has no `.git` directory

`find_repo_root` returns `None`, so the tool falls back to cwd for
`repo_root` and to `rglob("*")` for file discovery (instead of
`git ls-files`). That's fine — the ignore machinery still applies.
If you ever `git init` this project, nothing changes behaviourally;
the tool will just prefer `git ls-files`.

## Visualization

Interactive HTML graph (community mode) lives at
`docs/code_review_graph.html` (2 MB, self-contained). Double-click to
open in a browser. Regenerate with:

```
code-review-graph visualize --mode community --format html
copy .code-review-graph\graph.html docs\code_review_graph.html
```

Other modes: `full` (all nodes, heavy), `file` (file-level only).
Other formats: `graphml` (Gephi/Cytoscape), `cypher` (Neo4j),
`obsidian`, `svg`.

For a richer wiki with per-community member lists and cross-community
dependency tables, install `python-igraph` (`pip install python-igraph`).
Without igraph, community detection falls back to directory-based
grouping and wiki pages show empty member sections.

## Troubleshooting

- **`code-review-graph: command not found`** — the CLI is not on PATH.
  Verify with `Get-Command code-review-graph` in PowerShell. Reinstall
  with `pip install code-review-graph` if missing.
- **Queries return stale results after a big refactor** — the
  `--skip-flows` hook doesn't recompute flows/communities. Run
  `rebuild_graph.cmd`.
- **archive share > 0% in `graph_status.cmd` output** — the
  `.code-review-graphignore` file has been removed or reverted. Restore
  it (at least `archive/**`) and run `rebuild_graph.cmd`.
- **DB size grows unbounded** — run `graph_status.cmd` to see which
  bucket grew; add matching patterns to `.code-review-graphignore`.
