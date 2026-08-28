"""Audit which schtasks will pop up a terminal window."""
import subprocess
import re

# List all TrendMaster schtasks
out = subprocess.check_output(
    ["schtasks", "/Query", "/FO", "CSV", "/V"],
    timeout=15,
).decode("utf-8", "replace")

# Parse CSV
lines = out.splitlines()
header = lines[0].split('","')
header = [h.strip('"') for h in header]
name_idx = header.index("TaskName")
action_idx = header.index("Task To Run")

print(f"{'TaskName':<45} {'Hidden?':<10} {'Action'}")
print("-" * 130)

popups = []
for line in lines[1:]:
    parts = line.split('","')
    parts = [p.strip('"') for p in parts]
    if len(parts) <= max(name_idx, action_idx):
        continue
    name = parts[name_idx]
    if "TrendMaster" not in name:
        continue
    action = parts[action_idx]
    # Hidden if uses pythonw.exe OR wscript.exe
    is_hidden = (
        "pythonw.exe" in action.lower()
        or "wscript.exe" in action.lower()
        or ".vbs" in action.lower()
    )
    # If uses python.exe (not pythonw) or cmd.exe → will pop up
    will_popup = (
        ("python.exe" in action.lower() and "pythonw.exe" not in action.lower())
        or "cmd.exe" in action.lower()
        or ".cmd" in action.lower()
        or ".bat" in action.lower()
    )
    mark = "OK" if is_hidden else ("POPUP" if will_popup else "??")
    print(f"{name:<45} {mark:<10} {action[:80]}")
    if will_popup:
        popups.append((name, action))

print()
print(f"Total tasks that pop up: {len(popups)}")
for n, a in popups:
    print(f"  {n}")
    print(f"    {a}")
