"""
Fallback: use yfinance to pull spot-BTC ETF AUM/volume as proxy for net flows.
The 11 spot ETFs launched 11 Jan 2024.
Net flow ~ sum(create/redeem) ~ shares_outstanding_change * NAV.
yfinance gives us OHLCV for each ticker, so we can use volume*close as proxy.
But better: fetch from Bitbo or coinglass which expose JSON.
"""
import yfinance as yf, pandas as pd, os, json
import requests, time

OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"

# US spot BTC ETFs (post Jan 2024)
ETF_TICKERS = ["IBIT","FBTC","ARKB","BITB","BTCO","EZBC","BRRR","HODL","BTCW","DEFI","GBTC"]
print("Trying yfinance ETF data...")
all_etf = {}
for t in ETF_TICKERS:
    try:
        df = yf.download(t, start="2024-01-01", end="2026-04-26", progress=False, auto_adjust=False, threads=False)
        if df is None or df.empty:
            print(f"  {t}: empty"); continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df["date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        # Volume * close = $-volume (rough proxy for flows; not net flow)
        df["dollar_volume"] = df["Close"] * df["Volume"]
        all_etf[t] = df[["date","Close","Volume","dollar_volume"]].rename(columns={"Close":"close","Volume":"shares_volume"})
        print(f"  {t}: {len(df)} rows {df['date'].min().date()}→{df['date'].max().date()}")
        time.sleep(0.3)
    except Exception as e:
        print(f"  {t}: {e}")

# Save per-ETF
for t, df in all_etf.items():
    df.to_csv(os.path.join(OUT, f"etf_{t}.csv"), index=False)

# Note: dollar volume != net flow. For net flow we need shares_outstanding deltas.
# Try sosovalue API as backup.

# SoSoValue has a public web API
print("\nTrying alternate Bitcoin ETF flow API...")
candidates = [
    "https://sosovalue.com/api/v1/etf/historicalInflowChart/us-btc-spot",
    "https://www.coinglass.com/api/etf/index/historicalDataChart/btc",
    "https://www.theblock.co/api/charts/chart/crypto-markets/spot-bitcoin-etfs/aggregated-inflows-of-spot-bitcoin-etfs",
]
for url in candidates:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0", "Accept":"application/json"})
        print(f"  {url}: {r.status_code} {len(r.text)}b ct={r.headers.get('content-type','')}")
        if r.status_code == 200 and r.headers.get("content-type","").startswith("application/json"):
            with open("/tmp/etf_flow_alt.json","w") as f: f.write(r.text)
            print("    saved /tmp/etf_flow_alt.json")
    except Exception as e:
        print(f"  {url}: {e}")
    time.sleep(1)

print("DONE")
