---
name: trading-news-events
description: "News and event risk handling for a trading bot. Use when integrating an economic calendar (ForexFactory / Finnhub / TradingEconomics), building news-embargo windows, handling FOMC/NFP/CPI spike behavior, managing weekend gap risk, and adding sentiment / COT feeds. Covers scraping the calendar, the CSV contract between Python fetcher and EA, embargo math (minutes before/after), XAUUSD-specific exposure (PMI, ISM, DXY prints), and the 'news filter saves more accounts than any indicator' principle."
---

# trading-news-events

News kills retail accounts faster than any strategy mistake. A perfectly tuned trend-follower can lose a month of gains in three minutes around NFP. This skill covers how to detect, classify, and avoid (or occasionally trade) event risk.

**Core principle:** default to blocking entries in a ±N-minute window around high-impact news. Trading news is a specialty; avoiding news is a free win for retail.

## When to use

- Adding a news filter to the EA for the first time.
- Upgrading from a crude ±30-minute blanket filter to a per-event classification.
- Handling FOMC / ECB / BoE rate decisions (different tempo than NFP).
- Building a weekend gap handler.
- Integrating a sentiment / COT / positioning feed.

## 1. Economic calendar sources

| Source | Cost | Quality | Notes |
|---|---|---|---|
| **ForexFactory** (scraped) | Free | Good | De facto retail standard; HTML scraping; respect their ToS, cache aggressively |
| **Finnhub** | Free tier | Good | API, JSON, generous limits |
| **TradingEconomics** | Paid | Best | Clean API, full history, actual vs. forecast vs. previous |
| **investpy** (scrape investing.com) | Free | Good | Sometimes blocked; fragile |
| **MT5 built-in calendar** | Free | OK | `CalendarValueHistoryByEvent` in MQL5; limited filtering |

For this project, default to **ForexFactory scrape → CSV → EA reads file**, because it works offline and the EA never makes HTTP calls (fragile in MT5). Fall back to MT5 built-in if scraping breaks.

## 2. Python fetcher — ForexFactory

Run once daily as a scheduled task; writes `news.csv` into MT5's `Files/` folder.

```python
import requests, pandas as pd
from datetime import datetime, timedelta
import os

UA = "Mozilla/5.0 (trendmaster news bot; contact: <email>)"
FF = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"  # public JSON feed

def fetch_ff(out_csv: str):
    j = requests.get(FF, headers={"User-Agent": UA}, timeout=10).json()
    rows = []
    for e in j:
        # fields: title, country, date, impact, forecast, previous
        dt = datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        rows.append({
            "ts_utc":   dt.isoformat(),
            "country":  e.get("country", ""),
            "title":    e.get("title", ""),
            "impact":   e.get("impact", "").lower(),   # "high" / "medium" / "low" / "holiday"
            "forecast": e.get("forecast", ""),
            "previous": e.get("previous", ""),
        })
    df = pd.DataFrame(rows).sort_values("ts_utc")
    tmp = out_csv + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, out_csv)    # atomic
    return len(df)

# run daily at 00:05 UTC via scheduled-tasks
if __name__ == "__main__":
    n = fetch_ff(r"C:\...\MQL5\Files\news.csv")
    print(f"wrote {n} events")
```

**Atomic write matters** — the EA reads this file on every new bar. A half-written CSV crashes the parse.

## 3. EA consumption — news filter

Read the CSV in `OnInit` and on a timer (hourly refresh in case the Python fetcher ran mid-session).

```cpp
struct NewsEvent { datetime ts; string country; string title; int impact; };
NewsEvent g_news[];

int ImpactFromStr(string s) {
    StringToLower(s);
    if(s == "high")    return 3;
    if(s == "medium")  return 2;
    if(s == "low")     return 1;
    return 0;
}

bool LoadNews(string path)
{
    int h = FileOpen(path, FILE_READ|FILE_TXT|FILE_ANSI|FILE_CSV, ',');
    if(h == INVALID_HANDLE) return false;
    ArrayFree(g_news);
    // skip header
    for(int c = 0; c < 6; c++) FileReadString(h);
    while(!FileIsEnding(h)) {
        NewsEvent e;
        string ts_str = FileReadString(h);
        if(StringLen(ts_str) == 0) break;
        e.ts      = StringToTime(ts_str);
        e.country = FileReadString(h);
        e.title   = FileReadString(h);
        e.impact  = ImpactFromStr(FileReadString(h));
        FileReadString(h); FileReadString(h);   // forecast, previous
        int n = ArraySize(g_news); ArrayResize(g_news, n+1);
        g_news[n] = e;
    }
    FileClose(h);
    return true;
}

bool NewsEmbargoed(datetime now, int min_impact = 3, int before_sec = 900, int after_sec = 900)
{
    for(int i = 0; i < ArraySize(g_news); i++) {
        if(g_news[i].impact < min_impact) continue;
        if(!IsRelevantCountry(g_news[i].country)) continue;
        datetime t = g_news[i].ts;
        if(now >= t - before_sec && now <= t + after_sec) return true;
    }
    return false;
}
```

