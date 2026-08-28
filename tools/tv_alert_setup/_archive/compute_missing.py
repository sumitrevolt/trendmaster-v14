"""Compute which (symbol, TF) Rocket Prime alerts are MISSING from TV."""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
INVENTORY_PATH = HERE / "alerts_full_inventory.json"

# Target: 19 symbols × 4 TFs (TV resolution strings: 5/15/60/240)
SYMBOLS = [
    "XAUUSD", "XAGUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY",
    "CADJPY", "EURGBP",
    "BTCUSD", "ETHUSD",
    "XTIUSD", "XBRUSD", "XNGUSD",
]
TF_MAP = {"M5": "5", "M15": "15", "H1": "60", "H4": "240"}

# Exchange per symbol
def _exchange(s: str) -> str:
    if s in ("BTCUSD", "ETHUSD"): return "BINANCE"
    if s in ("XTIUSD", "XBRUSD", "XNGUSD"): return "TVC"
    return "OANDA"

def _broker_sym(s: str) -> str:
    return {"XTIUSD": "USOIL", "XBRUSD": "UKOIL", "XNGUSD": "NATGASUSD"}.get(s, s)

# Rocket Prime pine_id from earlier discovery
ROCKET_PRIME_PINE_ID = "PUB;56f0fb74de7f4eed9325b987428b727e"

data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
alerts = data.get("r", [])

# Build set of existing (symbol, resolution) pairs that use Rocket Prime
existing = set()
for a in alerts:
    cond = a.get("condition") or {}
    if cond.get("type") != "pine_alert":
        continue
    series = cond.get("series") or [{}]
    if series[0].get("pine_id") != ROCKET_PRIME_PINE_ID:
        continue
    sym_raw = a.get("symbol", "")
    try:
        sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
        sym = sym_obj.get("symbol", "")
    except Exception:
        sym = sym_raw
    existing.add((sym, str(a.get("resolution", ""))))

print(f"=== Existing Rocket Prime alerts: {len(existing)} ===")
for s, r in sorted(existing):
    print(f"  {s:<25} res={r}")

print(f"\n=== Building target list (19 × 4 = 76) ===")
missing = []
have_symbols = set()
for sym in SYMBOLS:
    full_sym = f"{_exchange(sym)}:{_broker_sym(sym)}"
    have_symbols.add(full_sym)
    for tf, res in TF_MAP.items():
        key = (full_sym, res)
        if key not in existing:
            missing.append({
                "symbol": sym,
                "exchange": _exchange(sym),
                "broker_symbol": _broker_sym(sym),
                "full_symbol": full_sym,
                "tf": tf,
                "resolution": res,
            })

# Existing alerts that aren't in our target list (extras / different exchanges)
extras = sorted(existing - {(f"{_exchange(s)}:{_broker_sym(s)}", r)
                              for s in SYMBOLS for r in TF_MAP.values()})

print(f"\n=== MISSING alerts: {len(missing)} ===")
by_tf = {}
for m in missing:
    by_tf.setdefault(m["tf"], []).append(m["symbol"])
for tf, syms in sorted(by_tf.items()):
    print(f"  {tf}: {len(syms)} - {', '.join(syms)}")

print(f"\n=== EXTRAS (existing but outside target 19×4): {len(extras)} ===")
for s, r in extras:
    print(f"  {s} res={r}")

# Save for later replay
out_path = HERE / "missing_alerts.json"
out_path.write_text(json.dumps(missing, indent=2), encoding="utf-8")
print(f"\nSaved {len(missing)} missing alerts spec -> {out_path}")
