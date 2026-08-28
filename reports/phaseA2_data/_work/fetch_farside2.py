"""Try Farside again with full browser-like headers; also try alternate URL endpoints."""
import requests, time

URLS = [
    "https://farside.co.uk/bitcoin-etf-flow-all-data/",
    "https://farside.co.uk/btc/",
    "https://farside.co.uk/bitcoin-etf-flow/",
]

UA_VARIANTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

s = requests.Session()
for ua in UA_VARIANTS:
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    for url in URLS:
        try:
            r = s.get(url, headers=headers, timeout=20)
            print(f"{url} ua={ua[:30]} → {r.status_code} bytes={len(r.text)}")
            if r.status_code == 200 and "11 Jan 2024" in r.text:
                with open("/tmp/farside.html","w") as f: f.write(r.text)
                print("OK saved /tmp/farside.html")
                raise SystemExit(0)
        except Exception as e:
            print(f"{url}: {e}")
        time.sleep(2)
print("ALL FAIL")
