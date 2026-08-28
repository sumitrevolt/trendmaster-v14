import yfinance as yf
import pandas as pd
import numpy as np
import os, json

OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"
os.makedirs(OUT, exist_ok=True)

yf_map = {
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "XTIUSD": "CL=F",
    "XBRUSD": "BZ=F",
    "XNGUSD": "NG=F",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
}

results = {}
for symbol, ticker in yf_map.items():
    try:
        df = yf.download(ticker, start="2010-01-01", end="2026-04-26", progress=False, auto_adjust=False, threads=False)
        if df is None or df.empty:
            print(f"FAIL {symbol} ({ticker}): empty")
            continue
        # Multiindex columns -> flatten
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        # standard column
        if "Adj Close" in df.columns:
            df = df.rename(columns={"Adj Close": "adj_close"})
        df = df.rename(columns={"Close": "close", "Date": "date", "Open": "open", "High": "high", "Low": "low", "Volume": "volume"})
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df[["date", "close"]].dropna()
        out = os.path.join(OUT, f"price_{symbol}.csv")
        df.to_csv(out, index=False)
        results[symbol] = {"n_rows": int(len(df)), "start": str(df["date"].min().date()), "end": str(df["date"].max().date())}
        print(f"OK {symbol} ({ticker}): {len(df)} rows {df['date'].min().date()} → {df['date'].max().date()}")
    except Exception as e:
        print(f"FAIL {symbol} ({ticker}): {e}")
        results[symbol] = {"error": str(e)}

with open(os.path.join(OUT, "_price_fetch_summary.json"), "w") as f:
    json.dump(results, f, indent=2)

print("DONE")
