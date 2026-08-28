"""Clean outputs/ folder — keep useful diagnostics, archive throwaway shell-escape cmds."""
from pathlib import Path
import shutil

OUT = Path(r"C:\Users\Ratanshila\Documents\autmated trading\outputs")
ARCHIVE = OUT / "_session_scratch"
ARCHIVE.mkdir(exist_ok=True)

# Keep — useful diagnostic scripts (referenced by workspace root cmd files OR
# generally useful for ops)
KEEP = {
    "close_all_now.py",          # used by CLOSE_ALL_NOW.cmd at root
    "check_mt5_positions.py",    # useful operational diagnostic
    "_session_scratch",
}

print(f"=== Cleaning {OUT} ===")
moved = 0
kept = 0
for f in OUT.iterdir():
    if f.is_dir():
        if f.name in KEEP:
            print(f"  KEEP  {f.name}/")
            kept += 1
        continue
    if f.name in KEEP:
        print(f"  KEEP  {f.name}")
        kept += 1
        continue
    target = ARCHIVE / f.name
    if target.exists():
        # already there
        continue
    try:
        shutil.move(str(f), str(target))
        moved += 1
    except Exception as e:
        print(f"  FAIL  {f.name}: {e}")

print(f"\n=== Summary: {kept} kept, {moved} moved to outputs/_session_scratch/ ===")
