"""Sync trading_config.yaml trading_pairs to match settings.py concentrated 8.

Idempotent: if already synced, prints OK and exits 0.
Backup written to backup/<stamp>/trading_config.yaml by the calling cmd before this runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YAML = ROOT / "config" / "trading_config.yaml"

NEW_BLOCK = """trading_pairs:
  # Concentrated 8 — synced from settings.py 2026-05-08
  # (Sharpe-ranked top 2 per team; 10 dropped pairs preserved as comments in settings.py.)
  metals:    ["XAUUSD", "XAGUSD"]
  forex:     ["USDCHF", "AUDJPY"]
  crypto:    ["BTCUSD", "ETHUSD"]
  commodities: ["XTIUSD", "XNGUSD"]
"""


def main() -> int:
    if not YAML.exists():
        print(f"[X] {YAML} not found")
        return 1
    txt = YAML.read_text(encoding="utf-8")

    # Find the "trading_pairs:" section and the next top-level key (or EOF).
    lines = txt.splitlines(keepends=True)
    start_i = None
    end_i = None
    for i, line in enumerate(lines):
        if line.startswith("trading_pairs:"):
            start_i = i
            continue
        if start_i is not None and line and not line.startswith((" ", "\t", "#", "\n", "\r")):
            # next top-level key — end of trading_pairs block
            end_i = i
            break
    if start_i is None:
        print("[X] no `trading_pairs:` section found in YAML — refusing to write blindly")
        return 2
    if end_i is None:
        end_i = len(lines)

    current_block = "".join(lines[start_i:end_i]).rstrip() + "\n"
    if current_block.strip() == NEW_BLOCK.strip():
        print("  [OK] trading_pairs already synced (8 pairs)")
        return 0

    new_lines = lines[:start_i] + [NEW_BLOCK] + (lines[end_i:] if end_i < len(lines) else [])
    new_txt = "".join(new_lines)
    YAML.write_text(new_txt, encoding="utf-8")
    print("  [OK] trading_config.yaml trading_pairs replaced with concentrated 8")
    print(f"        (was {len(current_block.splitlines())} lines, now {len(NEW_BLOCK.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
