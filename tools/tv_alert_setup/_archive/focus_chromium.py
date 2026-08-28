"""Find the Playwright Chromium window and bring it to the foreground."""
import pygetwindow as gw
import sys
# Force UTF-8 stdout (Windows cp1252 chokes on TV emoji titles)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def _safe(s: str) -> str:
    return (s or "").encode("ascii", "replace").decode("ascii")

# Look for the Playwright Chromium window. Title patterns:
#   "TradingView ..." (after TV loads)
#   Or empty / "about:blank" before page loads
print("=== All visible windows ===")
for w in gw.getAllWindows():
    if not w.title.strip():
        continue
    print(f"  {_safe(w.title)!r:60} pos=({w.left},{w.top}) size={w.width}x{w.height}")

print()
print("=== matching candidates (TradingView/Chromium/about:blank) ===")
candidates = [w for w in gw.getAllWindows()
              if w.title and "Chrome for Testing" in w.title]
if not candidates:
    candidates = [w for w in gw.getAllWindows()
                  if w.title and any(s in w.title for s in ("Chromium", "about:blank"))]
for w in candidates:
    print(f"  {_safe(w.title)!r:60} pos=({w.left},{w.top}) size={w.width}x{w.height}")

# Pick best candidate — prefer Chromium-titled or TradingView-titled non-Antigravity windows
target = None
for w in candidates:
    if "Antigravity" in w.title:
        continue
    target = w
    break

if target:
    print(f"\nFOCUSING: {_safe(target.title)!r}")
    try:
        if target.isMinimized:
            target.restore()
        target.activate()
        print("OK — window brought to foreground")
    except Exception as e:
        print(f"Activate failed: {e}")
else:
    print("\n[!] No Playwright Chromium window found.")
    print("    The browser may be still loading, or it crashed silently.")
    sys.exit(1)
