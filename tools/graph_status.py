"""Quick status + counts for the code-review-graph DB.

Called by graph_status.cmd, but also runnable directly:
    python tools/graph_status.py

Reads .code-review-graph/graph.db relative to the project root and prints
schema/build metadata, node/edge/flow counts, and highlights the archive/
share (a common exclusion candidate).
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    # Resolve project root (parent of tools/), so this works from any cwd.
    project_root = Path(__file__).resolve().parent.parent
    db_path = project_root / ".code-review-graph" / "graph.db"

    if not db_path.exists():
        print(f"[graph_status] No graph DB found at {db_path}")
        print("               Run rebuild_graph.cmd to create it.")
        return 1

    size_mb = db_path.stat().st_size / 1024 / 1024

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.cursor()
        meta = dict(cur.execute("SELECT key, value FROM metadata").fetchall())

        print("=== code-review-graph status ===")
        print(f"DB             : {db_path}  ({size_mb:.1f} MB)")
        print(f"schema_version : {meta.get('schema_version')}")
        print(f"last_build_type: {meta.get('last_build_type')}")
        print(f"last_updated   : {meta.get('last_updated')}")
        print(
            f"postprocess    : {meta.get('last_postprocessed_at')}  "
            f"(level={meta.get('postprocess_level')})"
        )
        print()

        print("--- node counts by kind ---")
        for kind, n in cur.execute(
            "SELECT kind, COUNT(*) FROM nodes GROUP BY kind ORDER BY 2 DESC"
        ):
            print(f"  {kind:<10} {n:>6}")

        print("--- edge counts by kind ---")
        for kind, n in cur.execute(
            "SELECT kind, COUNT(*) FROM edges GROUP BY kind ORDER BY 2 DESC"
        ):
            print(f"  {kind:<15} {n:>6}")

        print("--- totals ---")
        total_nodes = cur.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        total_edges = cur.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        total_flows = cur.execute("SELECT COUNT(*) FROM flows").fetchone()[0]
        total_files = cur.execute(
            "SELECT COUNT(DISTINCT file_path) FROM nodes WHERE file_path IS NOT NULL"
        ).fetchone()[0]
        print(f"  files : {total_files}")
        print(f"  nodes : {total_nodes}")
        print(f"  edges : {total_edges}")
        print(f"  flows : {total_flows}")

        archive_nodes = cur.execute(
            "SELECT COUNT(*) FROM nodes WHERE file_path LIKE '%archive%'"
        ).fetchone()[0]
        if total_nodes:
            pct = archive_nodes / total_nodes * 100
            label = "OK" if archive_nodes == 0 else "WARN"
            print(
                f"  archive share: {archive_nodes}/{total_nodes} nodes "
                f"({pct:.1f}%)  [{label}]"
            )
            if archive_nodes:
                print(
                    "    -> archive/** should be in .code-review-graphignore; "
                    "run rebuild_graph.cmd to purge."
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
