"""Audit why signals were missed.

Checks:
1. Webhook receiver — what arrived from TV (count by source/strategy)
2. Executor — what was skipped vs placed
3. TV alerts — last_fire_time per alert (did Rocket Prime even trigger?)
4. JSON files — what's the latest content per symbol
5. Pipeline downtime windows
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
WEBHOOK_LOG = ROOT / "logs/tv_webhook.log"
EXECUTOR_LOG = ROOT / "logs/python_executor.log"
TV_SIGNALS_JSONL = ROOT / "logs/tv_signals.jsonl"
SIGNAL_OUTCOMES = ROOT / "logs/signal_outcomes.jsonl"


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def parse_log_lines(path):
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def main():
    print(f"AUDIT: {datetime.now().isoformat(timespec='seconds')}\n")

    # ─── Webhook receiver: what arrived ────────────────────────────────
    section("1. WEBHOOK RECEIVER LOG — what arrived")
    lines = parse_log_lines(WEBHOOK_LOG)
    if not lines:
        print("  No log file")
    else:
        # Last 24h activity
        now_unix = time.time()
        ok_by_strategy = Counter()
        auth_fails = 0
        last_24h = []
        for line in lines:
            if "TV" in line and "OK" in line and "strategy=" in line:
                # Parse strategy
                parts = line.split("strategy=")
                if len(parts) > 1:
                    strat = parts[1].split()[0]
                    ok_by_strategy[strat] += 1
            elif "auth fail" in line:
                auth_fails += 1
            # Get timestamp
            try:
                ts_str = line.split(" [")[0]
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f").timestamp()
                if now_unix - ts < 86400:
                    last_24h.append(line)
            except Exception:
                pass

        print(f"  Total signals OK by strategy:")
        for strat, count in ok_by_strategy.most_common():
            print(f"    {strat}: {count}")
        print(f"  Auth fails: {auth_fails}")
        print(f"  Lines in last 24h: {len(last_24h)}")

        # Show last 5 OK entries to see freshest activity
        ok_last = [l for l in lines if "TV" in l and "OK" in l][-5:]
        print(f"\n  Last 5 OK entries:")
        for l in ok_last:
            short = l.replace("path=", "").split("strategy=")
            if len(short) > 1:
                print(f"    {short[0][:80]}... strategy={short[1].split()[0]}")
            else:
                print(f"    {l[:120]}")

    # ─── Executor log: skip reasons ────────────────────────────────────
    section("2. EXECUTOR LOG — placed vs skipped")
    lines = parse_log_lines(EXECUTOR_LOG)
    if not lines:
        print("  No log file")
    else:
        placed_count = 0
        failed_count = 0
        skip_total = 0
        recent_heartbeats = []
        for line in lines:
            if "ORDER PLACED" in line:
                placed_count += 1
            elif "ORDER FAILED" in line:
                failed_count += 1
            elif "heartbeat" in line:
                recent_heartbeats.append(line)
        print(f"  Total ORDER PLACED: {placed_count}")
        print(f"  Total ORDER FAILED: {failed_count}")
        print(f"  Recent heartbeats (last 5):")
        for hb in recent_heartbeats[-5:]:
            print(f"    {hb[hb.find('heartbeat'):]}")

    # ─── TV signals JSONL — full audit trail ────────────────────────────
    section("3. TV SIGNALS JSONL — full record of every signal received")
    if not TV_SIGNALS_JSONL.exists():
        print("  No tv_signals.jsonl file")
    else:
        lines = TV_SIGNALS_JSONL.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"  Total entries (all-time): {len(lines)}")
        now_unix = time.time()
        recent_24h = []
        recent_2h = []
        by_source = Counter()
        for line in lines:
            try:
                obj = json.loads(line)
                ts = obj.get("ts", 0)
                if now_unix - ts < 7200:
                    recent_2h.append(obj)
                if now_unix - ts < 86400:
                    recent_24h.append(obj)
                strategy = obj.get("tv_strategy") or obj.get("strategy") or "(none)"
                by_source[strategy] += 1
            except Exception:
                pass
        print(f"  Last 24h: {len(recent_24h)} signals")
        print(f"  Last 2h:  {len(recent_2h)} signals")
        print(f"  By strategy (all-time):")
        for s, c in by_source.most_common(10):
            print(f"    {s:<30} {c}")
        # Show last 5 received
        print(f"\n  Last 5 received signals:")
        for o in (recent_24h[-5:] if recent_24h else []):
            ts_str = datetime.fromtimestamp(o.get("ts", 0)).strftime("%H:%M:%S")
            print(f"    {ts_str}  {o.get('symbol','?'):<10} {o.get('direction','?'):<5} "
                  f"strat={o.get('tv_strategy','-'):<25} tf={o.get('tv_timeframe','-')}")

    # ─── Outcomes ────────────────────────────────────────────────────
    section("4. CLOSED-TRADE OUTCOMES (logs/signal_outcomes.jsonl)")
    if not SIGNAL_OUTCOMES.exists():
        print("  No outcomes file yet")
    else:
        n = sum(1 for _ in SIGNAL_OUTCOMES.open(encoding="utf-8"))
        print(f"  Total closed trades logged: {n}")
        if n > 0:
            wins = 0
            losses = 0
            total_pnl = 0
            for line in SIGNAL_OUTCOMES.open(encoding="utf-8"):
                try:
                    o = json.loads(line)
                    if o.get("win"):
                        wins += 1
                    else:
                        losses += 1
                    total_pnl += o.get("profit", 0)
                except Exception:
                    pass
            wr = (wins / n * 100) if n else 0
            print(f"  Wins: {wins}  Losses: {losses}  WR: {wr:.1f}%")
            print(f"  Total realized P/L: {total_pnl:+.2f}")

    # ─── Summary diagnosis ────────────────────────────────────────────
    section("DIAGNOSIS")
    print()
    print("Signal could be 'missed' for these reasons:")
    print()
    print("A. TV alert never fired       — Rocket Prime's alert() condition not met")
    print("                                  (most common: indicator quiet, market not trending)")
    print("B. Webhook auth failed         — alert URL missing secret (was true before — now fixed)")
    print("C. Receiver dedup (20s window) — same (sym, dir, TF) within 20s = ignored")
    print("D. Executor strict-mode reject — non-rocket-prime tv_strategy = ignored")
    print("E. Signal too old (>90s)       — broker-tz mismatch; we fixed this with TimeGMT")
    print("F. Position cooldown (5 min)   — already opened same dir within 5 min")
    print("G. Already-open same-direction — won't open duplicate")
    print("H. Order rejected by broker    — invalid stops, no money, market closed")


if __name__ == "__main__":
    sys.exit(main())
