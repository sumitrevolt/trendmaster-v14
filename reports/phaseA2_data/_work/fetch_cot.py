"""
CFTC COT Legacy Futures-Only — non-commercial vs commercial.
Socrata endpoint: https://publicreporting.cftc.gov/resource/6dca-aqww.json
Schema: noncomm_positions_long_all, noncomm_positions_short_all,
        comm_positions_long_all, comm_positions_short_all
For our analysis, "speculator net" = noncomm_long - noncomm_short (proxy for managed money).
"""
import requests, pandas as pd, time, os, json
from urllib.parse import urlencode

OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"
HEADERS = {"User-Agent": "Mozilla/5.0 (TrendMaster-research/1.0)"}

# Markets — verified by enumerating distinct contract_market_name in the dataset for our targets.
TARGETS = {
    "GC":  "GOLD - COMMODITY EXCHANGE INC.",
    "SI":  "SILVER - COMMODITY EXCHANGE INC.",
    "CL":  "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
    "BZ":  "BRENT LAST DAY FINANCIAL - NEW YORK MERCANTILE EXCHANGE",
    "NG":  "NATURAL GAS - NEW YORK MERCANTILE EXCHANGE",
    "6E":  "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "6J":  "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "6B":  "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE",
    "6A":  "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "6N":  "NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "6C":  "CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
    "6S":  "SWISS FRANC - CHICAGO MERCANTILE EXCHANGE",
    "BTC": "BITCOIN - CHICAGO MERCANTILE EXCHANGE",
}

session = requests.Session()
session.headers.update(HEADERS)

def fetch(market_name, since_year=2010):
    base = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    where = f"market_and_exchange_names='{market_name}' AND report_date_as_yyyy_mm_dd >= '{since_year}-01-01T00:00:00.000'"
    params = {
        "$where": where,
        "$select": "report_date_as_yyyy_mm_dd,market_and_exchange_names,noncomm_positions_long_all,noncomm_positions_short_all,comm_positions_long_all,comm_positions_short_all,open_interest_all",
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": "50000"
    }
    url = base + "?" + urlencode(params)
    r = session.get(url, timeout=30)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    data = r.json()
    if not data:
        return None, "empty result"
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.tz_localize(None)
    for c in ["noncomm_positions_long_all","noncomm_positions_short_all","comm_positions_long_all","comm_positions_short_all","open_interest_all"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["spec_net"] = df["noncomm_positions_long_all"] - df["noncomm_positions_short_all"]
    df["comm_net"] = df["comm_positions_long_all"] - df["comm_positions_short_all"]
    df = df.sort_values("date").reset_index(drop=True)
    return df, None

results = {}
for code, market_name in TARGETS.items():
    try:
        df, err = fetch(market_name)
        if err:
            results[code] = {"error": err, "market": market_name}
            print(f"FAIL {code} {market_name!r}: {err}")
        else:
            out = os.path.join(OUT, f"cot_{code}.csv")
            df.to_csv(out, index=False)
            results[code] = {"n_rows": int(len(df)), "start": str(df["date"].min().date()), "end": str(df["date"].max().date()), "market": market_name}
            print(f"OK {code} {market_name}: {len(df)} rows {df['date'].min().date()} → {df['date'].max().date()}")
        time.sleep(0.8)
    except Exception as e:
        results[code] = {"error": str(e)}
        print(f"FAIL {code}: {e}")

with open(os.path.join(OUT, "_cot_fetch_summary.json"), "w") as f:
    json.dump(results, f, indent=2, default=str)
print("DONE")
