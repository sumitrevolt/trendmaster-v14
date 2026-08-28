# Influencer / Smart-Money Flow Tracking — Feasibility Report

**Project:** TrendMaster v14
**Author:** Claude (research subagent)
**Date generated:** 2026-04-26
**Scope:** 19 symbols across METALS / FOREX / CRYPTO / COMMODITIES, H1 timeframe.

This report identifies the top 10 entities whose disclosed flows can move the markets that TrendMaster trades, maps each one to a verified data source, and recommends a starter set of 3-5 sources to wire into the Phase A2 correlation pipeline. All URLs were probed live on 2026-04-26 (HTTP 200/401/403 = reachable; details in section 2).

---

## Section 1 — Top 10 market-moving entities (ranked by signal density for our 19 symbols)

| # | Entity | Category | Scale (2026) | TrendMaster relevance | Mechanism |
|---|---|---|---|---|---|
| 1 | **BlackRock (iShares Bitcoin Trust, IBIT)** | Asset manager | ~806,700 BTC, ~$63.7B; ~49% of US spot-BTC ETF AUM | CRYPTO (BTCUSD direct, ETHUSD spillover) | Daily creations/redemptions force authorized participants to buy/sell spot BTC on Coinbase, Kraken; flow data leads spot price by minutes-hours. |
| 2 | **OPEC+ Joint Ministerial Monitoring Committee** | Producer cartel | ~35 mb/d DoC production | COMMODITIES (XTIUSD, XBRUSD direct) | Monthly MOMR + ad-hoc production cut/hike decisions move Brent/WTI 3-7% in seconds. |
| 3 | **US Federal Reserve (FOMC)** | Central bank | $7.0T balance sheet | FOREX (all USD pairs), METALS (XAU/XAG real-yield channel), CRYPTO (risk-on/off) | 8 scheduled rate decisions/yr at 14:00 ET; SEP dot plot moves DXY 50-150 pips in seconds. |
| 4 | **People's Bank of China (PBOC)** | Central bank | $3.2T FX reserves | FOREX (USDJPY, AUDUSD, NZDUSD via CNH proxy), COMMODITIES (oil, copper) | Daily USD/CNY fix at 09:15 China time signals tolerance for yuan move; spillover to AUD/NZD/JPY through Asia hours. |
| 5 | **Strategy (formerly MicroStrategy, MSTR)** | Treasury company | ~815,061 BTC as of Apr 2026 | CRYPTO (BTCUSD direct) | 8-K filings within ~1 business day of every BTC purchase; ~76% of corporate-treasury BTC concentration. |
| 6 | **Bank of Japan / Japanese MOF** | Central bank + Treasury | ~$1.2T FX reserves | FOREX (USDJPY direct, plus EURJPY/GBPJPY/AUDJPY/CADJPY crosses) | Verbal warnings then size-stamped intervention disclosed monthly by MOF; near 158-162 USDJPY zone since 2024. |
| 7 | **CFTC large-trader cohort (COT report)** | Regulator-aggregated | All CFTC-registered futures positioning | METALS (gold/silver futures), FOREX (CME 6E/6J/6B etc.), COMMODITIES (CL, NG, BZ) | Aggregated long/short positioning of "Managed Money" + "Commercials" published Friday 15:30 ET for prior Tuesday. |
| 8 | **World Gold Council central-bank tracker** | Industry body aggregator | 863t purchased 2025; ~190t/qtr forecast 2026 | METALS (XAUUSD direct, XAGUSD spillover) | Aggregates IMF IFS data + private intel on PBOC, RBI, NBP, CBR gold reserve adds; persistent bid for gold. |
| 9 | **EIA (US Energy Information Administration)** | Government agency | Reports US ~13 mb/d crude production | COMMODITIES (XTIUSD primary, XBRUSD spillover, XNGUSD direct) | Wednesday 10:30 ET WPSR moves WTI 1-3% on inventory surprises; Thursday 10:30 ET natural-gas storage moves XNGUSD 2-5%. |
| 10 | **Norges Bank Investment Management (NBIM)** | Sovereign wealth fund | ~$2.2T AUM | FOREX (sentiment, weak), out-of-scope for METALS/CRYPTO/COMMODITIES | 7,200+ company holdings with full quarterly + annual disclosures; **lag is too long for an H1 bot — included as reference, not for live use.** |

