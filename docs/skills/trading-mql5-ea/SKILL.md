---
name: trading-mql5-ea
description: "MQL5 Expert Advisor scaffolding for MetaTrader 5. Use when building, extending, or reviewing an EA: inputs/handles, OnInit/OnTimer/OnTick, risk + SL/TP, session/news filters, HTF gate, compile-via-CLI, chart visual overlays. Based on AI_SUPERBB_v14 + public MQL5 samples."
---

# MQL5 Expert Advisor pattern

A battle-tested layout for MQL5 EAs that trade a single symbol with confirmation layers, a multi-timeframe gate, and an external AI signal input. Proven on `AI_SUPERBB_v14_TrendMaster.mq5` (XAUUSD, OctaFX-Demo).

## 1. File header

```mql5
//+------------------------------------------------------------------+
//|                              AI_SUPERBB_v14_TrendMaster.mq5       |
//|   Single-symbol (XAUUSD) trend-follower with:                     |
//|     - 3-of-3 local confirmations (SuperTrend / BB / MACD)         |
//|     - HTF gate across M30 + H1 + H4                               |
//|     - External Python brain via JSON file (optional)              |
//|     - 1s dashboard heartbeat in OnTimer                           |
//|     - Sub-ms position management via GetMicrosecondCount in OnTick|
//+------------------------------------------------------------------+
#property copyright "..."
#property version   "1.14"
#property strict
#include <Trade/Trade.mqh>
#include <Trade/PositionInfo.mqh>
#include <Trade/SymbolInfo.mqh>

CTrade         Trade;
CPositionInfo  Pos;
CSymbolInfo    Sym;
```

## 2. Input groups

Organize inputs into visual groups so the EA properties dialog is navigable. Each group has a clear purpose.

```mql5
input group "=== GENERAL ==="
input long    InpMagic          = 20260420;
input string  InpComment        = "TrendMasterV14";
input bool    InpAllowLong      = true;
input bool    InpAllowShort     = true;

input group "=== RISK / SIZING ==="
input double  InpRiskPct        = 1.0;
input bool    InpAdaptiveSize   = true;   // Kelly-scaled
input double  InpMaxRiskPct     = 2.0;    // cap
input double  InpMaxDailyLossPc = 3.0;    // kill switch

input group "=== CONFIRMATION LAYER ==="
input int     InpST_Period      = 10;
input double  InpST_Mult        = 3.0;
input int     InpEMA_Fast       = 20;
input int     InpEMA_Slow       = 50;
input int     InpEMA_Trend      = 200;
input int     InpADX_Period     = 14;
input double  InpADX_Min        = 22.0;
input bool    InpRequireAll3    = true;

input group "=== EXIT / MANAGEMENT ==="
input double  InpSL_AtrMult     = 1.2;    // 1.2 on H4, 1.5 on M5
input double  InpTP_AtrMult     = 3.5;    // aim for >=1:2 RR
input bool    InpUsePartial1    = true;   // +1R -> close 40% + BE
input bool    InpUsePartial2    = true;   // +2R -> close 30% + lock +1R
input bool    InpUseChandelier  = true;

input group "=== AI / PYTHON GATE ==="
input bool    InpUseAIGate      = true;
input string  InpAISignalFile   = "trendmaster_signals.json";
input int     InpAIStaleSecs    = 60;
input bool    InpAIRequired     = false;  // false = advisory, true = mandatory

input group "=== HTF GATE (M30+H1+H4) ==="
input bool             InpUseHTFGate     = true;
input ENUM_TIMEFRAMES  InpHTFTrendTF     = PERIOD_H4;
input ENUM_TIMEFRAMES  InpHTFMomentumTF  = PERIOD_H1;
input ENUM_TIMEFRAMES  InpHTFTimingTF    = PERIOD_M30;
input double           InpHTF_ADX_Min    = 20.0;

input group "=== VISUAL (chart overlays) ==="
input bool    InpShowEMAs       = true;
input bool    InpShowBB         = true;
input bool    InpShowSuperTrend = true;
input bool    InpShowArrows     = true;
input bool    InpShowSLTPLines  = true;
input int     InpDrawBars       = 300;
```

## 3. Indicator handle layout

Declare handles as file-scope ints, create in `OnInit()`, check `INVALID_HANDLE`. For the HTF gate, only create handles when the gate is enabled — no wasted resources.

