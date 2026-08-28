"""
For BTC ETFs: shares-outstanding delta * NAV ≈ net flow.
yfinance Ticker has .info or .history for some metrics, but not shares-outstanding daily.
Use this fallback: dollar_volume itself correlates ~0.6+ with absolute net flow.
Build aggregate ETF dollar-volume signal.
"""
import pandas as pd, os, glob, numpy as np

OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"
files = sorted(glob.glob(os.path.join(OUT, "etf_*.csv")))
print("ETF files:", [os.path.basename(f) for f in files])

frames = []
for f in files:
    sym = os.path.basename(f).replace("etf_","").replace(".csv","")
    df = pd.read_csv(f, parse_dates=["date"])
    df["ticker"] = sym
    frames.append(df)
all_df = pd.concat(frames)
piv_dv = all_df.pivot_table(index="date", columns="ticker", values="dollar_volume", aggfunc="sum")
piv_close = all_df.pivot_table(index="date", columns="ticker", values="close", aggfunc="last")
# Total $-volume across all spot ETFs (excluding GBTC pre-conversion outflow noise — but include for total)
piv_dv["total_dv"] = piv_dv.sum(axis=1)

# IBIT alone
piv_dv_ibit = piv_dv[["IBIT","total_dv"]].copy() if "IBIT" in piv_dv.columns else piv_dv.copy()
piv_dv_ibit.to_csv(os.path.join(OUT, "etf_dollar_volume.csv"))
print("saved etf_dollar_volume.csv")
print(piv_dv_ibit.tail())

# A better proxy: net change in dollar volume = signed buy-sell pressure
# For IBIT specifically: use price * volume * sign(price-prev_close) as crude flow proxy.
# But Yahoo doesn't tell us buy vs sell side.
# SO: We use TOTAL DOLLAR VOLUME as a magnitude signal (volatility of attention),
# and the IBIT-close-vs-NAV premium would be the truer flow signal — not available here.
# We'll proceed with ETF dollar-volume as the best obtainable Phase A2 proxy and note this caveat heavily.

# A second proxy: average daily NAV change of ETFs vs spot BTC = a flow indicator
# (when ETFs trade premium, creations dominate)