**Where `IsRelevantCountry` is symbol-aware:**

```cpp
bool IsRelevantCountry(string country)
{
    if(_Symbol == "XAUUSD" || _Symbol == "XAGUSD")
        return country == "USD" || country == "CNY" || country == "EUR";   // gold reacts to USD + China + Euro
    if(StringFind(_Symbol, "EUR") >= 0)
        return country == "EUR" || country == "USD";
    if(StringFind(_Symbol, "JPY") >= 0)
        return country == "JPY" || country == "USD";
    return country == "USD";   // fallback
}
```

## 4. Embargo windows by impact

| Impact | Before | After | Reason |
|---|---|---|---|
| **High** (NFP, FOMC, CPI, ECB rate) | 15 min | 15-60 min | Large vol spike + sustained repricing |
| **Medium** (GDP, PMI, retail sales) | 5 min | 15 min | Brief spike |
| **Low** | 0 | 0 | Usually no market-wide impact |

**FOMC / ECB specifically:** the *statement release* is at T+0, the *press conference* starts ~30 min later and often moves the market as much as the statement. Extend the window to T+90 min for rate-decision events:

```cpp
bool IsRateDecision(NewsEvent &e) {
    string t = e.title; StringToLower(t);
    return StringFind(t, "rate decision") >= 0
        || StringFind(t, "interest rate") >= 0
        || StringFind(t, "fomc statement") >= 0
        || StringFind(t, "press conference") >= 0;
}

int AfterSecFor(NewsEvent &e) {
    if(IsRateDecision(e)) return 90 * 60;
    return 15 * 60;
}
```

## 5. XAUUSD-specific event list

Gold reacts to a specific subset of events most strongly:

**Tier 1 (extreme reactions — always block):**
- US NFP (first Friday)
- US CPI
- FOMC rate decision + dot plot
- FOMC minutes (3 weeks after meeting)
- US ISM Manufacturing / Services PMI
- US PPI

**Tier 2 (strong reactions — block high-impact only):**
- US retail sales
- US GDP
- US core PCE
- DXY-adjacent: ECB rate, BoE rate

**Tier 3 (market-dependent):**
- China PMI, CPI (risk-on / risk-off proxy)
- Geopolitical headlines (manual — news feed scraping hard)

## 6. Handling holidays

Exchange holidays are as dangerous as news — thin liquidity, wide spreads, random price action. Treat as another calendar event.

```python
HOLIDAYS_US = {"2026-01-01": "New Year", "2026-07-04": "Independence Day", ...}

def is_holiday(d: datetime, country: str = "US") -> bool:
    key = d.strftime("%Y-%m-%d")
    return key in HOLIDAYS_US
```

Block trading on:
- US holidays (XAUUSD, US equity CFDs, USD-pairs)
- UK holidays (GBP pairs)
- Major religious holidays (Easter Monday, Christmas Eve, etc.)

Build a small JSON file + Python refresher; same file-based delivery as news.

## 7. Weekend gap handling

Forex gaps over weekends. XAUUSD, oil, indices can gap materially.

**Rules:**

- Close all positions 30-60 min before Friday session close if held overnight risk is unacceptable.
- Alternatively, reduce position size by half on Friday afternoons.
- On Sunday open, wait 15-30 min before taking any entry — the Sunday/Monday spread is wide and prices whip.

```cpp
bool WeekendRisk(datetime now)
{
    MqlDateTime t; TimeToStruct(now, t);
    // Friday 20:00 UTC onwards (~1h before close)
    if(t.day_of_week == 5 && t.hour >= 20) return true;
    // Sunday 22:00 UTC through Monday 00:00 UTC (reopen churn)
    if(t.day_of_week == 0 && t.hour >= 22) return true;
    if(t.day_of_week == 1 && t.hour < 1)   return true;
    return false;
}
```

Adjust hours to your broker's exact session schedule — they differ slightly.

## 8. Sentiment feeds

Two types worth considering:

### 8a. COT (Commitments of Traders) — weekly

CFTC publishes Friday EOD. Retail uses net-positioning of large speculators as a contrarian or momentum signal.

```python
# Download via pandas or the cot_reports package
from cot_reports import cot_all
df = cot_all("legacy_fut")   # or "financial_futures"
# filter for Gold, read "noncomm_positions_long_all" vs "_short_all"
```

