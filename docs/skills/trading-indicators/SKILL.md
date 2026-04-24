---
name: trading-indicators
description: "Canonical technical-indicator implementations for both MQL5 and Python, side-by-side. Use when adding, porting, or auditing an indicator: EMA/SMA, RSI, ADX, MACD, ATR, Bollinger Bands, SuperTrend, Ichimoku, VWAP, Heikin-Ashi, Pivots, Order Blocks / FVGs. Covers math, off-by-one traps, MQL5 iBuffer vs Pandas vectorization differences, and how to keep the two languages in lockstep so backtest and live numbers match."
---

# trading-indicators

An indicator that computes differently in Python (backtest) and MQL5 (live) is a silent bug. This skill catalogues canonical implementations in both languages for the indicators this project actually uses, with the math explicit so you can audit any divergence.

**Core principle:** Don't trust TA libraries — know the formula. Every subtle difference between `pandas-ta`, `TA-Lib`, and MQL5's built-ins comes down to:
- Initial-value seeding (SMA of first N vs. first value vs. zero)
- Wilder smoothing (`1/N`) vs. EMA smoothing (`2/(N+1)`)
- Whether the current bar is included (MQL5 `shift=0` is the forming bar)

## When to use

- Adding a new indicator to the brain *and* the EA — you want identical numbers.
- Auditing why backtest signals fire but live doesn't (or vice versa).
- Porting a freqtrade / pandas-ta strategy to MQL5.
- Teaching / refreshing — the math is condensed here so you don't have to re-read a TA textbook.

## Shared conventions

Throughout this skill:

- `close`, `high`, `low`, `open` are same-length series or buffers.
- All functions operate on **closed bars only** — drop the last bar in Python (`df.iloc[:-1]`) or use `shift=1` in MQL5 when reading fresh values.
- Period defaults match `pandas-ta` / `TA-Lib` / MT5 defaults unless noted.

## 1. Moving averages — EMA, SMA, WMA

### Python

```python
def sma(s, n): return s.rolling(n).mean()
def ema(s, n): return s.ewm(span=n, adjust=False).mean()     # standard EMA, alpha = 2/(n+1)
def wma(s, n):
    w = pd.Series(range(1, n+1), dtype=float)
    return s.rolling(n).apply(lambda x: (x * w).sum() / w.sum(), raw=True)
```

**`adjust=False`** is critical. With `adjust=True` (pandas default), the EMA is computed using full historical weights on the warm-up window, which doesn't match MQL5. Always `adjust=False`.

### MQL5

```cpp
int h_ema = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_EMA,  PRICE_CLOSE);
int h_sma = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_SMA,  PRICE_CLOSE);
int h_wma = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_LWMA, PRICE_CLOSE);   // note: LWMA, not WMA

double buf[];
CopyBuffer(h_ema, 0, 1, 1, buf);     // shift=1 → previous closed bar
double ema_val = buf[0];
```

**Gotcha — EMA seeding:** MT5's EMA seeds from the SMA of the first N bars. `pandas.ewm(adjust=False)` seeds from the first value. For long series (>> N), this washes out by bar 3-4N. For short series, values differ — always compare after >= 5N bars.

## 2. RSI (Relative Strength Index)

Wilder's original formulation uses smoothing factor `1/N`, **not** `2/(N+1)`. This matters.

### Python

```python
def rsi(close, n=14):
    delta = close.diff()
    up =  delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = -delta.clip(upper=0).ewm(alpha=1/n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - (100 / (1 + rs))
```

### MQL5

```cpp
int h_rsi = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);
double buf[]; CopyBuffer(h_rsi, 0, 1, 1, buf);
double rsi_val = buf[0];
```

**Matches exactly** because MT5's `iRSI` uses Wilder smoothing by default. Using `pandas-ta.rsi` without `mamode="rma"` (or equivalent) will give different numbers — audit that.

## 3. MACD

### Python

```python
def macd(close, fast=12, slow=26, sig=9):
    line = ema(close, fast) - ema(close, slow)
    signal = ema(line, sig)
    hist = line - signal
    return line, signal, hist
```

### MQL5

```cpp
int h_macd = iMACD(_Symbol, PERIOD_H1, 12, 26, 9, PRICE_CLOSE);
double line[], sig[];
CopyBuffer(h_macd, 0, 1, 1, line);   // MAIN_LINE
CopyBuffer(h_macd, 1, 1, 1, sig);    // SIGNAL_LINE
double hist = line[0] - sig[0];
```

