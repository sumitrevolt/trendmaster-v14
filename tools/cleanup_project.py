"""
Organize the project into a clean v14-first layout.

ACTIVE (stay at root / in their v14 folders):
  AI_SUPERBB_v14_TrendMaster.mq5, START/STOP_TRENDMASTER_v14.bat
  ai_trading_agents/{trend_master_brain.py, __init__.py, requirements.txt}
  config/, data/, logs/, tools/, tests/
  *.md docs, README.md, requirements.txt, .gitignore

ARCHIVED (moved to archive/):
  all legacy EAs (v11, TradingView replica, MultiIndicator)
  all legacy Python (main.py, ai_swarm_main.py, safe_start.py, etc.)
  src/, backtesting/ entire folders
  all agent_*.json + .bak
  all mt5_*.png
  dashboards, legacy bat launchers
  __pycache__ (deleted)
"""
from __future__ import annotations
import shutil, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / "archive"
ARCH.mkdir(exist_ok=True)
(ARCH / "legacy_experts").mkdir(exist_ok=True)
(ARCH / "legacy_python").mkdir(exist_ok=True)
(ARCH / "legacy_state").mkdir(exist_ok=True)
(ARCH / "screenshots").mkdir(exist_ok=True)
(ARCH / "legacy_bat").mkdir(exist_ok=True)

moved = 0
deleted = 0

def move(rel: str, bucket: str) -> None:
    global moved
    src = ROOT / rel
    if not src.exists():
        return
    dst = ARCH / bucket / src.name
    if dst.exists():
        # numbered backup
        i = 1
        while (ARCH / bucket / f"{src.stem}_{i}{src.suffix}").exists():
            i += 1
        dst = ARCH / bucket / f"{src.stem}_{i}{src.suffix}"
    shutil.move(str(src), str(dst))
    print(f"[move] {rel:60s} -> archive/{bucket}/{dst.name}")
    moved += 1

def rmtree_if(rel: str) -> None:
    global deleted
    p = ROOT / rel
    if p.exists():
        shutil.rmtree(p)
        print(f"[rm]   {rel}")
        deleted += 1

# --- legacy EAs (root) ---
for f in ("AI_AMD_SMC_Indicator_v11.mq5",
          "AI_TradingView_Replica_v1.mq5"):
    move(f, "legacy_experts")

# legacy EAs inside ai_trading_agents/
for f in ("ai_trading_agents/AI_AMD_SMC_Indicator.mq5",
          "ai_trading_agents/MultiIndicatorSignals.mq5"):
    move(f, "legacy_experts")

# --- legacy Python entrypoints (root) ---
for f in ("main.py", "ai_swarm_main.py", "safe_start.py",
          "close_orphans.py", "run_backtest.py"):
    move(f, "legacy_python")

# legacy Python inside ai_trading_agents/ (keep ONLY trend_master_brain, __init__, requirements, .env*)
KEEP_IN_AGENTS = {
    "trend_master_brain.py", "__init__.py", "requirements.txt",
    ".env", ".env.example",
}
agents_dir = ROOT / "ai_trading_agents"
for p in list(agents_dir.iterdir()):
    if p.is_dir() and p.name in ("__pycache__",):
        rmtree_if(str(p.relative_to(ROOT)))
        continue
    if p.is_dir() and p.name == "tradingview_indicators":
        # whole subfolder is legacy
        shutil.move(str(p), str(ARCH / "legacy_python" / "tradingview_indicators"))
        print(f"[move] ai_trading_agents/tradingview_indicators -> archive/legacy_python/")
        moved += 1
        continue
    if p.is_dir():
        continue
    if p.name in KEEP_IN_AGENTS:
        continue
    # .bak files -> legacy_state
    bucket = "legacy_state" if p.suffix in (".bak", ".json", ".txt", ".log", ".html") else "legacy_python"
    move(f"ai_trading_agents/{p.name}", bucket)

# --- legacy bat launchers ---
for f in ("START_AI_SWARM.bat",):
    move(f, "legacy_bat")

# --- legacy folders (entire) ---
for d in ("src", "backtesting"):
    p = ROOT / d
    if p.exists():
        # move to archive
        shutil.move(str(p), str(ARCH / d))
        print(f"[move] {d}/ -> archive/{d}/")
        moved += 1

# --- screenshots ---
for p in list(ROOT.glob("mt5_*.png")):
    shutil.move(str(p), str(ARCH / "screenshots" / p.name))
    print(f"[move] {p.name} -> archive/screenshots/")
    moved += 1

# --- root misc ---
for f in ("QUICK_START.txt", "STATUS.json",
          "sync_engine.ps1", "trendmaster_signals.json"):
    move(f, "legacy_state")

# --- tools: remove legacy ---
for f in ("tools/visualize_swarm.py",):
    if (ROOT / f).exists():
        move(f, "legacy_python")

# --- __pycache__ everywhere ---
for p in ROOT.rglob("__pycache__"):
    if "archive" in p.parts:
        continue
    shutil.rmtree(p, ignore_errors=True)
    print(f"[rm]   {p.relative_to(ROOT)}")
    deleted += 1

# --- consolidate .pyc straggler files if any ---
for p in ROOT.rglob("*.pyc"):
    if "archive" in p.parts:
        continue
    p.unlink(missing_ok=True)

print()
print(f"DONE. moved={moved}  deleted={deleted}")
print(f"archive dir: {ARCH}")
