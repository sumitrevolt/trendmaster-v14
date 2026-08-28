"""
Phase A2 correlation analysis kernel.

For each (source, symbol) pair:
  - align signal to symbol return at lag 0/+1/+2/+3 periods (period unit varies by source)
  - compute Pearson + Spearman per lag
  - identify best lag by |Pearson|
  - bootstrap 95% CI on best lag
  - 70/30 time split for OOS validation
  - assign verdict
"""
import os, json, sys
import numpy as np, pandas as pd
from scipy import stats

OUT = "/sessions/laughing-sleepy-faraday/mnt/autmated trading/reports/phaseA2_data"
RNG = np.random.default_rng(42)

def load_price(symbol):
    p = os.path.join(OUT, f"price_{symbol}.csv")
    if not os.path.exists(p): return None
    df = pd.read_csv(p, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df

def make_returns(df, period="W"):
    """Return DataFrame indexed by period-end date with log returns."""
    df = df.set_index("date").sort_index()
    if period == "W":
        # Use Friday close
        wk = df["close"].resample("W-FRI").last()
        ret = np.log(wk).diff()
        return pd.DataFrame({"close": wk, "ret": ret}).dropna()
    elif period == "D":
        ret = np.log(df["close"]).diff()
        return pd.DataFrame({"close": df["close"], "ret": ret}).dropna()
    raise ValueError(period)

def lag_corr(signal, ret, max_lag=3):
    """Returns dict of {lag: (pearson, spearman, n)}."""
    out = {}
    for lag in range(0, max_lag+1):
        # Forward return at lag k = sum of returns from t+0..t+k (cumulative if k>0) — for simplicity use single-period at offset
        # We use single-period forward return at lag k: ret.shift(-k)
        s = signal.copy()
        r = ret.shift(-lag)
        merged = pd.concat([s.rename("sig"), r.rename("ret")], axis=1).dropna()
        if len(merged) < 10:
            out[lag] = (np.nan, np.nan, len(merged))
            continue
        try:
            p = stats.pearsonr(merged["sig"], merged["ret"])[0]
            sp = stats.spearmanr(merged["sig"], merged["ret"])[0]
        except Exception:
            p, sp = np.nan, np.nan
        out[lag] = (p, sp, len(merged))
    return out

def bootstrap_ci(signal, ret, n=1000, ci=0.95):
    merged = pd.concat([signal.rename("sig"), ret.rename("ret")], axis=1).dropna()
    if len(merged) < 30:
        return (np.nan, np.nan)
    arr = merged.to_numpy()
    boots = []
    n_obs = len(arr)
    for _ in range(n):
        idx = RNG.integers(0, n_obs, size=n_obs)
        sample = arr[idx]
        if sample[:,0].std() == 0 or sample[:,1].std() == 0:
            continue
        boots.append(stats.pearsonr(sample[:,0], sample[:,1])[0])
    if not boots: return (np.nan, np.nan)
    lo, hi = np.percentile(boots, [(1-ci)/2*100, (1-(1-ci)/2)*100])
    return (lo, hi)

def is_oos_split(signal, ret, lag, frac=0.7):
    merged = pd.concat([signal.rename("sig"), ret.shift(-lag).rename("ret")], axis=1).dropna()
    if len(merged) < 40:
        return (np.nan, np.nan, len(merged), 0, 0)
    cut = int(frac * len(merged))
    is_p = stats.pearsonr(merged["sig"].iloc[:cut], merged["ret"].iloc[:cut])[0]
    oos_p = stats.pearsonr(merged["sig"].iloc[cut:], merged["ret"].iloc[cut:])[0]
    return (is_p, oos_p, len(merged), cut, len(merged)-cut)

def verdict(corr, oos_sign_match):
    a = abs(corr) if corr is not None and not np.isnan(corr) else 0
    if a >= 0.10 and oos_sign_match:
        return "EDGE"
    if a >= 0.05:
        return "WEAK"
    return "NONE"

# ===== Build COT analysis =====

COT_MAP = [
    ("CFTC COT GC", "GC", "XAUUSD", False),
    ("CFTC COT SI", "SI", "XAGUSD", False),
    ("CFTC COT 6E", "6E", "EURUSD", False),
    ("CFTC COT 6J", "6J", "USDJPY", True),  # invert
    ("CFTC COT 6B", "6B", "GBPUSD", False),
    ("CFTC COT 6A", "6A", "AUDUSD", False),
    ("CFTC COT 6C", "6C", "USDCAD", True),
    ("CFTC COT 6S", "6S", "USDCHF", True),
    ("CFTC COT 6N", "6N", "NZDUSD", False),
    ("CFTC COT CL", "CL", "XTIUSD", False),
    ("CFTC COT BZ", "BZ", "XBRUSD", False),
    ("CFTC COT NG", "NG", "XNGUSD", False),
    ("CFTC COT BTC", "BTC", "BTCUSD", False),
]

results = []

for source_name, code, symbol, invert in COT_MAP:
    cot_path = os.path.join(OUT, f"cot_{code}.csv")
    if not os.path.exists(cot_path):
        results.append({"source": source_name, "symbol": symbol, "error": "missing cot file"})
        continue
    cot = pd.read_csv(cot_path, parse_dates=["date"])
    cot = cot.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    # Signal: change in spec_net (Δposition) — better than level (level is non-stationary)
    cot["spec_delta"] = cot["spec_net"].diff()
    cot = cot.dropna(subset=["spec_delta"])
    cot = cot.set_index("date")["spec_delta"]

    pdf = load_price(symbol)
    if pdf is None:
        results.append({"source": source_name, "symbol": symbol, "error": "missing price"})
        continue
    rdf = make_returns(pdf, "W")  # weekly returns aligned to Friday
    if invert:
        rdf["ret"] = -rdf["ret"]

    # Align: COT is "as of Tuesday", report Friday — we want Friday return AFTER COT report
    # So we shift COT signal date forward to that week's Friday by ceiling to Friday.
    # Easiest: reindex COT by week-end Friday using nearest forward
    cot_weekly = cot.reindex(rdf.index, method="ffill", limit=7)

    # Compute correlations at lag 0..3 weeks
    lags = lag_corr(cot_weekly, rdf["ret"], max_lag=3)
    # Pick best lag by |Pearson|
    valid = [(lag, p, sp, n) for lag, (p, sp, n) in lags.items() if not np.isnan(p)]
    if not valid:
        results.append({"source": source_name, "symbol": symbol, "error": "all NaN corrs"})
        continue
    best = max(valid, key=lambda t: abs(t[1]))
    best_lag, best_p, best_sp, best_n = best

    # Bootstrap on best lag
    lo, hi = bootstrap_ci(cot_weekly, rdf["ret"].shift(-best_lag), n=500)

    # OOS
    is_p, oos_p, n_total, n_is, n_oos = is_oos_split(cot_weekly, rdf["ret"], best_lag)
    sign_match = (np.sign(is_p) == np.sign(oos_p)) if not (np.isnan(is_p) or np.isnan(oos_p)) else False

    v = verdict(best_p, sign_match)
    results.append({
        "source": source_name,
        "symbol": symbol,
        "freq": "W",
        "n": best_n,
        "date_start": str(rdf.index.min().date()),
        "date_end": str(rdf.index.max().date()),
        "lag0_pearson": lags[0][0],  "lag0_spearman": lags[0][1],
        "lag1_pearson": lags[1][0],  "lag1_spearman": lags[1][1],
        "lag2_pearson": lags[2][0],  "lag2_spearman": lags[2][1],
        "lag3_pearson": lags[3][0],  "lag3_spearman": lags[3][1],
        "best_lag": best_lag,
        "best_pearson": best_p,
        "best_spearman": best_sp,
        "boot_lo": lo, "boot_hi": hi,
        "is_pearson": is_p, "oos_pearson": oos_p,
        "oos_sign_match": bool(sign_match),
        "n_is": n_is, "n_oos": n_oos,
        "verdict": v,
        "inverted": invert,
    })
    print(f"{source_name}:{symbol} lag={best_lag} r={best_p:.3f} OOS={oos_p:.3f} sign_match={sign_match} {v}")

# ===== Farside ETF flows (proxy: dollar-volume) =====
etf_path = os.path.join(OUT, "etf_dollar_volume.csv")
etf = pd.read_csv(etf_path, parse_dates=["date"]).set_index("date").sort_index()

btc = load_price("BTCUSD")
btc_d = make_returns(btc, "D")

for sig_col, label in [("total_dv", "Farside-ETF total $-volume (proxy for net flow)"),
                       ("IBIT", "Farside-ETF IBIT $-volume (proxy for net flow)")]:
    if sig_col not in etf.columns:
        continue
    sig = etf[sig_col].copy()
    # Use first-difference of log $-volume to make stationary (raw $-volume is non-stationary)
    sig = np.log(sig.replace(0, np.nan)).diff().dropna()

    # Align to BTC daily index
    sig = sig.reindex(btc_d.index)
    lags = lag_corr(sig, btc_d["ret"], max_lag=3)
    valid = [(lag, p, sp, n) for lag, (p, sp, n) in lags.items() if not np.isnan(p)]
    if not valid:
        results.append({"source": label, "symbol": "BTCUSD", "error": "all NaN"})
        continue
    best_lag, best_p, best_sp, best_n = max(valid, key=lambda t: abs(t[1]))
    lo, hi = bootstrap_ci(sig, btc_d["ret"].shift(-best_lag), n=500)
    is_p, oos_p, n_total, n_is, n_oos = is_oos_split(sig, btc_d["ret"], best_lag)
    sign_match = (np.sign(is_p) == np.sign(oos_p)) if not (np.isnan(is_p) or np.isnan(oos_p)) else False
    v = verdict(best_p, sign_match)
    results.append({
        "source": label, "symbol": "BTCUSD", "freq": "D", "n": best_n,
        "date_start": str(sig.dropna().index.min().date()), "date_end": str(sig.dropna().index.max().date()),
        "lag0_pearson": lags[0][0], "lag0_spearman": lags[0][1],
        "lag1_pearson": lags[1][0], "lag1_spearman": lags[1][1],
        "lag2_pearson": lags[2][0], "lag2_spearman": lags[2][1],
        "lag3_pearson": lags[3][0], "lag3_spearman": lags[3][1],
        "best_lag": best_lag, "best_pearson": best_p, "best_spearman": best_sp,
        "boot_lo": lo, "boot_hi": hi,
        "is_pearson": is_p, "oos_pearson": oos_p, "oos_sign_match": bool(sign_match),
        "n_is": n_is, "n_oos": n_oos, "verdict": v, "inverted": False,
    })
    print(f"{label}:BTCUSD lag={best_lag} r={best_p:.3f} OOS={oos_p:.3f} {v}")

# ===== EIA crude inventory delta =====
crude = pd.read_csv(os.path.join(OUT, "eia_crude_stocks.csv"), parse_dates=["date"]).set_index("date")
crude_delta = crude["delta"].dropna()

for sym in ["XTIUSD", "XBRUSD"]:
    px = load_price(sym)
    rdf = make_returns(px, "W")
    sig = crude_delta.reindex(rdf.index, method="ffill", limit=7)
    lags = lag_corr(sig, rdf["ret"], max_lag=3)
    valid = [(lag, p, sp, n) for lag, (p, sp, n) in lags.items() if not np.isnan(p)]
    if not valid: continue
    best_lag, best_p, best_sp, best_n = max(valid, key=lambda t: abs(t[1]))
    lo, hi = bootstrap_ci(sig, rdf["ret"].shift(-best_lag), n=500)
    is_p, oos_p, _, n_is, n_oos = is_oos_split(sig, rdf["ret"], best_lag)
    sign_match = (np.sign(is_p) == np.sign(oos_p)) if not (np.isnan(is_p) or np.isnan(oos_p)) else False
    v = verdict(best_p, sign_match)
    results.append({
        "source": "EIA crude stocks Δ", "symbol": sym, "freq": "W", "n": best_n,
        "date_start": str(sig.dropna().index.min().date()), "date_end": str(sig.dropna().index.max().date()),
        "lag0_pearson": lags[0][0], "lag0_spearman": lags[0][1],
        "lag1_pearson": lags[1][0], "lag1_spearman": lags[1][1],
        "lag2_pearson": lags[2][0], "lag2_spearman": lags[2][1],
        "lag3_pearson": lags[3][0], "lag3_spearman": lags[3][1],
        "best_lag": best_lag, "best_pearson": best_p, "best_spearman": best_sp,
        "boot_lo": lo, "boot_hi": hi,
        "is_pearson": is_p, "oos_pearson": oos_p, "oos_sign_match": bool(sign_match),
        "n_is": n_is, "n_oos": n_oos, "verdict": v, "inverted": False,
    })
    print(f"EIA-Crude-Δ:{sym} lag={best_lag} r={best_p:.3f} OOS={oos_p:.3f} {v}")

# Nat gas
ng = pd.read_csv(os.path.join(OUT, "eia_ng_storage.csv"), parse_dates=["date"]).set_index("date")
ng_delta = ng["delta"].dropna()
px = load_price("XNGUSD")
rdf = make_returns(px, "W")
sig = ng_delta.reindex(rdf.index, method="ffill", limit=7)
lags = lag_corr(sig, rdf["ret"], max_lag=3)
valid = [(lag, p, sp, n) for lag, (p, sp, n) in lags.items() if not np.isnan(p)]
if valid:
    best_lag, best_p, best_sp, best_n = max(valid, key=lambda t: abs(t[1]))
    lo, hi = bootstrap_ci(sig, rdf["ret"].shift(-best_lag), n=500)
    is_p, oos_p, _, n_is, n_oos = is_oos_split(sig, rdf["ret"], best_lag)
    sign_match = (np.sign(is_p) == np.sign(oos_p)) if not (np.isnan(is_p) or np.isnan(oos_p)) else False
    v = verdict(best_p, sign_match)
    results.append({
        "source": "EIA NG storage Δ", "symbol": "XNGUSD", "freq": "W", "n": best_n,
        "date_start": str(sig.dropna().index.min().date()), "date_end": str(sig.dropna().index.max().date()),
        "lag0_pearson": lags[0][0], "lag0_spearman": lags[0][1],
        "lag1_pearson": lags[1][0], "lag1_spearman": lags[1][1],
        "lag2_pearson": lags[2][0], "lag2_spearman": lags[2][1],
        "lag3_pearson": lags[3][0], "lag3_spearman": lags[3][1],
        "best_lag": best_lag, "best_pearson": best_p, "best_spearman": best_sp,
        "boot_lo": lo, "boot_hi": hi,
        "is_pearson": is_p, "oos_pearson": oos_p, "oos_sign_match": bool(sign_match),
        "n_is": n_is, "n_oos": n_oos, "verdict": v, "inverted": False,
    })
    print(f"EIA-NG-Δ:XNGUSD lag={best_lag} r={best_p:.3f} OOS={oos_p:.3f} {v}")

# ===== FedWatch proxy (ZQ implied rate change) =====
zq = pd.read_csv(os.path.join(OUT, "fedfunds_zq_front.csv"), parse_dates=["date"]).set_index("date")
# Signal: 30-day change in implied rate (negative = pricing cuts)
fedwatch_sig = zq["implied_rate_pct"].diff(30).dropna()

for sym, invert in [("EURUSD", False), ("USDJPY", True), ("XAUUSD", False)]:
    px = load_price(sym)
    rd = make_returns(px, "D")
    if invert:
        rd["ret"] = -rd["ret"]
    sig = fedwatch_sig.reindex(rd.index, method="ffill", limit=7)
    lags = lag_corr(sig, rd["ret"], max_lag=3)
    valid = [(lag, p, sp, n) for lag, (p, sp, n) in lags.items() if not np.isnan(p)]
    if not valid: continue
    best_lag, best_p, best_sp, best_n = max(valid, key=lambda t: abs(t[1]))
    lo, hi = bootstrap_ci(sig, rd["ret"].shift(-best_lag), n=500)
    is_p, oos_p, _, n_is, n_oos = is_oos_split(sig, rd["ret"], best_lag)
    sign_match = (np.sign(is_p) == np.sign(oos_p)) if not (np.isnan(is_p) or np.isnan(oos_p)) else False
    v = verdict(best_p, sign_match)
    results.append({
        "source": "FedWatch (ZQ 30d Δ implied rate)", "symbol": sym, "freq": "D", "n": best_n,
        "date_start": str(sig.dropna().index.min().date()), "date_end": str(sig.dropna().index.max().date()),
        "lag0_pearson": lags[0][0], "lag0_spearman": lags[0][1],
        "lag1_pearson": lags[1][0], "lag1_spearman": lags[1][1],
        "lag2_pearson": lags[2][0], "lag2_spearman": lags[2][1],
        "lag3_pearson": lags[3][0], "lag3_spearman": lags[3][1],
        "best_lag": best_lag, "best_pearson": best_p, "best_spearman": best_sp,
        "boot_lo": lo, "boot_hi": hi,
        "is_pearson": is_p, "oos_pearson": oos_p, "oos_sign_match": bool(sign_match),
        "n_is": n_is, "n_oos": n_oos, "verdict": v, "inverted": invert,
    })
    print(f"FedWatch:{sym} lag={best_lag} r={best_p:.3f} OOS={oos_p:.3f} {v}")

# ===== MSTR 8-K event study =====
mstr = pd.read_csv(os.path.join(OUT, "mstr_8k_all.csv"), parse_dates=["filingDate"])
# Keep only post-2020-08-11 (first BTC purchase) and Item 8.01
mstr_btc = mstr[(mstr["filingDate"] >= "2020-08-11") & (mstr["likely_btc"] == True)].copy()
event_dates = pd.DatetimeIndex(mstr_btc["filingDate"].dt.normalize().unique())
print(f"MSTR-likely-BTC events: {len(event_dates)} from {event_dates.min().date()} to {event_dates.max().date()}")

# Event window [-5,+5] returns vs unconditional
btc = load_price("BTCUSD")
btc_d = make_returns(btc, "D")
ret = btc_d["ret"]

window_pre, window_post = 5, 5
event_returns = []
for ed in event_dates:
    # Find next trading day on/after event
    sub = ret.loc[ed-pd.Timedelta(days=10):ed+pd.Timedelta(days=15)]
    if len(sub) < window_pre + window_post + 1: continue
    # Find index of event date (or next available)
    after_idx = sub.index.searchsorted(ed)
    if after_idx == 0 or after_idx > len(sub) - window_post - 1: continue
    pre = sub.iloc[max(0, after_idx-window_pre):after_idx].sum()
    post = sub.iloc[after_idx:after_idx+window_post].sum()
    cum = sub.iloc[max(0, after_idx-window_pre):after_idx+window_post].sum()
    event_returns.append({"event_date": ed, "cum_return_-5_+5": cum, "pre_-5_0": pre, "post_0_+5": post})

ev_df = pd.DataFrame(event_returns)
print(f"event-study sample: {len(ev_df)}")
mean_event = ev_df["cum_return_-5_+5"].mean()
mean_post  = ev_df["post_0_+5"].mean()
unconditional_10d = ret.rolling(10).sum().mean()
unconditional_5d  = ret.rolling(5).sum().mean()
# t-test event mean vs 0 and vs unconditional
t_stat, p_val = stats.ttest_1samp(ev_df["cum_return_-5_+5"].dropna(), unconditional_10d)
t_stat_post, p_val_post = stats.ttest_1samp(ev_df["post_0_+5"].dropna(), unconditional_5d)
# Treat effect size = mean_event / std as "Pearson-like"
n_ev = len(ev_df)
effect = mean_event / ev_df["cum_return_-5_+5"].std() if n_ev > 1 else np.nan
effect_post = mean_post / ev_df["post_0_+5"].std() if n_ev > 1 else np.nan

# IS/OOS event split
mid = n_ev // 2
is_mean = ev_df["cum_return_-5_+5"].iloc[:mid].mean()
oos_mean = ev_df["cum_return_-5_+5"].iloc[mid:].mean()
sign_match = np.sign(is_mean) == np.sign(oos_mean)

# Synth a "best_pearson"-like value = effect size; treat threshold same
v = verdict(effect, sign_match)

results.append({
    "source": "Strategy/MSTR 8-K event-window", "symbol": "BTCUSD", "freq": "event",
    "n": n_ev,
    "date_start": str(event_dates.min().date()), "date_end": str(event_dates.max().date()),
    "lag0_pearson": effect, "lag0_spearman": effect_post,  # repurposed
    "best_lag": 0, "best_pearson": effect, "best_spearman": effect_post,
    "boot_lo": np.nan, "boot_hi": np.nan,
    "is_pearson": is_mean, "oos_pearson": oos_mean, "oos_sign_match": bool(sign_match),
    "n_is": mid, "n_oos": n_ev-mid, "verdict": v, "inverted": False,
    "extra_event_mean_-5_+5": mean_event,
    "extra_event_mean_post_0_+5": mean_post,
    "extra_unconditional_10d": unconditional_10d,
    "extra_unconditional_5d": unconditional_5d,
    "extra_t_event_vs_uncond": t_stat,
    "extra_p_event_vs_uncond": p_val,
    "extra_t_post_vs_uncond": t_stat_post,
    "extra_p_post_vs_uncond": p_val_post,
})
print(f"MSTR event N={n_ev}, mean[-5,+5]={mean_event:.4f}, post[0,+5]={mean_post:.4f}, t={t_stat:.2f} p={p_val:.3f}, OOS_sign_match={sign_match}")

# ===== Save results =====
res_df = pd.DataFrame(results)
res_df.to_csv(os.path.join(OUT, "_phaseA2_results.csv"), index=False)
print(f"\n=== SAVED {len(res_df)} result rows ===")
print(res_df[["source","symbol","n","best_lag","best_pearson","oos_pearson","oos_sign_match","verdict"]].to_string(index=False))
