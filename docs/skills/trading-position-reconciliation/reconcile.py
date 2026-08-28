"""
Three-way position reconciliation for TrendMaster v14.

Compares:
  - Live MT5 broker positions (via MetaTrader5 module)
  - brain_memory.json::open_positions
  - logs/brain_state.json::open_positions

Flags drift; prints recommended manual fix commands. Never mutates state.

Pure-Python; only stdlib + MetaTrader5 (already in .venv per project).
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
MEMORY_PATH = REPO_ROOT / "brain_memory.json"
STATE_PATH = REPO_ROOT / "logs" / "brain_state.json"


def normalize_position(p: dict) -> tuple:
    """Tuple-key for cross-source comparison: (symbol, side, lots-rounded)."""
    return (
        str(p.get("symbol", "")).upper(),
        str(p.get("side", "")).lower(),
        round(float(p.get("lots", p.get("volume", 0))), 2),
    )


def load_file_positions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        d = json.loads(path.read_text())
    except Exception:
        return []
    return d.get("open_positions", []) or []


def load_mt5_positions(no_mt5: bool) -> list[dict] | None:
    if no_mt5:
        return None
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError:
        return None
    if not mt5.initialize():
        return None
    try:
        ps = mt5.positions_get()
        if ps is None:
            return []
        out = []
        for p in ps:
            out.append({
                "symbol": p.symbol,
                "side": "long" if p.type == 0 else "short",
                "lots": float(p.volume),
                "entry_px": float(p.price_open),
                "sl_px": float(p.sl) if p.sl else None,
                "ticket": int(p.ticket),
            })
        return out
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


def render_set(name: str, positions: list[dict] | None) -> str:
    if positions is None:
        return f"{name:36s} UNAVAILABLE (MT5 disconnected or module missing)"
    out = [f"{name:36s} {len(positions)} positions:"]
    for p in positions[:12]:
        sl = f"SL {p['sl_px']}" if p.get("sl_px") else "no SL"
        ticket = f"  ticket {p['ticket']}" if p.get("ticket") else ""
        out.append(
            f"  {p.get('symbol'):8s} {p.get('side'):5s} {p.get('lots')} lots @ "
            f"{p.get('entry_px')}  {sl}{ticket}"
        )
    return "\n".join(out)


def diff_sets(a_name: str, a: list[dict], b_name: str, b: list[dict]) -> list[str]:
    a_keys = {normalize_position(p): p for p in a}
    b_keys = {normalize_position(p): p for p in b}
    only_a = a_keys.keys() - b_keys.keys()
    only_b = b_keys.keys() - a_keys.keys()
    diffs = []
    for k in only_a:
        diffs.append(f"  {a_name} has {k}, NOT in {b_name}")
    for k in only_b:
        diffs.append(f"  {b_name} has {k}, NOT in {a_name}")
    return diffs


def detect_race(memory_path: Path, state_path: Path) -> bool:
    """If memory and state mtimes differ by <500ms and they disagree, suspect a race."""
    if not (memory_path.exists() and state_path.exists()):
        return False
    dt = abs(memory_path.stat().st_mtime - state_path.stat().st_mtime)
    return dt < 0.5


def render_recs(mt5_pos, mem_pos, state_pos) -> list[str]:
    out = ["", "RECOMMENDED ACTIONS (manual; this skill never mutates state):"]
    if mt5_pos is not None:
        mt5_keys = {normalize_position(p) for p in mt5_pos}
        mem_keys = {normalize_position(p) for p in mem_pos}
        for k in (mem_keys - mt5_keys):
            sym = k[0]
            out.append(f"  - {sym}: in brain_memory but NOT in MT5 - likely SL hit or manual close.")
            out.append(f"      Inspect: .venv\\Scripts\\python.exe tools\\diagnose_zero_trades.py --symbol {sym}")
        for k in (mt5_keys - mem_keys):
            sym = k[0]
            out.append(f"  - {sym}: in MT5 but NOT in brain_memory - manual trade or post-restart drift.")
            out.append(f"      Inspect: tools\\diagnose_zero_trades.py --symbol {sym} --window 24h")
    out.append("")
    out.append("DO NOT use taskkill /F to force-sync. Restart via start_brain_clean.cmd.")
    out.append("DO NOT mutate brain_memory.json without first inspecting MT5 history.")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mt5", action="store_true", help="Skip live MT5 query (file-only diff)")
    args = ap.parse_args()

    mt5_pos = load_mt5_positions(args.no_mt5)
    mem_pos = load_file_positions(MEMORY_PATH)
    state_pos = load_file_positions(STATE_PATH)

    print("Position Reconciliation - " + datetime.now().strftime("%Y-%m-%d %H:%M local"))
    print("=" * 50)
    print(render_set("MT5 broker (authoritative)", mt5_pos))
    print()
    print(render_set("brain_memory.json::open_positions", mem_pos))
    print()
    print(render_set("state_store.json::open_positions", state_pos))
    print()

    diffs = []
    if mt5_pos is not None:
        diffs += diff_sets("MT5", mt5_pos, "brain_memory", mem_pos)
        diffs += diff_sets("MT5", mt5_pos, "state_store", state_pos)
    diffs += diff_sets("brain_memory", mem_pos, "state_store", state_pos)

    if not diffs:
        print("DRIFT DETECTED: none - all sources agree.")
        return

    print("DRIFT DETECTED:")
    for d in diffs:
        print(d)
    if detect_race(MEMORY_PATH, STATE_PATH):
        print("  (mtime delta <500ms - RACE_SUSPECTED rather than STATE_DRIFT)")
    print("\n".join(render_recs(mt5_pos, mem_pos, state_pos)))


if __name__ == "__main__":
    main()
