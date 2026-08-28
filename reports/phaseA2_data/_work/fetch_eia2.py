import requests, pandas as pd, os, json, time, io
OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"
HEADERS = {"User-Agent":"Mozilla/5.0 (TrendMaster-research/1.0)"}

# Crude stocks – we already have the xls saved
xls_path = os.path.join(OUT, "eia_crude_stocks_us_raw.xls")
df = pd.read_excel(xls_path, sheet_name="Data 1", skiprows=2)
print("Crude xls cols:", list(df.columns)[:5], "rows:", len(df))
df.columns = ["date", "crude_stocks_kbbl"]
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df = df.dropna(subset=["date","crude_stocks_kbbl"]).sort_values("date").reset_index(drop=True)
df["delta"] = df["crude_stocks_kbbl"].diff()
df.to_csv(os.path.join(OUT, "eia_crude_stocks.csv"), index=False)
print(f"crude_stocks: {len(df)} rows {df['date'].min().date()}→{df['date'].max().date()}")

# Nat gas — try alternative public URL
NG_URLS = [
    "https://www.eia.gov/dnav/ng/hist_xls/NW2_EPG0_SWO_R48_BCFw.xls",
    "https://www.eia.gov/dnav/ng/xls/NG_STOR_WKLY_S1_W.xls",
]
for url in NG_URLS:
    r = requests.get(url, headers=HEADERS, timeout=30)
    print(f"{url}: {r.status_code} {len(r.content)}")
    if r.status_code == 200 and len(r.content) > 5000:
        with open(os.path.join(OUT, "eia_ng_storage_raw.xls"), "wb") as f:
            f.write(r.content)
        try:
            xs = pd.ExcelFile(io.BytesIO(r.content))
            print("  sheets:", xs.sheet_names)
            for sn in xs.sheet_names:
                if "Data" in sn or "data" in sn:
                    sdf = pd.read_excel(xs, sheet_name=sn, skiprows=2)
                    sdf.columns = ["date", "ng_stocks_bcf"]
                    sdf["date"] = pd.to_datetime(sdf["date"], errors="coerce")
                    sdf = sdf.dropna(subset=["date","ng_stocks_bcf"]).sort_values("date").reset_index(drop=True)
                    sdf["delta"] = sdf["ng_stocks_bcf"].diff()
                    sdf.to_csv(os.path.join(OUT, "eia_ng_storage.csv"), index=False)
                    print(f"  ng saved: {len(sdf)} rows {sdf['date'].min().date()}→{sdf['date'].max().date()}")
                    break
        except Exception as e:
            print(f"  parse error: {e}")
        break
    time.sleep(1)
