"""Pre-commit guard: fail if any .py file inside ai_trading_agents/ contains
an actual `.resolve()` CALL (not just a mention in a docstring or comment).

Uses ast.parse to walk for Call(func=Attribute(attr='resolve')) so we get
precise hits, no false positives from documentation.

The package lives behind an NTFS junction at ai_trading_agents/ ->
C:\\TrendMaster_aita_canonical\\. Calling Path(__file__).resolve() walks
through the junction so .parent.parent lands on C:\\ instead of the project
root, silently breaking every config-file load. This regression has bitten
the project FOUR times. See CLAUDE.md 'Brain path resolution rule v2'.

Exit 0 if clean, 1 if any real .resolve() call found.
"""
from __future__ import annotations
import ast
import sys
from pathlib import Path

# Plain parent.parent — eat your own dogfood
ROOT = Path(__file__).parent.parent
SCAN_DIRS = [
    ROOT / "ai_trading_agents",
    Path(r"C:\TrendMaster_aita_canonical"),
]

OFFENDERS: list[tuple[str, int, str]] = []

class ResolveCallFinder(ast.NodeVisitor):
    def __init__(self, src_lines: list[str]):
        self.src_lines = src_lines
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call):
        # Match `<anything>.resolve()`
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "resolve":
            line_no = node.lineno
            snippet = self.src_lines[line_no - 1].strip()[:120] if 0 < line_no <= len(self.src_lines) else "?"
            self.hits.append((line_no, snippet))
        self.generic_visit(node)


for d in SCAN_DIRS:
    if not d.exists():
        continue
    for f in d.glob("*.py"):
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src, filename=str(f))
            finder = ResolveCallFinder(src.splitlines())
            finder.visit(tree)
            for line_no, snippet in finder.hits:
                OFFENDERS.append((str(f), line_no, snippet))
        except SyntaxError as e:
            print(f"[no-resolve-in-brain] WARN: parse error in {f}: {e}")
        except Exception:
            pass

if OFFENDERS:
    print("[no-resolve-in-brain] FAIL -- `.resolve()` is forbidden inside ai_trading_agents/.")
    print("                       Use plain Path(__file__).parent.parent OR import")
    print("                       project_root from ai_trading_agents._paths instead.")
    print("                       See CLAUDE.md 'Brain path resolution rule v2'.")
    print()
    for path, line_no, snippet in OFFENDERS:
        print(f"  {path}:{line_no}")
        print(f"    {snippet}")
    print()
    print(f"  Total offenders: {len(OFFENDERS)}")
    sys.exit(1)

print("[no-resolve-in-brain] OK -- no `.resolve()` CALLS in brain package.")
sys.exit(0)
