"""
EIA Open Data v1 series endpoint (no auth needed for some) — try v2 with no key, then v1 fallback.
PET.WCESTUS1.W = U.S. Ending Stocks of Crude Oil (excluding SPR), weekly, kbbl
NG.NW2_EPG0_SWO_R48_BCF.W = U.S. Working Gas in Storage, weekly, Bcf  (or NG.NW2_EPG0_SWO_R48_MMBBL.W)
"""
import requests, pandas as pd, os, json, time

OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"
HEADERS = {"User-Agent":"Mozilla/5.0 (TrendMaster-research/1.0)"}

# v1 series API — deprecated but still works for some series
# Documented at https://www.eia.gov/opendata/qb.php
# We'll try multiple endpoints

V1 = "https://api.eia.gov/series/?series_id={sid}&out=json"

# Without API key, v1 returns auth error; need a free key. Try anyway:
SERIES = {
    "crude_stocks_us": "PET.WCESTUS1.W",
    "ng_storage_us":   "NG.NW2_EPG0_SWO_R48_BCF.W",
}

# Free public alternative: EIA dashboard CSV downloads
PUBLIC_DASHBOARD = {
    "crude_stocks_us": "https://www.eia.gov/dnav/pet/hist_xls/WCESTUS1w.xls",
    "ng_storage_us":   "https://ir.eia.gov/ngs/wngsr.xls",  # weekly natural gas storage report Excel
}

# Also a v2 endpoint (no key — should hit register-required, but maybe sample works)
V2 = "https://api.eia.gov/v2/seriesid/{sid}"

# Try public Excel
import io
results = {}
for name, url in PUBLIC_DASHBOARD.items():
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        print(f"{url}: {r.status_code} {len(r.content)}b")
        if r.status_code == 200 and len(r.content) > 5000:
            # Save raw
            with open(os.path.join(OUT, f"eia_{name}_raw.xls"), "wb") as f:
                f.write(r.content)
            try:
                df = pd.read_excel(io.BytesIO(r.content), sheet_name=None)
                for sheet, sdf in df.items():
                    print(f"  sheet={sheet} shape={sdf.shape}")
                # Save first non-trivial sheet
                non_empty = {k:v for k,v in df.items() if v.shape[0] > 50}
                if non_empty:
                    chosen_name, chosen = list(non_empty.items())[-1]  # data sheet usually last
                    chosen.to_csv(os.path.join(OUT, f"eia_{name}.csv"), index=False)
                    print(f"  saved eia_{name}.csv from sheet {chosen_name}")
                    results[name] = {"sheet": chosen_name, "rows": int(chosen.shape[0])}
            except Exception as e:
                print(f"  parse: {e}")
        time.sleep(1)
    except Exception as e:
        print(f"{url}: {e}")

print(json.dumps(results, indent=2))