**Gotcha:** MT5's histogram buffer (`MODE_MAIN` vs `MODE_SIGNAL` with some plot types) can return pre-scaled values depending on indicator variant. Compute `hist = line - signal` yourself for portability.

## 4. ATR (Average True Range)

Wilder smoothing again, not EMA.

### Python

```python
def atr(high, low, close, n=14):
    prev = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev).abs(),
        (low  - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
```

### MQL5

```cpp
int h_atr = iATR(_Symbol, PERIOD_H1, 14);
double buf[]; CopyBuffer(h_atr, 0, 1, 1, buf);
double atr_val = buf[0];
```

## 5. ADX / DI+ / DI-

The trickiest common indicator to match precisely. MT5's `iADX` uses Wilder smoothing; most Python libs default to EMA.

### Python (Wilder-accurate)

```python
def adx(high, low, close, n=14):
    prev_c = close.shift(1)
    tr = pd.concat([high-low, (high-prev_c).abs(), (low-prev_c).abs()], axis=1).max(axis=1)
    atr_s = tr.ewm(alpha=1/n, adjust=False).mean()

    up_move  = high.diff()
    dn_move  = -low.diff()
    plus_dm  = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)

    plus_di  = 100 * pd.Series(plus_dm,  index=close.index).ewm(alpha=1/n, adjust=False).mean() / atr_s
    minus_di = 100 * pd.Series(minus_dm, index=close.index).ewm(alpha=1/n, adjust=False).mean() / atr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()
```

### MQL5

```cpp
int h_adx = iADX(_Symbol, PERIOD_H1, 14);
double adx_b[], plus_b[], minus_b[];
CopyBuffer(h_adx, 0, 1, 1, adx_b);    // MAIN = ADX
CopyBuffer(h_adx, 1, 1, 1, plus_b);   // PLUSDI
CopyBuffer(h_adx, 2, 1, 1, minus_b);  // MINUSDI
```

**Audit it:** compute ADX in Python on the same bars MT5 has, compare bar-by-bar. Differences > 0.5 mean smoothing mismatch — fix Python, not MQL5 (MT5 is authoritative).

## 6. Bollinger Bands

### Python

```python
def bbands(close, n=20, k=2.0):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std(ddof=0)        # population std — matches MT5
    return mid - k*std, mid, mid + k*std
```

**`ddof=0`** is essential. Pandas default is `ddof=1` (sample std) which produces slightly wider bands than MT5.

### MQL5

```cpp
int h_bb = iBands(_Symbol, PERIOD_H1, 20, 0, 2.0, PRICE_CLOSE);
double up[], mid[], lo[];
CopyBuffer(h_bb, 0, 1, 1, mid);   // BASE_LINE (middle)
CopyBuffer(h_bb, 1, 1, 1, up);    // UPPER_BAND
CopyBuffer(h_bb, 2, 1, 1, lo);    // LOWER_BAND
```

## 7. SuperTrend

Not in MT5 built-ins or pandas-ta's default index — implement it yourself, identically in both languages.

### Python

```python
def supertrend(high, low, close, period=10, multiplier=3.0):
    a = atr(high, low, close, period)
    hl2 = (high + low) / 2.0
    up_basic = hl2 + multiplier * a
    dn_basic = hl2 - multiplier * a

    up, dn, trend = np.zeros(len(close)), np.zeros(len(close)), np.ones(len(close), dtype=int)
    for i in range(1, len(close)):
        up[i] = min(up_basic.iloc[i], up[i-1]) if close.iloc[i-1] <= up[i-1] else up_basic.iloc[i]
        dn[i] = max(dn_basic.iloc[i], dn[i-1]) if close.iloc[i-1] >= dn[i-1] else dn_basic.iloc[i]
        if trend[i-1] == +1:
            trend[i] = -1 if close.iloc[i] < dn[i-1] else +1
        else:
            trend[i] = +1 if close.iloc[i] > up[i-1] else -1
    return trend, up, dn
```

### MQL5 (simplified — loop inside `OnTick` or buffer on each new bar)

