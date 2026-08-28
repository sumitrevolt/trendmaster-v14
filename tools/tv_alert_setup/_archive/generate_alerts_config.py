"""Generate alerts_config.json for the Playwright TV alert setup script.

Reads:
  - ai_trading_agents/team_params.SYMBOL_TO_TEAM   (the 19-symbol whitelist)
  - config/.env                                     (TV_WEBHOOK_SECRET, TV_PUBLIC_URL)

Emits:
  - tools/tv_alert_setup/alerts_config.json

Each entry:
  {
    "id": "XAUUSD_M5_BUY",
    "symbol": "XAUUSD",
    "timeframe": "M5",
    "tv_interval": "5",            # what TradingView's interval field expects
    "direction": "BUY",
    "name": "TrendMaster XAUUSD M5 BUY",
    "webhook_url": "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal",
    "message_body": '{"secret":"...","symbol":"XAUUSD","direction":"buy",...}'
  }

Usage:
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\generate_alerts_config.py [--timeframes M5,M15,H1,H4] [--directions BUY,SELL]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# Map MetaTrader-style TF names → TradingView's `{{interval}}` value
TF_TO_TV_INTERVAL = {
    "M1": "1",   "M5": "5",   "M15": "15", "M30": "30",
    "H1": "60",  "H2": "120", "H4": "240",
    "D1": "D",   "W1": "W",
}
# Map MT-style TF → TradingView's chart-side display label (used for clicking)
TF_TO_TV_LABEL = {
    "M1": "1 minute", "M5": "5 minutes", "M15": "15 minutes", "M30": "30 minutes",
    "H1": "1 hour", "H2": "2 hours", "H4": "4 hours",
    "D1": "1 day", "W1": "1 week",
}


def _load_env() -> dict:
    env = {}
    env_path = ROOT / "config" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _load_symbols() -> list[str]:
    try:
        from ai_trading_agents.team_params import SYMBOL_TO_TEAM
    except Exception as e:
        print(f"FATAL: cannot import SYMBOL_TO_TEAM: {e}")
        sys.exit(1)
    # First 19 = canonical TrendMaster set; ignore extra crosses added for TV
    canonical = [
        "XAUUSD", "XAGUSD",
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
        "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY",
        "CADJPY", "EURGBP",
        "BTCUSD", "ETHUSD",
        "XTIUSD", "XBRUSD", "XNGUSD",
    ]
    return [s for s in canonical if s in SYMBOL_TO_TEAM]


def _broker_exchange(symbol: str) -> str:
    """OctaFX-Demo broker maps these symbols. TradingView lookups go via OCTAFX:
    or the user's preferred exchange (e.g. OANDA: for forex). Defaults to OANDA
    for FX/metals which is the most universally available; CRYPTO uses BINANCE."""
    if symbol in {"BTCUSD", "ETHUSD"}:
        return "BINANCE"
    if symbol in {"XTIUSD", "XBRUSD", "XNGUSD"}:
        # Energy commodities — OANDA carries these as USOIL/UKOIL/NATGASUSD
        return "TVC"  # TradingView's own data feed; user can change if needed
    return "OANDA"


def _broker_symbol(symbol: str) -> str:
    """Convert TrendMaster symbol → exchange-specific ticker."""
    overrides = {
        "XTIUSD": "USOIL",   # WTI
        "XBRUSD": "UKOIL",   # Brent
        "XNGUSD": "NATGASUSD",
    }
    return overrides.get(symbol, symbol)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", default="M5,M15,H1,H4",
                    help="Comma-separated TFs (default: M5,M15,H1,H4)")
    ap.add_argument("--directions", default="BUY,SELL",
                    help="Comma-separated directions (default: BUY,SELL — for indicators "
                         "that don't have {{strategy.order.action}}, you need both alerts)")
    ap.add_argument("--strategy-mode", action="store_true",
                    help="If set, emits ONE alert per (symbol,TF) using {{strategy.order.action}} "
                         "for direction (works only with TV strategy scripts, not plain indicators).")
    ap.add_argument("--out", default=None, help="Output path (default: alerts_config.json next to script)")
    args = ap.parse_args()

    env = _load_env()
    secret = env.get("TV_WEBHOOK_SECRET", "").strip()
    public_url = env.get("TV_PUBLIC_URL", "").strip().rstrip("/")
    if not secret:
        print("FATAL: TV_WEBHOOK_SECRET missing in config/.env"); return 1
    if not public_url:
        print("FATAL: TV_PUBLIC_URL missing in config/.env"); return 1
    webhook_url = f"{public_url}/tv-signal"

    symbols = _load_symbols()
    timeframes = [tf.strip().upper() for tf in args.timeframes.split(",") if tf.strip()]
    for tf in timeframes:
        if tf not in TF_TO_TV_INTERVAL:
            print(f"FATAL: unknown timeframe {tf}; supported: {list(TF_TO_TV_INTERVAL.keys())}")
            return 1
    directions = [d.strip().upper() for d in args.directions.split(",") if d.strip()]

    alerts = []
    for sym in symbols:
        ex = _broker_exchange(sym)
        broker_sym = _broker_symbol(sym)
        for tf in timeframes:
            if args.strategy_mode:
                body = json.dumps({
                    "secret": secret,
                    "symbol": sym,
                    "direction": "{{strategy.order.action}}",
                    "price": "{{close}}",
                    "tv_strategy": "{{strategy.order.comment}}",
                    "tv_alert_ts": "{{timenow}}",
                    "tv_timeframe": "{{interval}}",
                }, separators=(",", ":")).replace('"{{', '{{').replace('}}"', '}}')
                alerts.append({
                    "id": f"{sym}_{tf}_AUTO",
                    "symbol": sym, "exchange": ex, "broker_symbol": broker_sym,
                    "timeframe": tf, "tv_interval": TF_TO_TV_INTERVAL[tf],
                    "tv_timeframe_label": TF_TO_TV_LABEL[tf],
                    "direction": "AUTO",
                    "name": f"TrendMaster {sym} {tf}",
                    "webhook_url": webhook_url,
                    "message_body": body,
                })
            else:
                for direction in directions:
                    body = json.dumps({
                        "secret": secret,
                        "symbol": sym,
                        "direction": direction.lower(),
                        "price": "{{close}}",
                        "tv_strategy": "{{plot_0}}",   # generic; user can change per indicator
                        "tv_alert_ts": "{{timenow}}",
                        "tv_timeframe": "{{interval}}",
                    }, separators=(",", ":")).replace('"{{', '{{').replace('}}"', '}}')
                    alerts.append({
                        "id": f"{sym}_{tf}_{direction}",
                        "symbol": sym, "exchange": ex, "broker_symbol": broker_sym,
                        "timeframe": tf, "tv_interval": TF_TO_TV_INTERVAL[tf],
                        "tv_timeframe_label": TF_TO_TV_LABEL[tf],
                        "direction": direction,
                        "name": f"TrendMaster {sym} {tf} {direction}",
                        "webhook_url": webhook_url,
                        "message_body": body,
                    })

    out_path = Path(args.out) if args.out else Path(__file__).resolve().parent / "alerts_config.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(alerts, indent=2), encoding="utf-8")
    print(f"[OK] Wrote {len(alerts)} alert specs -> {out_path}")
    print(f"     Webhook URL : {webhook_url}")
    print(f"     Symbols     : {len(symbols)} ({', '.join(symbols[:5])}...)")
    print(f"     Timeframes  : {timeframes}")
    print(f"     Directions  : {directions if not args.strategy_mode else ['AUTO (strategy mode)']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
