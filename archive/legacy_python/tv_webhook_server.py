"""
=============================================================
  TradingView → MT5 Webhook Bot
  VERSION 1.0

  Flow:
  TradingView Alert (webhook) → This server → MT5 Trade

  Setup:
  1. pip install flask MetaTrader5 requests
  2. Run this file
  3. Use ngrok to get public URL
  4. Paste URL in TradingView alert webhook field
=============================================================
"""

from flask import Flask, request, jsonify
import MetaTrader5 as mt5
import json
import logging
import os
from datetime import datetime
from mt5_trader import MT5Trader

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('webhook_log.txt', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────
PORT        = 5000          # webhook server port
SECRET_KEY  = "xauusd2024"  # must match TradingView alert message

# ── Risk settings ────────────────────────────────────────────────────
RISK_CONFIG = {
    "account_balance_pct": 1.0,   # risk 1% of balance per trade
    "max_open_trades":     3,      # max simultaneous open trades
    "default_symbol":      "XAUUSD",
    "default_timeframe":   "M5",
    "sl_pips":             15,     # Stop Loss in pips (Gold: 1 pip = $0.10)
    "tp_pips":             30,     # Take Profit (2:1 RR)
    "lot_size":            0.01,   # fixed lot (will be overridden by risk%)
}

app = Flask(__name__)
trader = None  # initialized on startup

# ── Webhook endpoint ─────────────────────────────────────────────────
@app.route('/webhook', methods=['POST'])
def webhook():
    global trader

    try:
        # Parse incoming JSON from TradingView
        data = request.get_json(force=True)
        if not data:
            # Try plain text
            raw = request.data.decode('utf-8')
            log.info(f"Raw data received: {raw}")
            try:
                data = json.loads(raw)
            except:
                data = {"raw": raw}

        log.info(f"Signal received: {data}")

        # ── Security check ───────────────────────────────────────────
        if data.get("key") != SECRET_KEY:
            log.warning("Invalid secret key — signal rejected")
            return jsonify({"status": "rejected", "reason": "invalid key"}), 401

        # ── Extract signal fields ────────────────────────────────────
        action  = str(data.get("action",  "")).upper()   # BUY or SELL
        symbol  = str(data.get("symbol",  RISK_CONFIG["default_symbol"])).upper()
        comment = str(data.get("comment", "TV Signal"))

        # Optional: price levels from alert
        sl_price = float(data.get("sl", 0))
        tp_price = float(data.get("tp", 0))

        if action not in ["BUY", "SELL"]:
            log.warning(f"Unknown action: {action}")
            return jsonify({"status": "ignored", "reason": f"unknown action: {action}"}), 200

        # ── Execute trade ────────────────────────────────────────────
        if trader is None or not trader.connected:
            trader = MT5Trader()
            if not trader.connect():
                log.error("MT5 connection failed")
                return jsonify({"status": "error", "reason": "MT5 not connected"}), 500

        result = trader.execute_trade(
            symbol   = symbol,
            action   = action,
            sl_price = sl_price,
            tp_price = tp_price,
            comment  = comment
        )

        log.info(f"Trade result: {result}")
        return jsonify(result), 200

    except Exception as e:
        log.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({"status": "error", "reason": str(e)}), 500


@app.route('/status', methods=['GET'])
def status():
    """Health check — open in browser to verify server is running"""
    global trader
    mt5_ok = trader is not None and trader.connected
    return jsonify({
        "status":       "running",
        "mt5_connected": mt5_ok,
        "time":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version":       "1.0"
    })


@app.route('/close_all', methods=['POST'])
def close_all():
    """Emergency close all trades"""
    global trader
    if trader and trader.connected:
        result = trader.close_all_trades()
        return jsonify(result)
    return jsonify({"status": "error", "reason": "not connected"})


# ── Startup ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  TradingView → MT5 Webhook Bot v1.0")
    print("=" * 60)
    print(f"  Port:       {PORT}")
    print(f"  Endpoint:   http://localhost:{PORT}/webhook")
    print(f"  Status:     http://localhost:{PORT}/status")
    print(f"  Secret key: {SECRET_KEY}")
    print("=" * 60)
    print()
    print("  STEP 1: Make sure MT5 is open and logged in")
    print("  STEP 2: Run ngrok:  ngrok http 5000")
    print("  STEP 3: Copy ngrok URL → paste in TradingView alert")
    print("  STEP 4: Add /webhook at end of URL")
    print()
    print("  Example TradingView webhook URL:")
    print("  https://abc123.ngrok.io/webhook")
    print()

    # Connect MT5 on startup
    trader = MT5Trader()
    if trader.connect():
        print("  ✅ MT5 connected successfully!")
        info = trader.get_account_info()
        if info:
            print(f"  Account: {info['login']} | Balance: ${info['balance']:.2f} | Leverage: 1:{info['leverage']}")
    else:
        print("  ⚠️  MT5 not connected — will retry on first signal")

    print()
    print("  Webhook server starting...")
    print("=" * 60)

    app.run(host='0.0.0.0', port=PORT, debug=False)
