"""
SEC EDGAR full-text search for MSTR 8-K filings about Bitcoin.
CIK 0001050446 = MicroStrategy / Strategy.
"""
import requests, pandas as pd, os, json, time, re
OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"
HEADERS = {"User-Agent":"Sumit research@example.com"}  # SEC requires real-looking UA

# Index of recent 8-K filings via EDGAR JSON
url = "https://data.sec.gov/submissions/CIK0001050446.json"
r = requests.get(url, headers=HEADERS, timeout=30)
print("EDGAR submissions:", r.status_code, len(r.text))
if r.status_code != 200:
    raise SystemExit(1)

js = r.json()
filings = js.get("filings", {}).get("recent", {})
df = pd.DataFrame({k: filings.get(k, []) for k in filings.keys()})
print("recent filings cols:", list(df.columns))
print("total rows:", len(df))
# Filter 8-K with bitcoin in primaryDocument or items
df_8k = df[df["form"] == "8-K"].copy()
print(f"8-K count: {len(df_8k)}")
df_8k["filingDate"] = pd.to_datetime(df_8k["filingDate"])

# Save
df_8k.to_csv(os.path.join(OUT, "mstr_8k_filings.csv"), index=False)
print(df_8k[["filingDate","accessionNumber","primaryDocument","items"]].head(20))

# Items column shows reportable events; "Item 8.01" = "Other Events" common for BTC purchase announcements
# Heuristic: BTC-purchase 8-Ks usually have Item 8.01. Let's flag those.
df_8k["likely_btc"] = df_8k["items"].astype(str).str.contains("8.01", na=False)
btc_filings = df_8k[df_8k["likely_btc"]].copy()
print(f"\nLikely BTC 8-Ks (Item 8.01): {len(btc_filings)}")

# Need older filings — recent only goes ~1000. Add archive files
older_files = js.get("filings", {}).get("files", [])
print(f"\nAdditional older filing index files: {len(older_files)}")
# Fetch older indices
all_8k = [df_8k]
for f in older_files[:5]:  # at most 5 older files
    fname = f["name"]
    older_url = f"https://data.sec.gov/submissions/{fname}"
    print(f"  fetching {older_url}")
    rr = requests.get(older_url, headers=HEADERS, timeout=30)
    if rr.status_code == 200:
        oj = rr.json()
        # files index has same structure as 'recent'
        odf = pd.DataFrame({k: oj.get(k, []) for k in oj.keys() if isinstance(oj.get(k), list)})
        if "form" in odf.columns:
            odf_8k = odf[odf["form"] == "8-K"].copy()
            odf_8k["filingDate"] = pd.to_datetime(odf_8k["filingDate"])
            odf_8k["likely_btc"] = odf_8k["items"].astype(str).str.contains("8.01", na=False)
            all_8k.append(odf_8k)
            print(f"    +{len(odf_8k)} 8-K rows")
    time.sleep(0.5)

merged = pd.concat(all_8k, ignore_index=True)
merged["filingDate"] = pd.to_datetime(merged["filingDate"])
merged = merged.sort_values("filingDate").drop_duplicates("accessionNumber")
merged.to_csv(os.path.join(OUT, "mstr_8k_all.csv"), index=False)
print(f"\nALL 8-K: {len(merged)} from {merged['filingDate'].min().date()} to {merged['filingDate'].max().date()}")
print(f"Likely BTC (Item 8.01): {merged['likely_btc'].sum()}")
