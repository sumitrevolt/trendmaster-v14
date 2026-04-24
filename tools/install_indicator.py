"""
Install AI_AMD_SMC_Indicator v3.0 to MT5 MQL5/Indicators folder.
"""

import shutil, os

src = r"C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\AI_AMD_SMC_Indicator.mq5"

base = r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal"
found = []
if os.path.exists(base):
    for d in os.listdir(base):
        path = os.path.join(base, d, "MQL5", "Indicators")
        if os.path.exists(path):
            found.append(path)

print("MT5 Indicators folders found:")
for f in found:
    print(" ", f)

if found:
    dst = os.path.join(found[0], "AI_AMD_SMC_Indicator.mq5")
    shutil.copy2(src, dst)
    print(f"SUCCESS: Copied to {dst}")
    print("Now open MetaEditor in MT5 (press F4), find the file and press F7 to compile.")
else:
    print("MT5 folder NOT FOUND. Please copy manually:")
    print(f"  From: {src}")
    print(f"  To: MT5 -> File -> Open Data Folder -> MQL5 -> Indicators")
