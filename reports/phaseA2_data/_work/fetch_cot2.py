"""Re-fetch CL/BZ/6B/6N with full-history market names; concat with newer ones."""
import requests, pandas as pd, time, os, json
from urllib.parse import urlencode

OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"
HEADERS = {"User-Agent": "Mozilla/5.0 (TrendMaster-research/1.0)"}
session = requests.Session(); session.headers.update(HEADERS)

# code -> list of market names (older first)
MULTI = {
    "CL": ["CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE", "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE"],
    "BZ": ["CRUDE OIL, BRENT - NEW YORK MERCANTILE EXCHANGE", "BRENT CRUDE OIL LAST DAY - NEW YORK MERCANTILE EXCHANGE", "BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE"],
    "6B": ["BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE", "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"],
    "6N": ["NEW ZEALAND DOLLAR - CHICAGO MERCANTILE EXCHANGE", "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE"],
}

def fetch(market_name, since_year=2010):
    base = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    where = f"market_and_exchange_names='{market_name}' AND report_date_as_yyyy_mm_dd >= '{since_year}-01-01T00:00:00.000'"
    params = {"$where": where,
        "$select": "report_date_as_yyyy_mm_dd,market_and_exchange_names,noncomm_positions_long_all,noncomm_positions_short_all,comm_positions_long_all,comm_positions_short_all,open_interest_all",
        "$order": "report_date_as_yyyy_mm_dd ASC", "$limit": "50000"}
    r = session.get(base + "?" + urlencode(params), timeout=30)
    if r.status_code != 200: return None, f"HTTP {r.status_code}"
    data = r.json()
    if not data: return None, "empty"
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.tz_localize(None)
    for c in ["noncomm_positions_long_all","noncomm_positions_short_all","comm_positions_long_all","comm_positions_short_all","open_interest_all"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["spec_net"] = df["noncomm_positions_long_all"] - df["noncomm_positions_short_all"]
    df["comm_net"] = df["comm_positions_long_all"] - df["comm_positions_short_all"]
    return df.sort_values("date").reset_index(drop=True), None

results = {}
for code, markets in MULTI.items():
    frames = []
    for m in markets:
        df, err = fetch(m)
        if df is not None:
            frames.append(df)
            print(f"   {code} {m}: {len(df)} rows {df['date'].min().date()}→{df['date'].max().date()}")
        else:
            print(f"   {code} {m}: {err}")
        time.sleep(0.7)
    if frames:
        merged = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
        out = os.path.join(OUT, f"cot_{code}.csv")
        merged.to_csv(out, index=False)
        results[code] = {"n_rows": int(len(merged)), "start": str(merged["date"].min().date()), "end": str(merged["date"].max().date())}
        print(f"OK {code} merged: {len(merged)} rows")
    else:
        results[code] = {"error": "all variants empty"}

# Also add NG newer name (NG stopped 2022). Older: NATURAL GAS, newer: HENRY HUB
ng_frames = []
for m in ["NATURAL GAS - NEW YORK MERCANTILE EXCHANGE", "HENRY HUB - NEW YORK MERCANTILE EXCHANGE"]:
    df, err = fetch(m)
    if df is not None:
        ng_frames.append(df)
        print(f"   NG {m}: {len(df)} rows {df['date'].min().date()}→{df['date'].max().date()}")
    time.sleep(0.7)
if ng_frames:
    merged = pd.concat(ng_frames, ignore_index=True).drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    merged.to_csv(os.path.join(OUT, "cot_NG.csv"), index=False)
    results["NG"] = {"n_rows": int(len(merged)), "start": str(merged["date"].min().date()), "end": str(merged["date"].max().date())}
    print(f"OK NG merged: {len(merged)} rows")

print(json.dumps(results, indent=2, default=str))
