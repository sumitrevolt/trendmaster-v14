"""
2026-05-14 — Audit why crypto signals were missed on the last weekend.

Check ALL these sources in one shot:
 1. logs/python_executor.log — every BTCUSD/ETHUSD line in last 7 days
 2. logs/trend_master_brain.out — every BTC/ETH signal/decision
 3. logs/brain_state.json — last_signal_per_symbol for BTC/ETH
 4. logs/brain_memory.json — trade_history filtered to crypto
 5. MT5 history_deals — actual closed deals for BTC/ETH over last 7 days
 6. tv_webhook_receiver.log — did TV alerts even arrive for crypto?

Writes report to outputs/crypto_audit_report.json
"""
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOGS = ROOT / "logs"
OUT = Path(__file__).parent / "crypto_audit_report.json"
NOW = datetime.now()
SEVEN_DAYS_AGO = NOW - timedelta(days=7)

report = {
    "audit_ts": NOW.isoformat(timespec="seconds"),
    "window_start": SEVEN_DAYS_AGO.isoformat(timespec="seconds"),
    "errors": [],
}

# ---- 1. executor log: crypto lines in window ----
exec_log = LOGS / "python_executor.log"
crypto_exec_lines = []
if exec_log.exists():
    try:
        with open(exec_log, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if "BTCUSD" in line or "ETHUSD" in line:
                    # Parse leading timestamp
                    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                    if m:
                        try:
                            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                            if ts >= SEVEN_DAYS_AGO:
                                crypto_exec_lines.append(line.strip())
                        except ValueError:
                            pass
    except Exception as e:
        report["errors"].append(f"exec_log read: {e}")

report["executor_log_count"] = len(crypto_exec_lines)
report["executor_log_sample"] = crypto_exec_lines[-50:]  # last 50

# Tally by reason
exec_tally = {}
for ln in crypto_exec_lines:
    for kw in ["stale", "SAFEGUARD BLOCK", "tv_strategy=", "skip ", "place_order",
              "BUY", "SELL", "filling_mode", "deal_id", "BRAIN VETO", "no_file",
              "filtered", "archived"]:
        if kw in ln:
            exec_tally[kw] = exec_tally.get(kw, 0) + 1
report["executor_keyword_tally"] = exec_tally

# ---- 2. brain log (if exists) ----
brain_logs = []
for candidate in [LOGS / "trend_master_brain.out", LOGS / "brain.out"]:
    if candidate.exists():
        try:
            with open(candidate, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "BTCUSD" in line or "ETHUSD" in line:
                        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                        if m:
                            try:
                                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                                if ts >= SEVEN_DAYS_AGO:
                                    brain_logs.append(line.strip())
                            except ValueError:
                                pass
            report[f"brain_log_path"] = str(candidate)
            break
        except Exception as e:
            report["errors"].append(f"brain log read {candidate.name}: {e}")
report["brain_log_count"] = len(brain_logs)
report["brain_log_sample"] = brain_logs[-30:]

# ---- 3. brain_state.json ----
bs_path = LOGS / "brain_state.json"
if bs_path.exists():
    try:
        bs = json.loads(bs_path.read_text(encoding="utf-8"))
        report["brain_state"] = {
            "halted": bs.get("halted"),
            "trading_paused": bs.get("trading_paused"),
            "drawdown_lockout_until": bs.get("drawdown_lockout_until"),
            "start_of_day_equity": bs.get("start_of_day_equity"),
            "last_btc_signal": bs.get("last_signal_per_symbol", {}).get("BTCUSD"),
            "last_eth_signal": bs.get("last_signal_per_symbol", {}).get("ETHUSD"),
        }
        # recent_results — crypto only
        rr = bs.get("recent_results", [])
        crypto_results = [r for r in rr if r.get("symbol") in ("BTCUSD", "ETHUSD")]
        report["brain_state_recent_crypto"] = crypto_results[-20:]
    except Exception as e:
        report["errors"].append(f"brain_state parse: {e}")

# ---- 4. brain_memory.json trade_history (crypto only, recent) ----
bm_path = LOGS / "brain_memory.json"
if bm_path.exists():
    try:
        bm = json.loads(bm_path.read_text(encoding="utf-8"))
        th = bm.get("trade_history", [])
        crypto_trades = []
        for t in th:
            if t.get("symbol") in ("BTCUSD", "ETHUSD"):
                ts_val = t.get("ts") or t.get("time") or t.get("open_time")
                try:
                    if isinstance(ts_val, (int, float)):
                        dt = datetime.fromtimestamp(ts_val)
                    else:
                        dt = datetime.fromisoformat(str(ts_val).replace("Z", "+00:00"))
                    if dt >= SEVEN_DAYS_AGO:
                        crypto_trades.append({
                            "ts": dt.isoformat(timespec="seconds"),
                            "symbol": t.get("symbol"),
                            "dir": t.get("dir") or t.get("direction"),
                            "pnl": t.get("pnl") or t.get("profit"),
                        })
                except (ValueError, TypeError):
                    continue
        report["brain_memory_crypto_recent"] = crypto_trades
    except Exception as e:
        report["errors"].append(f"brain_memory parse: {e}")

# ---- 5. MT5 history_deals for crypto over 7 days ----
try:
    import MetaTrader5 as mt5  # type: ignore
    if mt5.initialize():
        from_ts = int(SEVEN_DAYS_AGO.timestamp())
        to_ts = int(time.time())
        deals = mt5.history_deals_get(from_ts, to_ts) or []
        crypto_deals = []
        for d in deals:
            if d.symbol in ("BTCUSD", "ETHUSD"):
                crypto_deals.append({
                    "ts": datetime.fromtimestamp(d.time).isoformat(timespec="seconds"),
                    "symbol": d.symbol,
                    "type": "BUY" if d.type == 0 else "SELL" if d.type == 1 else f"type_{d.type}",
                    "entry": "IN" if d.entry == 0 else "OUT" if d.entry == 1 else f"e_{d.entry}",
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "comment": d.comment,
                })
        report["mt5_crypto_deals_count"] = len(crypto_deals)
        report["mt5_crypto_deals"] = crypto_deals
        mt5.shutdown()
    else:
        report["errors"].append(f"mt5 init failed: {mt5.last_error()}")
except Exception as e:
    report["errors"].append(f"mt5 deals query: {e}")

# ---- 6. TV webhook receiver log for crypto alerts ----
for candidate in [LOGS / "tv_webhook_receiver.out", LOGS / "tv_webhook_receiver.log",
                  LOGS / "tv_webhook.log", LOGS / "tv_webhook.out"]:
    if candidate.exists():
        try:
            tv_lines = []
            with open(candidate, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "BTCUSD" in line or "ETHUSD" in line:
                        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                        if m:
                            try:
                                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                                if ts >= SEVEN_DAYS_AGO:
                                    tv_lines.append(line.strip())
                            except ValueError:
                                pass
            report["tv_webhook_log_path"] = str(candidate)
            report["tv_webhook_crypto_count"] = len(tv_lines)
            report["tv_webhook_crypto_sample"] = tv_lines[-30:]
            break
        except Exception as e:
            report["errors"].append(f"tv webhook read {candidate.name}: {e}")

# Save
OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
print(f"audit done. executor_lines={report['executor_log_count']} mt5_crypto_deals={report.get('mt5_crypto_deals_count','?')} tv_crypto_alerts={report.get('tv_webhook_crypto_count','?')}")
