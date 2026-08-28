"""Comprehensive BTC signal audit — what signals has the bot seen
in the last 24 hours, and what happened to each.

Sources audited:
  1. logs/tv_webhook.log         - TV webhook arrivals + parse + reject
  2. logs/tv_webhook_unparsed_bodies.log - raw TV bodies
  3. logs/trend_master_brain.out - brain ticks + profit_gate decisions
  4. logs/python_executor.log    - executor SAFEGUARD blocks + heartbeats
  5. logs/brain_state.json       - recent_results closed trades
  6. MT5 history_deals_get       - last 24h closed deals on BTCUSD
  7. MT5 positions_get           - current open BTCUSD positions

Goal: prove (or disprove) the operator's claim "BTC signal mila par
trade nahi hua" by showing every BTC-touching event in chronological
order with outcome.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"


def section(title: str) -> None:
    print()
    print("=" * 76)
    print(f"  {title}")
    print("=" * 76)


def lines_with(path: Path, needle: str, since_ts: float | None = None) -> list[tuple[str, str]]:
    """Return [(timestamp_str, line)] tuples from file containing needle."""
    if not path.exists():
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if needle.lower() not in line.lower():
                    continue
                m = re.search(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", line)
                ts_str = m.group(1).replace("T", " ") if m else ""
                if since_ts is not None and ts_str:
                    try:
                        line_ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").timestamp()
                        if line_ts < since_ts:
                            continue
                    except Exception:
                        pass
                out.append((ts_str, line.rstrip()))
    except Exception as e:
        out.append(("?", f"[error reading {path.name}: {e}]"))
    return out


def main() -> int:
    print(f"=== BTC signal audit ({datetime.now()}) ===")
    print(f"Last 24h scan from {datetime.now() - timedelta(hours=24)}")

    since_24h = time.time() - 24 * 3600

    # 1. TV webhook arrivals
    section("[1/6] TV webhook BTC arrivals (logs/tv_webhook.log)")
    tv_lines = lines_with(LOGS / "tv_webhook.log", "BTCUSD", since_24h)
    if tv_lines:
        for ts, line in tv_lines[-20:]:
            print(f"  {line}")
    else:
        print("  (no BTC TV alerts in last 24h)")

    # 2. Raw unparsed bodies (gives a count of TV pings)
    section("[2/6] TV webhook BTC raw bodies (logs/tv_webhook_unparsed_bodies.log)")
    raw = lines_with(LOGS / "tv_webhook_unparsed_bodies.log", "sym='BTCUSD'", since_24h)
    print(f"  count: {len(raw)} BTC-targeted webhook hits in last 24h")
    if raw:
        for ts, line in raw[-5:]:
            print(f"  {line}")

    # 3. Brain BTC ticks
    section("[3/6] Brain BTCUSD profit_gate decisions (last 100 distinct messages)")
    brain_lines = lines_with(LOGS / "trend_master_brain.out", "BTCUSD", since_24h)
    distinct: dict[str, str] = {}
    for ts, line in brain_lines:
        # Strip timestamp + ATR float to dedupe similar veto messages
        key = re.sub(r"ATR \d+\.\d+", "ATR X", re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "", line))
        if key not in distinct:
            distinct[key] = f"{ts}: {line[line.find(']') + 2:][:200] if ']' in line else line[:200]}"
    for v in list(distinct.values())[:15]:
        print(f"  {v}")

    # 4. Executor BTC events
    section("[4/6] python_executor BTC events (heartbeats omitted)")
    exec_lines = lines_with(LOGS / "python_executor.log", "BTCUSD", since_24h)
    interesting = [(ts, line) for ts, line in exec_lines if "heartbeat" not in line.lower()]
    if interesting:
        for ts, line in interesting[-15:]:
            print(f"  {line}")
    else:
        print("  (no non-heartbeat BTC events)")

    # 5. brain_state recent_results
    section("[5/6] brain_state.json recent_results (BTCUSD only)")
    sf = LOGS / "brain_state.json"
    if sf.exists():
        st = json.loads(sf.read_text(encoding="utf-8"))
        rr = st.get("recent_results", [])
        btc_rr = [r for r in rr if isinstance(r, dict) and r.get("symbol") == "BTCUSD"]
        print(f"  total recent_results entries: {len(rr)}")
        print(f"  BTCUSD entries: {len(btc_rr)}")
        for r in btc_rr[-10:]:
            ts_h = datetime.fromtimestamp(r.get("ts", 0)).strftime("%Y-%m-%d %H:%M:%S")
            print(f"    {ts_h}  pnl=${r.get('pnl', 0):+.2f}  R={r.get('r_mult', 0):+.2f}  deal={r.get('deal_id')}")

    # 6. MT5 deals + positions
    section("[6/6] MT5 BTCUSD history (last 24h) + open positions")
    try:
        import MetaTrader5 as mt5  # type: ignore
        if not mt5.initialize():
            print(f"  MT5 initialize failed: {mt5.last_error()}")
        else:
            now = time.time()
            since = int(now - 24 * 3600)
            until = int(now + 60)
            deals = mt5.history_deals_get(since, until) or []
            btc_deals = [d for d in deals if getattr(d, "symbol", "") == "BTCUSD"]
            print(f"  BTCUSD deals in last 24h: {len(btc_deals)}")
            for d in btc_deals[-10:]:
                d_time = datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M:%S")
                print(f"    {d_time}  ticket={d.ticket}  type={d.type}  vol={d.volume}  profit={d.profit:+.2f}  comment={d.comment}")

            positions = mt5.positions_get(symbol="BTCUSD") or []
            print(f"  Currently open BTCUSD positions: {len(positions)}")
            for p in positions:
                p_time = datetime.fromtimestamp(p.time).strftime("%Y-%m-%d %H:%M:%S")
                age_min = int((now - p.time) / 60)
                print(f"    {p_time}  ticket={p.ticket}  type={'BUY' if p.type == 0 else 'SELL'}  vol={p.volume}  open={p.price_open}  pnl={p.profit:+.2f}  age={age_min}m")
            mt5.shutdown()
    except Exception as e:
        print(f"  MT5 error: {e}")

    section("Verdict")
    n_tv = len(raw) if raw else 0
    n_btc_results = 0
    if (LOGS / "brain_state.json").exists():
        st = json.loads((LOGS / "brain_state.json").read_text(encoding="utf-8"))
        n_btc_results = sum(1 for r in st.get("recent_results", [])
                           if isinstance(r, dict) and r.get("symbol") == "BTCUSD")
    print(f"  TV alerts in last 24h: {n_tv}")
    print(f"  BTC closed trades in recent_results: {n_btc_results}")
    print()
    if n_tv == 0:
        print("  No TV-source signals in last 24h — bot can't trade what didn't arrive")
    elif n_tv > 0 and n_btc_results == 0:
        print("  TV alerts arrived but ZERO trades — likely the no-direction bug")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
