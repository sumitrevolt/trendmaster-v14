"""Compile AI_SUPERBB_v14_TrendMaster.mq5 via metaeditor64.exe CLI.

- Copies source from workspace into MT5 MQL5\\Experts\
- Runs metaeditor64.exe /compile /log
- Reads the UTF-16 LE log and prints the tail
"""

import os, shutil, subprocess, sys

SRC = r"C:\Users\Ratanshila\Documents\autmated trading\AI_SUPERBB_v14_TrendMaster.mq5"
TERM_DIR = r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075"
DST_DIR = os.path.join(TERM_DIR, "MQL5", "Experts")
DST = os.path.join(DST_DIR, "AI_SUPERBB_v14_TrendMaster.mq5")
EX5 = DST.replace(".mq5", ".ex5")
ME = r"C:\Program Files\MetaTrader 5\metaeditor64.exe"
LOG = DST.replace(".mq5", ".log")

os.makedirs(DST_DIR, exist_ok=True)
shutil.copy2(SRC, DST)
print(f"[copy] {SRC}\n    -> {DST} ({os.path.getsize(DST)} B)")

# Delete previous ex5 to ensure we detect failure
try:
    os.remove(EX5)
except FileNotFoundError:
    pass
try:
    os.remove(LOG)
except FileNotFoundError:
    pass

cmd = [ME, "/compile:" + DST, "/log:" + LOG]
print("[exec]", " ".join(cmd))
r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
print("[rc  ]", r.returncode)
if r.stdout.strip():
    print("[out ]", r.stdout)
if r.stderr.strip():
    print("[err ]", r.stderr)

# Read log (MT5 writes UTF-16 LE BOM)
if os.path.exists(LOG):
    raw = open(LOG, "rb").read()
    if raw.startswith(b"\xff\xfe"):
        txt = raw.decode("utf-16", errors="ignore")
    else:
        txt = raw.decode("utf-8", errors="ignore")
    print("--- COMPILE LOG ---")
    print(txt)
    print("--- END LOG ---")
else:
    print("[warn] no log file produced")

# Verify ex5 exists and is fresh
if os.path.exists(EX5):
    sz = os.path.getsize(EX5)
    print(f"[OK  ] produced {EX5}  ({sz} B)")
    sys.exit(0)
else:
    print(f"[FAIL] {EX5} NOT produced — compile failed")
    sys.exit(1)
