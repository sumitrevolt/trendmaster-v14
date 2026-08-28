"""Bulk-patch all hidden_*.vbs files to remove `cmd /c ... >> log` pattern.

Replaces:
  sh.Run "cmd /c "".venv\Scripts\python.exe"" PATH >> log 2>&1", 0, False
With:
  sh.Run """.venv\Scripts\pythonw.exe"" PATH", 0, False

This eliminates the visible cmd flash + redirect (Python scripts must do their
own file logging via logging.FileHandler).

Switches python.exe → pythonw.exe (no console at all).
"""
import re
import sys
from pathlib import Path

LOG = Path(r"C:\Users\Ratanshila\Documents\autmated trading\outputs\patch_all_vbs.log")
TOOLS = Path(r"C:\Users\Ratanshila\Documents\autmated trading\tools")

_log_lines = []
def log(msg):
    _log_lines.append(msg)
    print(msg)


# Pattern: sh.Run "cmd /c ""<EXE>"" <ARGS> >> log 2>&1", 0, False
# Also handles: cmd /c set FOO=BAR && ""<EXE>"" <ARGS> >> log 2>&1
PATTERN = re.compile(
    r'sh\.Run\s+"cmd /c\s+(?:set [^&]+&&\s+)?""([^"]+\.exe)""\s+(.*?)\s+>>\s+[^"]+\s+2>&1"\s*,\s*0\s*,\s*False',
    re.IGNORECASE,
)

patched = []
for vbs in sorted(TOOLS.glob("hidden_*.vbs")):
    text = vbs.read_text(encoding="utf-8")
    match = PATTERN.search(text)
    if not match:
        continue

    exe = match.group(1)
    args = match.group(2)

    # Convert python.exe → pythonw.exe (drop console)
    new_exe = exe.replace("python.exe", "pythonw.exe")

    new_run = f'sh.Run """{new_exe}"" {args}", 0, False'
    new_text = PATTERN.sub(new_run, text)

    if new_text != text:
        vbs.write_text(new_text, encoding="utf-8")
        patched.append(vbs.name)
        log(f"  patched {vbs.name}: {exe} {args[:60]}...")

log(f"\nTotal patched: {len(patched)}")
for p in patched:
    log(f"  - {p}")

LOG.write_text("\n".join(_log_lines), encoding="utf-8")
