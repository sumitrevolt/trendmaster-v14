"""Farside BTC ETF flow scrape — all-data table."""
import requests, pandas as pd, os, json
from io import StringIO

OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"
HEADERS = {"User-Agent": "Mozilla/5.0 (TrendMaster-research/1.0)",
           "Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"}

URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
r = requests.get(URL, headers=HEADERS, timeout=30)
print("HTTP:", r.status_code, "bytes:", len(r.text))
if r.status_code != 200:
    print("FAIL:", r.text[:500])
    raise SystemExit(1)

# Parse all tables
tables = pd.read_html(StringIO(r.text))
print("tables:", len(tables))
for i,t in enumerate(tables):
    print(f"  [{i}] shape={t.shape} cols={list(t.columns)[:6]}")

# Pick the largest table
best = max(tables, key=lambda t: t.shape[0]*t.shape[1])
print("Picked shape", best.shape)
# Save raw
best.to_csv(os.path.join(OUT, "farside_raw.csv"), index=False)

# Parse it: usually first column is Date, then issuer columns including Total and "IBIT"
# Some rows are footers ("Total","Sums","Average"...) — drop non-date.
df = best.copy()
# Flatten possible multiindex
if isinstance(df.columns, pd.MultiIndex):
    df.columns = [' '.join([str(c) for c in tup if c and 'Unnamed' not in str(c)]).strip() for tup in df.columns]
print("flattened columns:", list(df.columns))

# Heuristic: find date column
date_col = df.columns[0]
df[date_col] = df[date_col].astype(str)
# Keep rows where date_col looks like a date (e.g. 11 Jan 2024)
import re
date_pat = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$")
mask = df[date_col].str.match(date_pat)
print("date-match rows:", mask.sum(), "of", len(df))
df = df[mask].copy()
df["date"] = pd.to_datetime(df[date_col], format="%d %b %Y", errors="coerce")
df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

# Convert numeric columns
def to_num(x):
    if pd.isna(x): return None
    s = str(x).replace(",","").replace("(","-").replace(")","").strip()
    if s in ("-","","–"): return 0.0
    try: return float(s)
    except: return None

for c in df.columns:
    if c in (date_col, "date"): continue
    df[c] = df[c].map(to_num)

# Save cleaned
out = os.path.join(OUT, "farside_btc_etf.csv")
df.to_csv(out, index=False)
print("saved", out, "rows", len(df), "range", df["date"].min().date(), df["date"].max().date())
print("columns:", list(df.columns))
