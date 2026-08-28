"""One-shot diagnostic: why are FOREX and COMMODITIES silent?

Reads logs/brain_state.json and logs/brain_memory.json (both already on
disk; does not touch MT5) and reports:
  - per-team trade count from trade_history
  - last veto per symbol, grouped by team
  - veto-reason frequency by team
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TEAMS = {
    "METALS":      {"XAUUSD", "XAGUSD"},
    "FOREX":       {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"},
    "CRYPTO":      {"BTCUSD", "ETHUSD"},
    "COMMODITIES": {"XTIUSD", "XBRUSD", "XNGUSD"},
}


def team_of(symbol: str) -> str:
    for t, syms in TEAMS.items():
        if symbol in syms:
            return t
    return "UNKNOWN"


def main() -> int:
    state_path  = REPO_ROOT / "logs" / "brain_state.json"
    memory_path = REPO_ROOT / "logs" / "brain_memory.json"

    if not state_path.exists():
        print(f"[ERROR] {state_path} missing - is the brain running / has it run?")
        return 2
    if not memory_path.exists():
        print(f"[ERROR] {memory_path} missing")
        return 2

    state  = json.loads(state_path.read_text(encoding="utf-8"))
    memory = json.loads(memory_path.read_text(encoding="utf-8"))

    # --- 1. trade count by team --------------------------------------------
    trades = memory.get("trade_history") or []
    team_trade_ct: Counter = Counter()
    for t in trades:
        team_trade_ct[team_of(t.get("symbol", ""))] += 1

    print("=" * 60)
    print("Trade count per team (from brain_memory.trade_history)")
    print("=" * 60)
    for team in ["METALS", "FOREX", "CRYPTO", "COMMODITIES"]:
        print(f"  {team:12}  {team_trade_ct.get(team, 0)}")
    print(f"  {'TOTAL':12}  {sum(team_trade_ct.values())}")

    # --- 2. last veto per symbol, grouped by team --------------------------
    vetoes = state.get("last_veto_per_symbol") or {}
    by_team: dict = defaultdict(list)
    for sym, v in vetoes.items():
        by_team[team_of(sym)].append(
            (sym, v.get("gate", "-"), v.get("reason", "-"), v.get("ts", "-"))
        )

    print()
    print("=" * 60)
    print("Last veto per symbol (from state.last_veto_per_symbol)")
    print("=" * 60)
    for team in ["METALS", "FOREX", "CRYPTO", "COMMODITIES"]:
        print(f"\n{team}:")
        entries = by_team.get(team, [])
        if not entries:
            print("  (no recent vetoes recorded)")
            continue
        for sym, gate, reason, ts in entries:
            reason_short = (reason[:80] + "...") if len(str(reason)) > 80 else reason
            print(f"  {sym:10}  gate={gate:<22}  reason={reason_short}")

    # --- 3. gate-reason frequency per team ---------------------------------
    print()
    print("=" * 60)
    print("Gate frequency per team (from veto records)")
    print("=" * 60)
    for team in ["METALS", "FOREX", "CRYPTO", "COMMODITIES"]:
        gate_ct: Counter = Counter()
        for _, gate, _, _ in by_team.get(team, []):
            gate_ct[gate] += 1
        print(f"\n{team}:")
        if not gate_ct:
            print("  (no gates recorded)")
            continue
        for gate, n in gate_ct.most_common(10):
            print(f"  {n:3}  {gate}")

    # --- 4. symbol config check --------------------------------------------
    print()
    print("=" * 60)
    print("Symbols in last_veto log vs. configured TEAMS")
    print("=" * 60)
    in_log    = set(vetoes.keys())
    expected  = set().union(*TEAMS.values())
    missing   = expected - in_log
    unexpected = in_log - expected
    if missing:
        print("Symbols we expect but NO veto recorded (either trading fine OR never scanned):")
        for s in sorted(missing):
            print(f"  {s}  (team={team_of(s)})")
    if unexpected:
        print("\nSymbols in veto log that aren't in our TEAMS mapping:")
        for s in sorted(unexpected):
            print(f"  {s}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