Weekly → stale by trade time. Useful as a regime feature, not an entry signal.

### 8b. News sentiment (NLP)

Free options: Finnhub sentiment, or roll your own with a FinBERT model on scraped headlines.

```python
from transformers import pipeline
nlp = pipeline("sentiment-analysis", model="ProsusAI/finbert")
result = nlp(headline)   # [{"label": "positive"/"negative"/"neutral", "score": 0.9}]
```

**Reality check:** retail NLP sentiment rarely moves the needle; the signal is already in prices by the time headlines are parsed. Skip unless you're building an experimental research track.

### 8c. Positioning data (alt)

Some brokers publish retail positioning ("72% of retail clients are long EURUSD"). Classic contrarian signal. Sources: OANDA, IG, FXBlue aggregators.

## 9. Trading news vs. avoiding news

Two philosophies:

**Avoid (default for retail):** block entries ±N min around high-impact events. Stable, safe, leaves some expected-value on the table but eliminates tail risk.

**Trade news (advanced):**
- Straddle strategy: pending buy-stop + sell-stop 20-30 pips beyond current price, cancel the unfilled after 30 min. Wide SL, trail aggressively.
- Post-spike mean reversion: after 1-2 min of violent movement, fade back to pre-news price (risky, requires tight execution).
- NFP number-vs-forecast: if actual > forecast by 2σ, buy DXY / sell gold for 15 min.

News trading needs ultra-low-latency execution and a broker that doesn't widen spreads to 50+ pips during news. Most retail setups don't qualify. Stick with "avoid" unless you've specifically built for it.

## 10. Integration with the 4-filter funnel

In this project's EA, news filter sits **early** in `TryEntry`:

```
TryEntry():
  if(!NewsClear()) return;              // news filter — EARLY exit
  if(!SessionOK()) return;
  if(!SpreadOK()) return;
  if(confirmations < 3) return;
  if(!CheckHTFGate(...)) return;
  if(!BrainSignalOK(...)) return;
  SendOrder(...);
```

News check is cheap (array lookup) — put it first to short-circuit expensive computation during embargoed windows.

## 11. Common news-handling bugs

- **Stale `news.csv`** (Python fetcher crashed overnight) → default to embargoing everything if file > 6 hours old, not to trading through unknown events.
- **Timezone confusion** → ForexFactory JSON is UTC; MT5 `TimeCurrent()` is broker server time. Compute in UTC on both sides or you'll be off by 2-3 hours.
- **Missing medium-impact releases** → some indicators are "medium" on FF but move markets (e.g. ADP). Maintain a manual override list.
- **Country name mismatch** → ForexFactory uses "USD" / "EUR"; TradingEconomics uses "United States" / "Euro Area". Normalize in the fetcher.
- **Holiday interpretation** → "Bank holiday UK" means GBP markets are thin but still open; "Federal Reserve Holiday" means US markets closed. Different handling.
- **News filter too aggressive** → blocks all trading, account doesn't compound. Tighten windows; consider impact-tier (only block "high" not "medium").

## 12. Scheduled-task pattern for news fetcher

Use the project's `scheduled-tasks` skill. Run once per day at 00:05 UTC:

```python
# register_news_task.py
{
    "name": "fetch-news-daily",
    "cron": "5 0 * * *",
    "command": "python",
    "args": ["C:/.../tools/fetch_news.py"],
}
```

Also run once on brain startup (in case scheduled task missed overnight).

## 13. GitHub references

- `bennycode/forex-news-event-parser` — example FF scraper patterns.
- `nickmccullum/python-for-finance-cookbook` — chapter on calendar integration.
- `RomelTorres/alpha_vantage` — if you switch to Alpha Vantage for events + fundamentals.
- `eduardofv/news-sentiment-trading` — FinBERT + trading gluecode.
- `DeltaML/Forex-News-Algo` — simple ForexFactory → CSV → MT5 reference.

## Extension workflow

Adding a new event source:

1. Write a Python fetcher that outputs the same CSV schema (ts_utc, country, title, impact, forecast, previous).
2. Register as a scheduled task with a fallback schedule (daily + startup).
3. Add symbol-country mapping if needed in `IsRelevantCountry`.
4. Don't change the CSV contract without bumping a version field — EA must remain backward-compatible with old files.

Tightening / loosening a filter:

1. Change `before_sec` / `after_sec` in the input group (expose as `InpNewsBeforeSec`, `InpNewsAfterSec`).
2. Run backtest with and without the change on same data.
3. Compare: did blocked trades have net-positive or net-negative PnL? If blocked trades averaged losses, tighten was correct.
4. Commit the `.set` change with the rationale in the commit message.