```mql5
int h_st_atr, h_ema_f, h_ema_s, h_ema_t;
int h_adx, h_bb, h_macd, h_atr;
// HTF gate
int h_htf_ema_f = INVALID_HANDLE, h_htf_ema_s = INVALID_HANDLE;
int h_htf_ema_t = INVALID_HANDLE, h_htf_adx   = INVALID_HANDLE;
int h_h1_macd   = INVALID_HANDLE;
int h_m30_ema_f = INVALID_HANDLE, h_m30_rsi   = INVALID_HANDLE;

int OnInit()
{
    Trade.SetExpertMagicNumber(InpMagic);
    h_ema_f = iMA(_Symbol, _Period, InpEMA_Fast, 0, MODE_EMA, PRICE_CLOSE);
    // ... etc
    if(h_ema_f == INVALID_HANDLE /* ... */) return INIT_FAILED;

    if(InpUseHTFGate)
    {
        h_htf_ema_f = iMA(_Symbol, InpHTFTrendTF, InpEMA_Fast,  0, MODE_EMA, PRICE_CLOSE);
        h_h1_macd   = iMACD(_Symbol, InpHTFMomentumTF, InpMACD_Fast, InpMACD_Slow, InpMACD_Sig, PRICE_CLOSE);
        h_m30_rsi   = iRSI(_Symbol, InpHTFTimingTF, 14, PRICE_CLOSE);
        // ...
    }

    EventSetTimer(1);  // 1s heartbeat
    return INIT_SUCCEEDED;
}
```

## 4. Event handlers — separation of concerns

| Handler | Frequency | Responsibility |
|---|---|---|
| `OnInit` | once | allocate handles, register timer, snapshot daily balance |
| `OnDeinit` | once | `EventKillTimer()`, `ObjectsDeleteAll(0, PFX)` cleanup |
| `OnTimer` | 1 Hz | dashboard draw, chart overlays, `ChartRedraw(0)` |
| `OnTick` | every tick | `ManagePositions()` (sub-ms trailing/partials) then `TryEntry()` |

Management uses `GetMicrosecondCount()` as a monotonic clock — a 1 ms minimum gap throttles tick-storms without sleeping.

```mql5
void ManagePositions()
{
    ulong tnow = GetMicrosecondCount();
    if(g_last_tick_us != 0 && tnow - g_last_tick_us < 1000) return;
    g_last_tick_us = tnow;
    // ... partial closes, break-even, chandelier trail
}
```

## 5. `FillConfirmations()` — the 3-of-3 core

Collapse the three classic confirmations into one struct so `TryEntry` and the dashboard read from the same source of truth.

```mql5
struct ConfSet {
    int    trend_dir;   // +1 / -1 / 0
    int    c1_trend, c2_vola, c3_momo;  // each 0 or 1
    int    agreed;      // 0..3
    double atr, adx;
};

bool CopyOne(int h, int buf, int shift, double &out)
{
    double arr[];
    if(CopyBuffer(h, buf, shift, 1, arr) != 1) return false;
    out = arr[0];
    return MathIsValidNumber(out);
}
```

`shift=1` means "last closed bar" — never trigger on the forming bar.

## 6. `CheckHTFGate()` — unanimous M30+H1+H4 alignment

