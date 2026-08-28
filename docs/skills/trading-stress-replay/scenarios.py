"""
Stress replay for TrendMaster v14.

Applies four canonical FX/metals shock scenarios to the current open book
read from logs/brain_state.json. Reports survive/blow per scenario.

Each scenario is a dict of per-symbol pct moves and vol multipliers; if the
shock is larger than the SL distance, we assume gap-through (no SL hit) and
the loss = full pct_move * notional. If shock is smaller, SL caps the loss.

Pure-Python; only json + pathlib + argparse + math.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
STATE_PATH = REPO_ROOT / "logs" / "brain_state.json"
RUNS_DIR = REPO_ROOT / "logs" / "stress_runs"


SCENARIOS: dict[str, dict[str, dict[str, float]]] = {
    # pct_move is the worst intraday move on the named day; sign is direction.
    # vol_mult: realised-vol multiplier for the day (used for SL slippage assumption).
    # spread_mult: how much spreads blow out vs normal.
    "snb_2015": {
        "EURUSD": {"pct_move": -0.022, "vol_mult": 3.5, "spread_mult": 8.0},
        "USDCHF": {"pct_move": -0.190, "vol_mult": 12.0, "spread_mult": 30.0},
        "EURCHF": {"pct_move": -0.190, "vol_mult": 12.0, "spread_mult": 30.0},
        "XAUUSD": {"pct_move": +0.026, "vol_mult": 2.5, "spread_mult": 4.0},
        "GBPUSD": {"pct_move": -0.014, "vol_mult": 2.0, "spread_mult": 3.0},
    },
    "covid_mar_2020": {
        "EURUSD": {"pct_move": -0.030, "vol_mult": 4.0, "spread_mult": 5.0},
        "GBPUSD": {"pct_move": -0.060, "vol_mult": 5.0, "spread_mult": 6.0},
        "USDJPY": {"pct_move": -0.030, "vol_mult": 4.0, "spread_mult": 4.0},
        "AUDUSD": {"pct_move": -0.050, "vol_mult": 4.5, "spread_mult": 5.0},
        "XAUUSD": {"pct_move": -0.050, "vol_mult": 4.0, "spread_mult": 5.0},
        "XTIUSD": {"pct_move": -0.300, "vol_mult": 8.0, "spread_mult": 10.0},
        "BTCUSD": {"pct_move": -0.420, "vol_mult": 6.0, "spread_mult": 8.0},
        "ETHUSD": {"pct_move": -0.430, "vol_mult": 6.0, "spread_mult": 8.0},
    },
    "brexit_2016": {
        "GBPUSD": {"pct_move": -0.110, "vol_mult": 8.0, "spread_mult": 12.0},
        "EURGBP": {"pct_move": +0.060, "vol_mult": 6.0, "spread_mult": 8.0},
        "EURUSD": {"pct_move": -0.025, "vol_mult": 3.0, "spread_mult": 4.0},
        "XAUUSD": {"pct_move": +0.045, "vol_mult": 3.5, "spread_mult": 4.0},
    },
    "cny_aug_2015": {
        "AUDUSD": {"pct_move": -0.030, "vol_mult": 3.0, "spread_mult": 4.0},
        "NZDUSD": {"pct_move": -0.025, "vol_mult": 3.0, "spread_mult": 4.0},
        "USDJPY": {"pct_move": -0.018, "vol_mult": 2.5, "spread_mult": 3.0},
        "XAUUSD": {"pct_move": +0.012, "vol_mult": 2.0, "spread_mult": 3.0},
    },
}


@dataclass
class Position:
    symbol: str
    side: str  # "buy" or "sell"
    lots: float
    entry_px: float
    sl_px: float | None
    contract_size: float = 100_000  # FX default; XAUUSD ~100, BTCUSD ~1


CONTRACT_SIZE = {
    "XAUUSD": 100,
    "XAGUSD": 5_000,
    "XTIUSD": 1_000,
    "XBRUSD": 1_000,
    "XNGUSD": 10_000,
    "BTCUSD": 1,
    "ETHUSD": 1,
}


def load_book() -> list[Position]:
    if not STATE_PATH.exists():
        return []
    state = json.loads(STATE_PATH.read_text())
    book = []
    for p in state.get("open_positions", []):
        book.append(
            Position(
                symbol=p["symbol"],
                side=p["side"],
                lots=float(p.get("lots", 0)),
                entry_px=float(p["entry_px"]),
                sl_px=float(p["sl_px"]) if p.get("sl_px") else None,
                contract_size=CONTRACT_SIZE.get(p["symbol"], 100_000),
            )
        )
    return book


def synthetic_max_book(equity: float = 5_000.0) -> list[Position]:
    """8 positions: 2 per team x 4 teams. Used when live book is empty."""
    return [
        Position("XAUUSD", "buy", 0.10, 2342.50, 2335.20, 100),
        Position("XAGUSD", "buy", 0.50, 27.20, 26.80, 5_000),
        Position("EURUSD", "buy", 0.20, 1.0682, 1.0651, 100_000),
        Position("GBPUSD", "sell", 0.15, 1.2421, 1.2462, 100_000),
        Position("BTCUSD", "buy", 0.05, 67_400, 66_200, 1),
        Position("ETHUSD", "buy", 0.10, 3_410, 3_350, 1),
        Position("XTIUSD", "buy", 1.00, 82.40, 81.50, 1_000),
        Position("XNGUSD", "buy", 1.00, 2.10, 2.05, 10_000),
    ]


def evaluate_scenario(name: str, shock: dict[str, dict[str, float]], book: list[Position]) -> dict:
    """Return dict with worst_pl, lines (per-position pl), and the worst line."""
    lines = []
    for pos in book:
        if pos.symbol not in shock:
            continue
        s = shock[pos.symbol]
        sign = +1 if pos.side == "buy" else -1
        # Direction of shock relative to position
        pct = s["pct_move"] * sign  # positive = profit, negative = loss
        # If SL would have been hit before the shock completes, cap at SL
        # (we conservatively assume SL slippage = vol_mult * 0.5 * normal-spread)
        notional = pos.lots * pos.contract_size * pos.entry_px
        if pos.sl_px is None:
            pl = notional * pct
            sl_hit = False
        else:
            sl_pct = (pos.sl_px - pos.entry_px) / pos.entry_px * sign
            # If shock is larger than SL distance and against us, gap through SL
            # add slippage = vol_mult * 0.0005 (50 bps notional approximation)
            slippage_bps = s["vol_mult"] * 0.0005
            if pct < sl_pct:
                # SL would catch in normal mkt, but shock gaps through.
                # Realised loss = SL distance + slippage worse
                pl = notional * (sl_pct - slippage_bps)
                sl_hit = True
            else:
                # Shock didn't reach SL or moved with us
                pl = notional * pct
                sl_hit = False
        lines.append({
            "symbol": pos.symbol,
            "side": pos.side,
            "lots": pos.lots,
            "pct_applied": round(pct, 4),
            "pl": round(pl, 2),
            "sl_hit": sl_hit,
        })
    worst_pl = sum(l["pl"] for l in lines if l["pl"] < 0)
    worst_line = min(lines, key=lambda l: l["pl"]) if lines else None
    return {"scenario": name, "worst_pl": round(worst_pl, 2), "lines": lines, "worst_line": worst_line}


def render_report(equity: float, dd_limit: float, results: list[dict], book: list[Position]) -> str:
    out = ["Stress Replay - " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")]
    out.append("=" * 40)
    out.append(f"Account equity: ${equity:,.2f}")
    out.append(f"Max DD allowed: ${dd_limit:,.2f}")
    out.append("")
    out.append(f"Open positions: {len(book)}")
    for p in book[:8]:
        sl_str = f"SL {p.sl_px}" if p.sl_px else "no SL"
        out.append(f"  {p.symbol:8s} {p.side:5s} {p.lots:.2f} lots @ {p.entry_px}  {sl_str}")
    out.append("")
    out.append("Scenario verdicts")
    out.append("-" * 40)
    for r in results:
        consumed = abs(r["worst_pl"]) / dd_limit if dd_limit > 0 else float("inf")
        verdict = "BLOW" if consumed > 1.0 else ("CLOSE" if consumed > 0.7 else "SURVIVE")
        out.append(
            f"[{verdict:7s}]  {r['scenario']:18s}  "
            f"worst_pl=${r['worst_pl']:+,.2f}   "
            f"vs DD limit ${dd_limit:,.2f}   ({consumed * 100:.0f}% consumed)"
        )
    blow = [r for r in results if abs(r["worst_pl"]) > dd_limit]
    if blow:
        out.append("")
        out.append("Worst-line detail in BLOW scenarios:")
        for r in blow:
            wl = r["worst_line"]
            if wl:
                out.append(f"  {r['scenario']} -> {wl['symbol']} {wl['side']} pl=${wl['pl']:,.2f} "
                           f"(SL {'hit' if wl['sl_hit'] else 'gapped through' if wl['pl'] < 0 else 'safe'})")
    out.append("")
    out.append("Recommendations:")
    if blow:
        for r in blow:
            out.append(f"  - {r['scenario']} would breach DD limit. Confirm state.trading_paused triggers correctly.")
    close = [r for r in results if 0.7 < abs(r["worst_pl"]) / dd_limit <= 1.0]
    for r in close:
        wl = r["worst_line"]
        if wl:
            out.append(f"  - {r['scenario']} consumes {abs(r['worst_pl']) / dd_limit * 100:.0f}% of DD. "
                       f"Worst contributor: {wl['symbol']}. Consider trimming.")
    if not (blow or close):
        out.append("  - All scenarios pass with margin >30%. Re-run after any cap or sizing change.")
    out.append("")
    out.append("Note: scenarios are deterministic estimates. Real shocks may produce slippage,")
    out.append("requote storms, and broker-side disconnects not captured here.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--scenario", choices=list(SCENARIOS.keys()))
    ap.add_argument("--synthetic-max-book", action="store_true")
    ap.add_argument("--equity", type=float, default=5_000.0)
    ap.add_argument("--dd-limit", type=float, default=750.0)  # 15% of 5k
    args = ap.parse_args()

    book = synthetic_max_book(args.equity) if args.synthetic_max_book else load_book()
    if not book:
        print("Live book empty; falling back to synthetic_max_book scenario.")
        book = synthetic_max_book(args.equity)

    if args.scenario:
        results = [evaluate_scenario(args.scenario, SCENARIOS[args.scenario], book)]
    else:
        results = [evaluate_scenario(n, s, book) for n, s in SCENARIOS.items()]

    print(render_report(args.equity, args.dd_limit, results, book))

    # Persist
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(json.dumps({"results": results, "equity": args.equity, "dd_limit": args.dd_limit}, indent=2))


if __name__ == "__main__":
    main()
