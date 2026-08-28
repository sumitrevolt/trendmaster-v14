"""Strip all indicators from MT5 chart files while preserving the EA.

Modifies every `chart##.chr` in the Default profile so:
  - all `<indicator>...</indicator>` blocks are removed
  - all `<window>...</window>` sections except the main one are removed
  - `windows_total` is reset to 1
  - `InpAutoAddStdIndicators=true` → `false` (so EA doesn't re-add them on attach)
The `<expert>...</expert>` block (your EA + its inputs) is preserved untouched.

Backup is taken first into Charts\Default.bak_<unix-ts>\.

Usage:
    python tools\strip_mt5_indicators.py
After running, CLOSE MT5 cleanly (so it doesn't overwrite our edits with its
in-memory state), then RESTART MT5 — your charts will show only the EA's
🙂 / 😞 icon, no indicator overlays.
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

CHARTS_DIR = Path(
    r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal"
    r"\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Profiles\Charts\Default"
)


def detect_encoding(path: Path) -> str:
    """MT5 .chr files are usually UTF-16-LE with BOM, sometimes ANSI."""
    head = path.read_bytes()[:4]
    if head[:2] == b"\xff\xfe":
        return "utf-16-le"
    if head[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    return "ansi"


def strip_one(path: Path) -> tuple[int, int]:
    """Returns (indicators_removed, extra_windows_removed)."""
    enc = detect_encoding(path)
    text = path.read_text(encoding=enc, errors="replace")

    # Count what we will remove
    n_inds = len(re.findall(r"<indicator>", text))

    # 1) Remove every `<indicator>...</indicator>` block (and its trailing newline).
    text = re.sub(
        r"<indicator>.*?</indicator>\r?\n?",
        "",
        text,
        flags=re.DOTALL,
    )

    # 2) Remove every `<window>...</window>` block AFTER the first one.
    # The chart can have <window> appearing multiple times. We keep only the
    # very first <window> (the main price pane) and chop everything from the
    # 2nd <window> tag through the last </window> in the file.
    matches = list(re.finditer(r"<window>", text))
    n_windows_extra = max(0, len(matches) - 1)
    if n_windows_extra > 0:
        # find the start of the 2nd window block
        second_start = matches[1].start()
        # find the last </window>
        last_close = text.rfind("</window>")
        if last_close > second_start:
            text = text[:second_start] + text[last_close + len("</window>") :].lstrip("\r\n")

    # 3) windows_total -> 1 (regardless of original value)
    text = re.sub(r"^windows_total=\d+", "windows_total=1", text, flags=re.MULTILINE)

    # 4) Disable EA auto-add indicators
    text = re.sub(r"InpAutoAddStdIndicators=true", "InpAutoAddStdIndicators=false", text)

    path.write_text(text, encoding=enc)
    return n_inds, n_windows_extra


def main() -> int:
    if not CHARTS_DIR.exists():
        print(f"[X] Charts dir not found: {CHARTS_DIR}", file=sys.stderr)
        return 1

    # Backup first
    ts = int(time.time())
    backup = CHARTS_DIR.parent / f"Default.bak_indicators_strip_{ts}"
    shutil.copytree(CHARTS_DIR, backup)
    print(f"[+] Backup: {backup}")

    chart_files = sorted(CHARTS_DIR.glob("chart*.chr"))
    if not chart_files:
        print("[!] No chart files found to clean.")
        return 0

    total_inds = 0
    total_wins = 0
    for c in chart_files:
        try:
            n_i, n_w = strip_one(c)
            total_inds += n_i
            total_wins += n_w
            print(f"  {c.name:20s}  -{n_i} indicators, -{n_w} extra windows")
        except Exception as e:
            print(f"  {c.name:20s}  FAILED: {e}", file=sys.stderr)

    print()
    print(f"[+] Done. Cleaned {len(chart_files)} chart files.")
    print(f"    Removed {total_inds} indicator blocks")
    print(f"    Removed {total_wins} extra window panels")
    print()
    print("Next steps:")
    print("  1. Close MT5 from File -> Exit (so it doesn't overwrite the .chr files)")
    print("  2. Restart MT5")
    print("  3. Charts will show no indicators, only the EA smiley icon")
    print()
    print(f"Rollback if needed:")
    print(f"  rmdir /s /q \"{CHARTS_DIR}\"")
    print(f"  move \"{backup}\" \"{CHARTS_DIR}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