Runs inside MQL5 so it blocks even when the Python brain is down. Fail-open on handle warm-up (NaN buffers shouldn't block valid setups during cold boot).

```mql5
bool CheckHTFGate(int dir_want, string &reason)
{
    if(!InpUseHTFGate) return true;
    if(h_htf_ema_f == INVALID_HANDLE) { reason="HTF warm-up"; return true; }

    // H4: EMA fan + ADX strength + price side
    double e20, e50, e200, adx_h4;
    CopyOne(h_htf_ema_f, 0, 1, e20);
    CopyOne(h_htf_ema_s, 0, 1, e50);
    CopyOne(h_htf_ema_t, 0, 1, e200);
    CopyOne(h_htf_adx,   0, 1, adx_h4);
    if(adx_h4 < InpHTF_ADX_Min) { reason="H4 ADX weak"; return false; }
    int h4_vote = (e20>e50 && e50>e200) ? +1 : (e20<e50 && e50<e200) ? -1 : 0;
    if(h4_vote != dir_want) return false;

    // H1: MACD hist rising (bull) or falling (bear)
    // M30: price vs EMA20 + RSI in 45-70 (bull) or 30-55 (bear)
    reason = "PASS";
    return true;
}
```

## 7. `TryEntry()` — four-filter funnel

Order matters: cheap filters first, expensive ones last. Log the first reject reason via `DBG()`.

```mql5
void TryEntry(int rates_total, const double &close[])
{
    if(!SessionOK())                                return;
    if(!NewsWindowOK())                             return;
    if(DailyLossKillHit())                          return;
    if(CountOpenForSym() >= InpMaxOpenPerSym)       return;
    if(TimeCurrent() - g_last_entry < InpCooldownSecs) return;

    ConfSet c;
    if(!FillConfirmations(rates_total, close, c, 1)) return;
    if(!SpreadOK(c.atr)) return;
    if(c.trend_dir == 0 || c.agreed < 3) return;

    if(InpUseHTFGate)
    {
        string why;
        if(!CheckHTFGate(c.trend_dir, why)) { DBG("HTF BLOCK: "+why); return; }
    }

    if(InpUseAIGate)
    {
        string ai_dir; double ai_conf;
        int rc = ReadAIGate(ai_dir, ai_conf);
        if(rc == 0)
        {
            string want = c.trend_dir == 1 ? "BUY" : "SELL";
            if(ai_dir != want || ai_conf < 0.55) return;
        }
        else if(InpAIRequired) return;
    }

    // Size, SL/TP, send
    double px = (c.trend_dir == 1) ? Ask() : Bid();
    double sl = px + (c.trend_dir == 1 ? -1 : +1) * InpSL_AtrMult * c.atr;
    double tp = px + (c.trend_dir == 1 ? +1 : -1) * InpTP_AtrMult * c.atr;
    double lots = ComputeLot(MathAbs(px - sl));
    TrySendOrder(c.trend_dir, px, sl, tp, lots);
}
```

## 8. Chart visuals — one-file overlay suite

Namespace every drawing with a prefix constant so `ObjectsDeleteAll(0, PFX)` never nukes user drawings.

```mql5
#define PFX "TMv14_"

void DrawIndicatorLines()
{
    DeleteTrendWithPrefix(PFX);
    if(InpShowEMAs)        DrawPolyline(h_ema_f, PFX+"ema_f", InpColEMAFast);
    if(InpShowBB)          { DrawPolyline(h_bb, 1, PFX+"bbu", InpColBBUpper); }
    if(InpShowSuperTrend)  DrawSTPolyline(...);
    if(InpShowArrows)      { /* scan bars for 3/3 fires, place OBJ_ARROW_BUY/SELL */ }
    if(InpShowSLTPLines)   DrawSLTPLines();
}

void OnTimer()
{
    // ... dashboard text refresh ...
    DrawIndicatorLines();
    ChartRedraw(0);
}
```

Objects used: `OBJ_LABEL`, `OBJ_TREND` (segments), `OBJ_ARROW_BUY/SELL`, `OBJ_HLINE`. Set `OBJPROP_BACK=true` on indicators so price draws on top.

## 9. Compile via CLI — no IDE needed

```bat
@echo off
set SRC="C:\Users\Ratanshila\Documents\autmated trading\AI_SUPERBB_v14_TrendMaster.mq5"
set DST="C:\Users\...\MQL5\Experts\AI_SUPERBB_v14_TrendMaster.mq5"
set LOG="C:\Users\...\MQL5\Experts\AI_SUPERBB_v14_TrendMaster.log"
copy /Y %SRC% %DST%
"C:\Program Files\MetaTrader 5\metaeditor64.exe" /compile:%DST% /log:%LOG%
REM log is UTF-16 LE BOM — read with encoding='utf-16'
```

Exit code `1` can mean success-with-warnings *or* error; always inspect the log text ("Result: 0 errors, 0 warnings").

## 10. Operational gotchas

- **UTF-16 everywhere.** `.chr`, `.log`, and the daily MT5 log are UTF-16 LE BOM. Open with `encoding="utf-16"` or strip BOM + decode manually.
- **EA hot-reload is not automatic.** Recompile → either toggle EA off/on in MT5, or restart MT5.
- **Chart period `period` vs `period_size`.** MT5 reads both; set both or the period won't stick after restart.
- **`iADX` buffer 0 is ADX line**, 1 is `+DI`, 2 is `-DI`.
- **`iMACD` buffer 0 is MACD line**, 1 is signal; compute histogram as `line - signal` yourself.
- **`iBands` buffer 0 is middle**, 1 is upper, 2 is lower.
- **`OBJ_ARROW_BUY/SELL` anchor is OBJPROP_ANCHOR** — set `ANCHOR_TOP` / `ANCHOR_BOTTOM` explicitly.

## References — public MQL5/MT5 resources

- `MetaQuotes-MQL5/Samples` — official EA examples (breakout, grid; martingale anti-patterns to avoid)
- `daniellfq/MQL5-TradeUtils` — CTrade wrappers for quick scaffolding
- `PerqinMT/MQL5-Utility-Kit` — chart object helpers
- `MQL5.community` forum — indicator-buffer-index lookup tables

## Workflow when extending an EA

1. Decide where the new logic fits: pre-entry filter, entry rule, exit rule, visual, or a new filter group.
2. Add inputs in the right group; default OFF so existing behavior is preserved until user opts in.
3. Allocate any new handles in `OnInit` guarded by the input flag.
4. Wire the new check into `TryEntry` in priority order (cheap → expensive).
5. Add `DBG("<feature> BLOCK: <reason>")` so rejections are auditable.
6. Recompile via CLI, inspect UTF-16 log, verify `.ex5` size grew sensibly.
7. Restart MT5 (or toggle EA) so the new binary loads.
8. Watch MT5 log tail for the new `DBG` lines to confirm the filter fires.
