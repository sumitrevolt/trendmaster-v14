"""Verify 2026-05-17 safeguards changes import + work as expected."""
import sys
import json
import traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

RESULTS_PATH = ROOT / "outputs" / "verify_results.json"

results = {"checks": [], "errors": []}

def save():
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

# 1. Import safeguards
try:
    import safeguards
    results["checks"].append(("import_safeguards", True))
    save()
except Exception as e:
    results["errors"].append(f"safeguards import: {e}\n{traceback.format_exc()}")
    save()
    raise SystemExit(1)

# 2. _usd_side: crypto must return 0
btc_buy = safeguards._usd_side("BTCUSD", True)
btc_sell = safeguards._usd_side("BTCUSD", False)
eth_buy = safeguards._usd_side("ETHUSD", True)
eth_sell = safeguards._usd_side("ETHUSD", False)
results["checks"].append(("BTCUSD_BUY_usd_side", btc_buy, "expected 0"))
results["checks"].append(("BTCUSD_SELL_usd_side", btc_sell, "expected 0"))
results["checks"].append(("ETHUSD_BUY_usd_side", eth_buy, "expected 0"))
results["checks"].append(("ETHUSD_SELL_usd_side", eth_sell, "expected 0"))

# 3. _usd_side: USDJPY/GBPUSD still work
usdjpy_buy = safeguards._usd_side("USDJPY", True)
gbpusd_sell = safeguards._usd_side("GBPUSD", False)
results["checks"].append(("USDJPY_BUY_usd_side", usdjpy_buy, "expected +1 long-USD"))
results["checks"].append(("GBPUSD_SELL_usd_side", gbpusd_sell, "expected +1 long-USD"))

# 4. time_of_day_blackout: BTC/ETH always allowed
btc_tod = safeguards.time_of_day_blackout("BTCUSD", "BUY")
eth_tod = safeguards.time_of_day_blackout("ETHUSD", "SELL")
results["checks"].append(("BTCUSD_time_blackout", btc_tod, "expected (False, '...exempt...')"))
results["checks"].append(("ETHUSD_time_blackout", eth_tod, "expected (False, '...exempt...')"))

# 5. brain_explicitly_agrees exists + callable
try:
    agreed, reason = safeguards.brain_explicitly_agrees("BTCUSD", "BUY")
    results["checks"].append(("brain_explicitly_agrees_BTCUSD_BUY", (agreed, reason)))
except AttributeError:
    results["errors"].append("brain_explicitly_agrees NOT defined")
except Exception as e:
    results["errors"].append(f"brain_explicitly_agrees call: {e}")

# 6. brain_explicitly_agrees vs brain_agrees_with_signal
try:
    blocked, reason1 = safeguards.brain_agrees_with_signal("BTCUSD", "BUY")
    agreed, reason2 = safeguards.brain_explicitly_agrees("BTCUSD", "BUY")
    results["checks"].append(("compare_brain_perms", {
        "brain_agrees_with_signal_blocked": blocked,
        "brain_agrees_with_signal_reason": reason1,
        "brain_explicitly_agrees_agreed": agreed,
        "brain_explicitly_agrees_reason": reason2,
    }))
except Exception as e:
    results["errors"].append(f"compare_brain_perms: {e}")

# 7. Check brain_state.json has BTC view
brain_state_path = ROOT / "logs" / "brain_state.json"
if brain_state_path.exists():
    try:
        bs = json.loads(brain_state_path.read_text(encoding="utf-8"))
        last_sig_map = bs.get("last_signal_per_symbol", {})
        btc_view = last_sig_map.get("BTCUSD")
        eth_view = last_sig_map.get("ETHUSD")
        results["checks"].append(("brain_state_btc_view", btc_view))
        results["checks"].append(("brain_state_eth_view", eth_view))
    except Exception as e:
        results["errors"].append(f"brain_state read: {e}")
else:
    results["errors"].append(f"brain_state.json not found at {brain_state_path}")

Path("outputs/verify_results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
print(f"checks={len(results['checks'])} errors={len(results['errors'])}")
for e in results["errors"]:
    print(f"  ERR: {e}")