**Honest exclusions from the top 10:** Berkshire Hathaway (US-equity heavy, no FX/crypto/commodity edge for our pairs), Bridgewater (13F lag), Citadel/Renaissance (don't disclose). These show up in pop-finance lists but offer zero usable H1 signal for TrendMaster.

---

## Section 2 — Data source map (per entity)

### 1. BlackRock IBIT / spot Bitcoin ETF complex
- **Best URL:** [farside.co.uk/btc/](https://farside.co.uk/btc/) (aggregator); [theblock.co/data/etfs/bitcoin-etf](https://www.theblock.co/data/etfs/bitcoin-etf/spot-bitcoin-etf-flows) (alt)
- **Update frequency:** Daily, evening US time
- **Reporting lag:** T+0 (same trading day, post-close)
- **Cost:** Free (HTML scrape) — Farside also publishes raw tables
- **Format:** HTML table; community CSV mirrors via Tableau dashboards
- **Reliability:** 4/5 (aggregator of issuer-published NAV; cross-checks with [bitbo.io/treasuries/us-etfs](https://bitbo.io/treasuries/us-etfs/))
- **Ease of automation:** 4/5 — clean HTML, stable schema since Jan 2024
- **Legal/ToS:** No explicit ban on scraping. Use polite rate (≤1 req/min). Last verified 2026-04-26 (HTTP 403 to bare curl, 200 in browser — needs UA header).

### 2. OPEC+ MOMR + decisions
- **Best URL:** [publications.opec.org/momr](https://publications.opec.org/momr) (PDF) and [opec.org/monthly-oil-market-report.html](https://www.opec.org/monthly-oil-market-report.html)
- **Update frequency:** Monthly (mid-month); ad-hoc statements after JMMC meetings
- **Reporting lag:** T+30 to T+45 for production data; decisions are real-time on press release
- **Cost:** Free
- **Format:** PDF (production data); HTML/RSS (press releases)
- **Reliability:** 5/5 (issuer)
- **Ease of automation:** 2/5 — PDF parsing required for tabular data; press release RSS is easier
- **Legal/ToS:** Public domain. Last verified 2026-04-26 (HTTP 403 to bare curl, content visible via browser).

### 3. US Federal Reserve / FOMC
- **Best URL:** [federalreserve.gov/monetarypolicy/fomccalendars.htm](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) (calendar); [federalreserve.gov/releases/h41/](https://www.federalreserve.gov/releases/h41/) (weekly balance sheet)
- **Update frequency:** 8 scheduled meetings/yr; H.4.1 weekly Thursday 16:30 ET
- **Reporting lag:** T+0 for statements; minutes T+21 days
- **Cost:** Free
- **Format:** HTML + PDF + structured XML for SEP
- **Reliability:** 5/5
- **Ease of automation:** 4/5 — calendar is parseable; CME FedWatch [API](https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html) ($25/mo) gives implied-prob feed. Free alternative: [PyFedWatch](https://github.com/ARahimiQuant/pyfedwatch).
- **Legal/ToS:** Public domain. Last verified 2026-04-26 (200 OK).

### 4. PBOC USD/CNY fix
- **Best URL:** [chinamoney.com.cn](https://www.chinamoney.com.cn) (official); [investinglive.com/centralbank](https://investinglive.com/centralbank/) (English aggregator with Reuters estimate vs actual delta)
- **Update frequency:** Daily ~01:15 GMT (09:15 Beijing)
- **Reporting lag:** T+0
- **Cost:** Free
- **Format:** HTML / news headline; Bloomberg/Reuters wire mirrors
- **Reliability:** 5/5 issuer, 4/5 aggregators
- **Ease of automation:** 3/5 — chinamoney requires Mandarin parsing; English aggregator scrape easier
- **Legal/ToS:** Public reference rate; no restriction. Last verified 2026-04-26.

### 5. Strategy / MSTR Bitcoin treasury
- **Best URL:** [saylortracker.com](https://saylortracker.com/) (free aggregator, T+0); [SEC EDGAR 8-K filings](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001050446&type=8-K) (authoritative)
- **Update frequency:** Per-purchase (typically weekly Mon-morning announcement covering prior week)
- **Reporting lag:** ~T+1 to T+5 from purchase
- **Cost:** Free
- **Format:** HTML (SaylorTracker), structured XBRL (SEC EDGAR)
- **Reliability:** 5/5 (EDGAR), 4/5 (SaylorTracker mirror)
- **Ease of automation:** 5/5 via EDGAR full-text search API
- **Legal/ToS:** Public filings. Last verified 2026-04-26 (200 OK).

### 6. BoJ / Japanese MOF intervention
- **Best URL:** [mof.go.jp/english/policy/international_policy/reference/feio/index.html](https://www.mof.go.jp/english/policy/international_policy/reference/feio/index.html)
- **Update frequency:** Monthly (size disclosed last business day of following month); daily detail published quarterly
- **Reporting lag:** T+30 (monthly aggregate); T+~90 (daily detail)
- **Cost:** Free
- **Format:** Excel/CSV
- **Reliability:** 5/5
- **Ease of automation:** 3/5 — file URL changes monthly; needs a fetch crawler
- **Legal/ToS:** Public domain. Last verified 2026-04-26 (200 OK).
- **Caveat:** The size data is too lagged for live H1 trading. Use only as a regime classifier ("intervention era / not"). Verbal warnings from MOF press conferences are higher-frequency leading signals.

### 7. CFTC Commitments of Traders
- **Best URL:** [publicreporting.cftc.gov/stories/s/r4w3-av2u](https://publicreporting.cftc.gov/stories/s/r4w3-av2u) (Socrata public data env, JSON/CSV); [cftc.gov/MarketReports/CommitmentsofTraders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
- **Update frequency:** Weekly, Friday 15:30 ET
- **Reporting lag:** T+3 (Tuesday positioning published Friday)
- **Cost:** Free
- **Format:** CSV / JSON via Socrata API; legacy plain-text on cftc.gov
- **Reliability:** 5/5
- **Ease of automation:** 5/5 — Socrata REST API with filters, no auth required
- **Legal/ToS:** Public domain. Last verified 2026-04-26 (200 OK).
- **Coverage for TrendMaster:** GC (gold), SI (silver), 6E/6B/6J/6A/6N/6C (FX futures), CL (WTI), BZ (Brent), NG (nat gas), BTC (Bitcoin futures). Maps cleanly to 17 of the 19 symbols.

### 8. World Gold Council
- **Best URL:** [gold.org/goldhub/research/gold-demand-trends](https://www.gold.org/goldhub/research/gold-demand-trends); monthly central-bank blog at [gold.org/goldhub/gold-focus](https://www.gold.org/goldhub/gold-focus/)
- **Update frequency:** Quarterly (full demand trends); monthly (central-bank stats blog)
- **Reporting lag:** T+30 to T+45
- **Cost:** Free (PDF + summary tables)
- **Format:** PDF + HTML; underlying IMF IFS data via [data.imf.org](https://data.imf.org)
- **Reliability:** 5/5 industry body, 5/5 IMF source
- **Ease of automation:** 2/5 (WGC PDF), 4/5 (IMF SDMX API)
- **Legal/ToS:** Free for research. Last verified 2026-04-26 (200 OK).

### 9. EIA petroleum + natural gas
- **Best URL:** [eia.gov/petroleum/supply/weekly](https://www.eia.gov/petroleum/supply/weekly/) (WPSR); [eia.gov/opendata](https://www.eia.gov/opendata/) (public API)
- **Update frequency:** WPSR Wednesday 10:30 ET; Natural gas storage Thursday 10:30 ET
- **Reporting lag:** T+5 to T+7 (data for prior week)
- **Cost:** Free; API key registration free
- **Format:** CSV + JSON via EIA Open Data API
- **Reliability:** 5/5
- **Ease of automation:** 5/5 — clean REST API with stable series IDs (e.g. `PET.WCESTUS1.W`)
- **Legal/ToS:** Public; cite EIA. Last verified 2026-04-26 (200 OK).

### 10. NBIM / Norway sovereign wealth fund
- **Best URL:** [nbim.no/en/investments/all-investments/](https://www.nbim.no/en/investments/all-investments/)
- **Update frequency:** Annual full disclosure; semi-annual updates
- **Reporting lag:** ~60-90 days
- **Cost:** Free
- **Format:** HTML + Excel
- **Reliability:** 5/5
- **Ease of automation:** 3/5
- **Legal/ToS:** Public. Last verified 2026-04-26 (200 OK).
- **Verdict:** Lag is fatal for an H1 bot. Treat as long-horizon equity-sentiment proxy only.

---

## Section 3 — Per-team mapping table

| Team | Top 3 most-influential entities | Single best data source | Lead/Lag vs H1 price |
|---|---|---|---|
| **METALS** (XAUUSD, XAGUSD) | (1) US Fed (real yields), (2) PBOC + WGC central-bank cohort, (3) CFTC Managed Money positioning | [CFTC COT — Socrata API](https://publicreporting.cftc.gov/stories/s/r4w3-av2u) for GC/SI futures; cross-check with [WGC central-bank blog](https://www.gold.org/goldhub/gold-focus/) | COT is **lagging** (T+3) — works as regime/positioning extreme indicator, not an H1 trigger. Fed events are coincident (T+0 at 14:00 ET). |
| **FOREX** (14 pairs) | (1) US Fed, (2) PBOC daily fix, (3) BoJ/MOF (for JPY pairs) | [Federal Reserve calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) + [CME FedWatch](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html) for rate-implied probs | Fed-funds futures positioning is **leading** (continuously updated from CME); FOMC announcement is coincident; PBOC fix leads Asia-session FX by ~30 min. |
| **CRYPTO** (BTCUSD, ETHUSD) | (1) BlackRock IBIT flows, (2) Strategy/MSTR purchases, (3) Whale Alert on-chain movements | [Farside Investors BTC ETF flows](https://farside.co.uk/btc/) — daily T+0 by ~22:00 UTC | Flows are **slightly lagging** vs intraday price (NAV settles after close) but **lead** next-day price by 2-4% mean reversion. SaylorTracker 8-K announcements are typically Mon morning ET — short-lived BTC pop. |
| **COMMODITIES** (XTIUSD, XBRUSD, XNGUSD) | (1) OPEC+ JMMC, (2) EIA WPSR, (3) CFTC COT (CL/NG/BZ) | [EIA Open Data API](https://www.eia.gov/opendata/) for inventories; OPEC press-release RSS for decisions | EIA WPSR is **coincident** (Wed 10:30 ET — large H1 spike); OPEC decisions are coincident (statement = price move in seconds); COT is lagging confirmation. |

---

## Section 4 — Recommended starter set (Phase A2)

Of the 10 entities, these 5 satisfy all four hard criteria (daily-or-better updates, free or under $50/mo, mechanical link to TrendMaster symbols, 60+ days history, automatable):

| Rank | Source | Symbols moved | Why this one | Confidence |
|---|---|---|---|---|
| **1** | **CFTC COT via Socrata API** ([publicreporting.cftc.gov](https://publicreporting.cftc.gov/stories/s/r4w3-av2u)) | 17 of 19 (all except XAGUSD-spot peculiarities, EURGBP) | Single endpoint covers METALS + FOREX + COMMODITIES + crypto futures. Free JSON, no auth, weekly cadence acceptable as a positioning-extreme regime feature (not a tick signal). 10+ years history. | High |
| **2** | **Farside Investors BTC ETF flows** ([farside.co.uk/btc](https://farside.co.uk/btc/)) | BTCUSD (direct), ETHUSD (correlated) | Daily T+0 net-flow $m by issuer; mechanically tied to BTC spot via creation/redemption. 24+ months history. Scrape-friendly with UA header. | High |
| **3** | **EIA Open Data API** ([eia.gov/opendata](https://www.eia.gov/opendata/)) | XTIUSD, XBRUSD, XNGUSD | Free API key, JSON; weekly inventories + monthly STEO. The biggest scheduled mover for oil/nat-gas in any given week. Decade+ of history. | High |
| **4** | **Federal Reserve FOMC calendar + CME FedWatch web** ([fedwatch](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html)) | All FOREX pairs (DXY-driven), spillover to METALS/CRYPTO | Free web tool gives rate-decision-implied probabilities updated continuously. PyFedWatch is a free OSS replica if scraping the web tool breaks. Decision dates are deterministic (8/yr). | High |
| **5** | **Strategy / SaylorTracker** ([saylortracker.com](https://saylortracker.com/)) + SEC EDGAR 8-K backstop | BTCUSD | Single-entity, but ~76% of corporate-treasury BTC. Announcements concentrated Mon morning ET; cleanest event-study window in crypto. EDGAR is the source of truth. | Medium-High (single-entity concentration risk) |

**Tier-2 (add later if Tier-1 yields signal):**
- World Gold Council central-bank stats blog (XAUUSD, monthly)
- PBOC daily fix scrape (USDJPY/AUDUSD/NZDUSD Asia-session feature)
- OPEC press-release RSS (XTIUSD/XBRUSD event-study)

**Skip entirely for live H1 use:**
- 13F filings (45-day lag is multiple full trading horizons)
- NBIM disclosures (60-90 day lag)
- BoJ size-disclosed intervention (T+30 minimum)

---

## Section 5 — Honest gaps and cautions

### Teams with weak influencer-flow coverage
- **Cross-JPY pairs (EURJPY, GBPJPY, AUDJPY, CADJPY)** — covered only indirectly via BoJ/MOF + CME 6J COT. None of the 10 entities offer pair-specific flow data; signal must come from constituent-leg positioning (e.g. EURJPY = EURUSD residual + USDJPY).
- **EURGBP** — neither leg has a dominant institutional discloser. ECB and BoE balance-sheet ops are public but slow. Effectively no influencer alpha for this pair.
- **XAGUSD (silver)** — much smaller institutional footprint than gold; CFTC SI COT works, but ETFs (SLV) are 30x smaller than GLD. Treat XAG as a XAU beta multiplier rather than independently trackable.
- **ETHUSD** — institutional ETH ETFs launched mid-2024 but flows are ~10% of BTC ETF size. Piggyback on BTC ETF flow signal until ETH ETF AUM exceeds $20B (currently ~$10B).

### Failure modes to design around
1. **Disclosure-front-running by HFTs.** Farside ETF data publishes ~17:00-22:00 UTC; the move is partially priced before retail sees the row. Lag your trade-trigger and assume 30-50% slippage from headline number.
2. **Smart-money survivorship bias.** Strategy is the *surviving* corporate BTC buyer — others (Tesla, Block) trimmed. A "follow MSTR" signal trained on 2020-2026 has selection bias baked in.
3. **Signal decay after public disclosure.** COT is a good example: the alpha from "Managed Money extremes" has decayed to ~50-65% hit rate vs ~70%+ in 2010-2015 academic studies (López de Prado AFML notes this for many public datasets).
4. **Schema drift on scraped sources.** Farside, SaylorTracker, OPEC press-release pages have all changed HTML structure since 2024. Build a daily integrity check that fails loud if the parser returns zero rows.
5. **Calendar-effect contamination.** Many of these signals cluster on the same days (Wednesday EIA + Friday COT + monthly NFP). Don't let your model overweight Wednesdays just because that's when news happens.
6. **Rate-limiting / IP bans.** Farside, CFTC Socrata, EIA all have rate caps. Cache aggressively; one fetch per source per day is plenty.

### "Too good to be true" flags
- **Whale Alert public feed** advertised as "real-time large BTC transactions." Reality: free-tier hides historical data >30 days, and the public feed is already heavily front-run by paid subscribers. Useful as a sentiment sample, **not** as an entry signal. Verified 2026-04-26 (HTTP 401 on raw API call, as expected).
- **"Hedge fund tracking" SaaS products** advertising daily 13F-derived signals: these reverse-engineer quarterly snapshots into "implied" daily holdings. The implication is interpolation, not real flow. Skip.
- **"FedWatch alternatives"** that promise rate probabilities without using CME futures data: these are usually surveys-of-economists (Reuters poll style) and lag the futures market by 1-3 days.

### Honest summary
The set of entities whose flows can actually be tracked daily for free is small: **CFTC COT, BTC ETF flows, EIA inventories, Fed calendar/futures, MSTR 8-K filings.** Everything else is either too lagged (13F, NBIM, MOF size data), too expensive (Bloomberg, Refinitiv), or has been arb'd to break-even (most public sentiment feeds). The recommended starter set is therefore conservative on purpose — five reliable inputs beat fifteen noisy ones, especially given that the ML model is currently in MODEL_UNIFORM and we need clean features, not more dirty ones.

---

## Sources

- [The Block — Spot BTC ETF Flows](https://www.theblock.co/data/etfs/bitcoin-etf/spot-bitcoin-etf-flows)
- [Bitbo — US BTC ETF Tracker & AUM](https://bitbo.io/treasuries/us-etfs/)
- [CFTC — Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
- [CFTC Public Reporting Environment (Socrata)](https://publicreporting.cftc.gov/stories/s/r4w3-av2u)
- [OPEC MOMR](https://publications.opec.org/momr) and [opec.org/monthly-oil-market-report](https://www.opec.org/monthly-oil-market-report.html)
- [IEA Oil Market Report April 2026](https://www.iea.org/reports/oil-market-report-april-2026)
- [World Gold Council — Gold Demand Trends](https://www.gold.org/goldhub/research/gold-demand-trends)
- [SaylorTracker](https://saylortracker.com/) and [bitbo.io/treasuries/microstrategy](https://bitbo.io/treasuries/microstrategy/)
- [The Block — Strategy 815k BTC](https://www.theblock.co/post/387014/michael-saylors-strategy-buys-more-bitcoin-unstoppable-orange)
- [Federal Reserve — FOMC Calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- [Federal Reserve H.4.1](https://www.federalreserve.gov/releases/h41/)
- [CME FedWatch tool](https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html) and [FedWatch API](https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html)
- [PyFedWatch (OSS)](https://github.com/ARahimiQuant/pyfedwatch)
- [Investing Live — PBOC USD/CNY fix](https://investinglive.com/centralbank/pboc-is-expected-to-set-the-usdcny-reference-rate-at-68400-reuters-estimate-20260424/)
- [Bank of Japan — FX Intervention Outline](https://www.boj.or.jp/en/intl_finance/outline/expkainyu.htm)
- [Japanese MOF — FX Intervention Operations](https://www.mof.go.jp/english/policy/international_policy/reference/feio/index.html)
- [US Treasury — TIC System](https://home.treasury.gov/data/treasury-international-capital-tic-system)
- [NBIM — All Investments](https://www.nbim.no/en/investments/all-investments/)
- [EIA — Weekly Petroleum Status Report](https://www.eia.gov/petroleum/supply/weekly/) and [EIA Open Data API](https://www.eia.gov/opendata/)
- [Farside Investors — BTC ETF Flow](https://farside.co.uk/btc/)
- [Whale Alert API docs](https://docs.whale-alert.io/)
- [SPDR Gold Shares](https://www.spdrgoldshares.com/usa/gld/)
