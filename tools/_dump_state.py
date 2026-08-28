import json, sys
from datetime import datetime, timezone

s = json.load(open('logs/brain_state.json'))
print("=== brain_state.json snapshot ===")
print(f"recent_results count: {len(s.get('recent_results', []))}")
print(f"recent_results: {json.dumps(s.get('recent_results', []), indent=2)[:1200]}")
print()
print(f"last_signal_direction: {s.get('last_signal_direction')}")
print()
print(f"last_processed_deal_ts: {s.get('last_processed_deal_ts')}")
ts = s.get('last_processed_deal_ts', 0)
if ts:
    print(f"  -> {datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()}")
print(f"daily_pnl_close: {s.get('daily_pnl_close')}")
print(f"start_of_day_equity: {s.get('start_of_day_equity')}")
print(f"daily_drawdown_peak_eq: {s.get('daily_drawdown_peak_eq')}")
print(f"trading_paused: {s.get('trading_paused')}")
