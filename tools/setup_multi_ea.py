"""
tools/setup_multi_ea.py — one-shot multi-symbol EA attachment.

What it does
------------
Builds a complete MT5 chart profile named `TrendMaster_v14_All19` that
contains 19 tiled charts (one per configured trading symbol), each with
AI_SUPERBB_v14_TrendMaster.ex5 attached and configured for multi-symbol
mode (`InpAIAutoPerSymbol=true`).

Why
---
The EA is already wired for multi-symbol filenames — it derives
`trendmaster_signals_<SYM>.json` per chart when attached. But nothing
in MT5 auto-attaches the EA to every chart; that's a manual drag-drop
per chart which is tedious for 19 symbols and gets undone on every
profile reset. This script does it once.

Usage
-----
    python tools/setup_multi_ea.py
    # → writes the profile under MT5 Profiles dir
    # In MT5: File > Profiles > TrendMaster_v14_All19
    # All 19 charts open with EA attached.

Safe to re-run. Backs up any existing profile with the same name.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from typing import List

# --- MT5 install locations ---
MT5_DATA_ROOT = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075")
PROFILES_DIR = MT5_DATA_ROOT / "MQL5" / "Profiles" / "Charts"
NEW_PROFILE_NAME = "TrendMaster_v14_All19"
NEW_PROFILE_DIR = PROFILES_DIR / NEW_PROFILE_NAME

ROOT = Path(__file__).resolve().parent.parent
EXPERT_BLOCK_SRC = ROOT / "tools" / "trendmaster_v14_expert_block.txt"


# Default symbols from config.settings. If settings isn't importable we
# fall back to a known-good list.
def _load_symbols() -> List[str]:
    try:
        sys.path.insert(0, str(ROOT))
        from config import settings as _s
        syms = list(_s.TRADING_PAIRS)
        if syms:
            return syms
    except Exception as e:
        print(f"[i] settings import failed ({e}); using fallback list")
    return [
        "XAUUSD", "XAGUSD",
        "GBPJPY", "USDCAD", "USDCHF", "EURUSD", "GBPUSD", "AUDUSD",
        "USDJPY", "NZDUSD", "EURJPY", "EURGBP", "AUDJPY", "CADJPY",
        "BTCUSD", "ETHUSD",
        "XTIUSD", "XBRUSD", "XNGUSD",
    ]


def _chart_template(symbol: str, chart_id: int, expert_block: str) -> str:
    """One chart file in MT5 profile format."""
    # The expert_block already starts with <expert> ... </expert>.
    # We wrap it in a minimal <chart> structure with H1 timeframe.
    # period_type=4 is H1, period_type=5 is H4, etc. Stick with H1
    # (matches the brain's primary_timeframe).
    period_type = 4
    # Ensure expert block has InpAIAutoPerSymbol=true — patch if legacy.
    eb = expert_block
    if "InpAIAutoPerSymbol" not in eb:
        eb = eb.replace(
            "</inputs>",
            "InpAIAutoPerSymbol=true\nInpAIPrimarySymbol=XAUUSD\n</inputs>",
        )
    return (
        "<chart>\n"
        f"id=131072{chart_id:04d}\n"
        f"symbol={symbol}\n"
        f"description=\n"
        f"period_type={period_type}\n"
        f"period_size=1\n"
        f"digits=5\n"
        f"tick_size=0.000000\n"
        f"position_time={int(time.time())}\n"
        f"scale_fix=0\n"
        f"scale_fixed_min=0.000000\n"
        f"scale_fixed_max=0.000000\n"
        f"scale_fix11=0\n"
        f"scale_bar=0\n"
        f"scale_bar_val=1.000000\n"
        f"scale=16\n"
        f"mode=1\n"
        f"fore=0\n"
        f"grid=0\n"
        f"volume=0\n"
        f"scroll=1\n"
        f"shift=1\n"
        f"shift_size=10.000000\n"
        f"fixed_pos=0.000000\n"
        f"ohlc=1\n"
        f"one_click=0\n"
        f"one_click_btn=1\n"
        f"bidline=1\n"
        f"askline=0\n"
        f"lastline=0\n"
        f"days=1\n"
        f"descriptions=1\n"
        f"tradelines=1\n"
        f"tradehistory=1\n"
        f"window_left=0\n"
        f"window_top=0\n"
        f"window_right=600\n"
        f"window_bottom=400\n"
        f"window_type=1\n"
        f"floating=0\n"
        f"floating_left=0\n"
        f"floating_top=0\n"
        f"floating_right=0\n"
        f"floating_bottom=0\n"
        f"floating_type=1\n"
        f"floating_toolbar=1\n"
        f"floating_tbstate=\n"
        f"background_color=0\n"
        f"foreground_color=16777215\n"
        f"barup_color=65280\n"
        f"bardown_color=65280\n"
        f"bullcandle_color=0\n"
        f"bearcandle_color=16777215\n"
        f"chartline_color=65280\n"
        f"volumes_color=3329330\n"
        f"grid_color=12632256\n"
        f"bidline_color=12632256\n"
        f"askline_color=255\n"
        f"lastline_color=12632256\n"
        f"stops_color=17919\n"
        f"windows_total=1\n\n"
        + eb + "\n"
        "<window>\n"
        "height=100.000000\n"
        "objects=0\n"
        "\n"
        "<indicator>\n"
        "name=Main\n"
        "path=\n"
        "apply=1\n"
        "show_data=1\n"
        "scale_inherit=0\n"
        "scale_line=0\n"
        "scale_line_percent=50\n"
        "scale_line_value=0.000000\n"
        "scale_fix_min=0\n"
        "scale_fix_min_val=0.000000\n"
        "scale_fix_max=0\n"
        "scale_fix_max_val=0.000000\n"
        "expertmode=0\n"
        "fixed_height=-1\n"
        "</indicator>\n"
        "</window>\n"
        "</chart>\n"
    )


def main() -> int:
    print("=" * 70)
    print("  TrendMaster v14 — multi-symbol EA auto-attach")
    print("=" * 70)

    if not MT5_DATA_ROOT.exists():
        print(f"[X] MT5 data root missing: {MT5_DATA_ROOT}")
        print("    Fix the hardcoded path at the top of this file.")
        return 1

    if not EXPERT_BLOCK_SRC.exists():
        print(f"[X] expert block file missing: {EXPERT_BLOCK_SRC}")
        return 1

    expert_block = EXPERT_BLOCK_SRC.read_text(encoding="ascii").strip()
    symbols = _load_symbols()
    print(f"[i] generating profile for {len(symbols)} symbols: "
          f"{', '.join(symbols)}")

    # Backup any existing profile.
    if NEW_PROFILE_DIR.exists():
        bk = NEW_PROFILE_DIR.parent / f"{NEW_PROFILE_NAME}.bak-{int(time.time())}"
        shutil.move(NEW_PROFILE_DIR, bk)
        print(f"[i] backed up existing profile → {bk.name}")

    NEW_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for i, sym in enumerate(symbols, start=1):
        chart_file = NEW_PROFILE_DIR / f"chart{i:02d}.chr"
        chart_file.write_text(
            _chart_template(sym, i, expert_block), encoding="utf-16-le",
        )
    # Write profile.ini enumerating the charts.
    lines = [
        "[Common]",
        f"Profile={NEW_PROFILE_NAME}",
        "WindowsTotal=" + str(len(symbols)),
    ]
    for i in range(1, len(symbols) + 1):
        lines.append(f"Window{i}=chart{i:02d}.chr")
    profile_ini = NEW_PROFILE_DIR / "profile.ini"
    profile_ini.write_text("\n".join(lines) + "\n", encoding="utf-16-le")

    print(f"\n[OK] profile written: {NEW_PROFILE_DIR}")
    print(f"     {len(symbols)} chart files + profile.ini")
    print("\nNext steps:")
    print(f"  1. In MT5:  File > Profiles > {NEW_PROFILE_NAME}")
    print( "  2. Verify each chart shows the AI_SUPERBB_v14_TrendMaster")
    print( "     smiley face in the top-right (Auto-Trading enabled).")
    print( "  3. Brain will write per-symbol signal files; EA on each")
    print( "     chart will auto-derive its filename via InpAIAutoPerSymbol.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
