"""
FedWatch implied probabilities require pyfedwatch (downloads CME ZQ contract data) OR Fed funds futures from yfinance.
The CME widget JSON requires a specific session token that's not stable.
Try the pyfedwatch open-source library OR construct from ZQ Fed Funds futures via yfinance.

Pragmatic approach:
- ZQ futures (30-day Fed Funds) are tradable and give us implied avg rate for the contract month.
- Implied rate = 100 - ZQ_price (in %)
- Implied prob of cut (vs current target rate) = how far below current the implied rate is.

For Phase A2, we'll use:
- ZQ=F front month yfinance => implied avg rate
- Compare to current Fed Funds upper-bound from FRED DFEDTARU
- Spread = implied - current = signal of expected cut/hike
- Probability(cut) ≈ map spread to a [0,1] using -25bp = full cut.
"""
import yfinance as yf, pandas as pd, os, json, requests
from io import StringIO

OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"

# Yahoo doesn't carry continuous ZQ. Try alternatives:
# - "ZQ=F" = 30-day Fed Funds — should exist on Yahoo.
df = yf.download("ZQ=F", start="2010-01-01", end="2026-04-26", progress=False, auto_adjust=False, threads=False)
print("ZQ=F:", None if df is None else df.shape)
if df is not None and not df.empty:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    df["implied_rate_pct"] = 100 - df["Close"]
    df = df[["date","Close","implied_rate_pct"]].dropna()
    df.to_csv(os.path.join(OUT, "fedfunds_zq_front.csv"), index=False)
    print(f"saved fedfunds_zq_front: {len(df)} rows {df['date'].min().date()}→{df['date'].max().date()}")
    print(df.tail())
else:
    print("ZQ=F empty - trying alternate symbol")

# FRED for current Fed funds upper bound (DFEDTARU)
import requests
r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU", timeout=20,
                 headers={"User-Agent":"Mozilla/5.0"})
print("FRED DFEDTARU:", r.status_code, len(r.text))
if r.status_code == 200:
    fred = pd.read_csv(StringIO(r.text))
    fred.columns = ["date","fed_target_upper"]
    fred["date"] = pd.to_datetime(fred["date"], errors="coerce")
    fred["fed_target_upper"] = pd.to_numeric(fred["fed_target_upper"], errors="coerce")
    fred = fred.dropna()
    fred.to_csv(os.path.join(OUT, "fred_fed_target_upper.csv"), index=False)
    print(f"saved fred_fed_target: {len(fred)} rows {fred['date'].min().date()}→{fred['date'].max().date()}")