```cpp
double ST_Up[], ST_Dn[], ST_ATR[];
int    ST_Trend[];

void SuperTrendUpdate(int shift, int period, double mult)
{
    double hl2  = (iHigh(_Symbol, _Period, shift) + iLow(_Symbol, _Period, shift)) / 2.0;
    double a    = iATR_shift(period, shift);     // wrap iATR + CopyBuffer
    double up_b = hl2 + mult * a;
    double dn_b = hl2 - mult * a;

    // Same carry-over logic as Python version
    double prev_close = iClose(_Symbol, _Period, shift+1);
    ST_Up[shift] = (prev_close <= ST_Up[shift+1]) ? MathMin(up_b, ST_Up[shift+1]) : up_b;
    ST_Dn[shift] = (prev_close >= ST_Dn[shift+1]) ? MathMax(dn_b, ST_Dn[shift+1]) : dn_b;

    double close = iClose(_Symbol, _Period, shift);
    if(ST_Trend[shift+1] == +1)
        ST_Trend[shift] = (close < ST_Dn[shift+1]) ? -1 : +1;
    else
        ST_Trend[shift] = (close > ST_Up[shift+1]) ? +1 : -1;
}
```

**Gotcha:** SuperTrend is *stateful* — bar `t` depends on bar `t-1`'s values. Backtest must warm up ≥ 2× period bars before trusting output. In live MQL5, initialize from the first N bars during `OnInit`.

## 8. Ichimoku Kinko Hyo

```python
def ichimoku(high, low, close, conv=9, base=26, span_b=52, displacement=26):
    hh = lambda s, n: s.rolling(n).max()
    ll = lambda s, n: s.rolling(n).min()
    tenkan   = (hh(high, conv)   + ll(low, conv))   / 2
    kijun    = (hh(high, base)   + ll(low, base))   / 2
    span_a   = ((tenkan + kijun) / 2).shift(displacement)
    span_b_s = ((hh(high, span_b) + ll(low, span_b)) / 2).shift(displacement)
    chikou   = close.shift(-displacement)       # plotted 26 bars behind
    return tenkan, kijun, span_a, span_b_s, chikou
```

MT5: `iIchimoku(_Symbol, PERIOD_H4, 9, 26, 52)` with buffers 0-4 for the five lines. Numbers match if `conv/base/span_b` params align.

**Chikou gotcha:** the `-displacement` shift means `chikou` at time `t` uses `close[t+26]` — that's future data! Only safe to read `chikou` values for bars at least `displacement` in the past. In live trading, never query chikou for the current or recent bars.

## 9. VWAP (Volume Weighted Average Price)

Intraday indicator — resets at session start. Retail MT5 volume is tick-volume (not real volume), but VWAP still gives a reasonable intraday anchor.

```python
def session_vwap(df: pd.DataFrame) -> pd.Series:
    """df must have: high, low, close, tick_volume, session_date column or index-based grouping"""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = tp * df["tick_volume"]
    cum_pv  = pv.groupby(df.index.date).cumsum()
    cum_vol = df["tick_volume"].groupby(df.index.date).cumsum()
    return cum_pv / cum_vol
```

MT5: no native `iVWAP`. Either implement in MQL5 with arrays reset per session, or import from a community indicator (`Zigzag_VWAP.mq5` variants on the MQL5 code base).

## 10. Heikin-Ashi

Smoothed candles — each HA candle is a function of the previous HA candle plus current OHLC.

```python
def heikin_ashi(df):
    ha = pd.DataFrame(index=df.index)
    ha["close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    ha_open = [(df["open"].iloc[0] + df["close"].iloc[0]) / 2.0]
    for i in range(1, len(df)):
        ha_open.append((ha_open[-1] + ha["close"].iloc[i-1]) / 2.0)
    ha["open"] = ha_open
    ha["high"] = df[["high"]].join(ha[["open","close"]]).max(axis=1)
    ha["low"]  = df[["low"]].join(ha[["open","close"]]).min(axis=1)
    return ha
```

**Use as a filter only**, not for entries. HA candles lag real price and using them for execution puts you behind the market.

## 11. Pivot Points (classic / Fibonacci)

Daily pivot from previous day's HLC.

```python
def classic_pivots(prev_high, prev_low, prev_close):
    p = (prev_high + prev_low + prev_close) / 3.0
    r1, s1 = 2*p - prev_low, 2*p - prev_high
    r2, s2 = p + (prev_high - prev_low), p - (prev_high - prev_low)
    r3 = prev_high + 2*(p - prev_low)
    s3 = prev_low  - 2*(prev_high - p)
    return dict(P=p, R1=r1, R2=r2, R3=r3, S1=s1, S2=s2, S3=s3)
```

Compute at session start, display as horizontal lines on the chart via `ObjectCreate(..., OBJ_HLINE, ...)`.

## 12. Order Blocks & Fair-Value-Gaps (SMC style)

Popular in "Smart Money Concepts" trading. Not in standard libraries — code it yourself.

**Order Block (bullish):** the last bearish candle before a sharp impulse move up. Marked as a supply→demand flip.

```python
def bullish_order_blocks(df, impulse_atr_mult=1.5):
    a = atr(df["high"], df["low"], df["close"], 14)
    body = df["close"] - df["open"]
    impulse = body > impulse_atr_mult * a
    obs = []
    for i in range(1, len(df)):
        if impulse.iloc[i]:
            # walk back to last bearish candle
            for j in range(i-1, max(i-10, 0), -1):
                if df["close"].iloc[j] < df["open"].iloc[j]:
                    obs.append({"idx": j, "top": df["open"].iloc[j], "bot": df["low"].iloc[j]})
                    break
    return obs
```

**Fair-Value-Gap (FVG):** three-candle pattern where candle 1 high is below candle 3 low (or vice versa). Marks an imbalance.

```python
def fvgs(df):
    gaps = []
    for i in range(2, len(df)):
        h1, l3 = df["high"].iloc[i-2], df["low"].iloc[i]
        l1, h3 = df["low"].iloc[i-2],  df["high"].iloc[i]
        if l3 > h1:   gaps.append({"idx": i, "kind": "bull", "bot": h1, "top": l3})
        elif h3 < l1: gaps.append({"idx": i, "kind": "bear", "bot": h3, "top": l1})
    return gaps
```

**Retail reality check:** SMC is hugely popular but empirically noisy — backtests often show no edge after realistic spread. Treat as context, not a signal, unless you've rigorously validated.

## 13. Keeping MQL5 and Python in lockstep

Three practices:

1. **One source of truth per indicator.** For built-ins (EMA, RSI, MACD, ATR, ADX, BBands) — let MT5's `i*` be the reference, audit Python to match. For custom (SuperTrend, VWAP, Order Blocks) — write once, port; keep the formula in a `.md` file next to both implementations.
2. **Cross-validation script.** A small Python script that pulls the same N bars MT5 has, computes indicators both ways (Python native + via `mt5.copy_buffer` from a compiled indicator), and asserts `abs(diff) < 1e-3` bar by bar. Run in CI.
3. **Shared constants file.** Periods, multipliers, price-source (`PRICE_CLOSE` vs. median) live in ONE place — `config/indicators.py` in Python, mirrored as `#define`s in MQL5. If they drift, the cross-validation script catches it.

## 14. Common indicator bugs

- **Repaint** — indicator looks backwards when a new bar forms because it rebuilds from live data. Fix: use closed-bar-only (`shift>=1`) in MQL5, `.iloc[:-1]` in Python.
- **ADX/RSI divergence between platforms** → Wilder vs. EMA smoothing. Use `alpha=1/n` not `span=n`.
- **SMA vs. EMA seeding drift** → only affects first ~5N bars; ignore for production, fix for deterministic unit tests.
- **Bollinger band width mismatch** → `ddof=0` (population) vs `ddof=1` (sample) std.
- **SuperTrend resets after restart** → needs warm-up; persist last N bars of state to disk or recompute from N bars back on startup.
- **Using `high[0]` / `low[0]` in MQL5** → this is the forming bar; use `shift=1`.

## 15. GitHub references

- `pandas-ta` source — reference implementations of nearly all indicators above; read the source, not the README, for actual math.
- `mrjbq7/ta-lib` — battle-tested C indicators with Python bindings; authoritative when pandas-ta disagrees.
- MQL5 code base — search each indicator name, compare built-in vs. community variants.
- `twopirllc/pandas-ta` — the main maintained fork of pandas-ta; check `talib` compatibility flags (`mamode="rma"` for Wilder).
- `furk4neren/Order-Block` (and similar) — community implementations of SMC indicators; use as reference not dogma.

## Extension workflow

Adding a new indicator:

1. Write the math in Markdown first — formulas, seeding, smoothing, edge cases.
2. Implement in Python (vectorized) and validate against a known reference (pandas-ta or TA-Lib).
3. Implement in MQL5 (iterative or buffered).
4. Add to cross-validation script; assert `< 1e-3` divergence on 1000-bar sample.
5. Add to `config/indicators.py` constants; use everywhere instead of magic numbers.
6. Document in this skill under the appropriate section.
