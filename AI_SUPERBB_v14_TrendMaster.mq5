//+------------------------------------------------------------------+
//|  AI_SUPERBB_v14_TrendMaster.mq5                                  |
//|  M5 Trend-Master EA — catches M5 trend, rides it for max profit  |
//|                                                                  |
//|  ENTRY (3-of-3 mandatory confirmations + optional AI gate):      |
//|    C1  TREND : SuperTrend(10, 3.0) direction aligned with        |
//|                 EMA20 > EMA50 > EMA200 (bull) / vice versa.      |
//|                 ADX(14) >= 22. Price on correct side of EMA50.   |
//|    C2  VOLA  : Bollinger(20, 2.0) — price closes above BB mid    |
//|                 for long, below BB mid for short, AND BB width   |
//|                 is above its 50-bar median (trend, not squeeze). |
//|    C3  MOMO  : MACD(12,26,9) histogram rising for long (current  |
//|                 hist > prev hist) with hist > 0 OR positive      |
//|                 MACD line cross; symmetric for short.            |
//|    AI (opt.) : Python brain writes signals.json. If file exists  |
//|                 and disagrees, trade is skipped. If missing,     |
//|                 EA runs standalone.                              |
//|                                                                  |
//|  EXIT / MANAGEMENT (adaptive, scales with volatility):           |
//|    SL  = 1.5 x ATR(14)  (floored at broker min stop + buffer)    |
//|    TP  = 3.0 x ATR      (base 1:2 RR)                            |
//|    +1R : close 40%  + shift SL to break-even + 1 pip             |
//|    +2R : close 30%  + shift SL to +1R lock                       |
//|    RUN : chandelier trail — HH(last 10) - 2x ATR (symmetric)     |
//|                                                                  |
//|  MILLISECOND LAYER:                                              |
//|    OnTick() uses GetMicrosecondCount() so management runs on     |
//|    every tick, not every bar. Entry signals still gate on        |
//|    bar close (avoids repainting). Partial close / trail / BE     |
//|    / emergency exit all react tick-by-tick.                      |
//|                                                                  |
//|  RISK:                                                           |
//|    1% default account risk per trade. Adaptive mode scales       |
//|    size with recent win-rate (Kelly-fraction, capped at 2%).     |
//|    Max 1 open position per symbol, max daily loss -3%.           |
//+------------------------------------------------------------------+
#property copyright "AI Trading Agents — TrendMaster v14.0"
#property link      ""
#property version   "14.00"
#property description "M5 Trend-Master: 3-confirmation entry, adaptive trailing, tick-level mgmt, optional AI gate"
#property strict

#include <Trade/Trade.mqh>
#include <Trade/PositionInfo.mqh>
#include <Trade/SymbolInfo.mqh>

CTrade         Trade;
CPositionInfo  Pos;
CSymbolInfo    Sym;

//====================================================================
//  INPUTS
//====================================================================
input group "=== GENERAL ==="
input long    InpMagic          = 20260420;   // Magic number
input string  InpComment        = "TrendMasterV14";
input bool    InpAllowLong      = true;
input bool    InpAllowShort     = true;
input bool    InpPrintDebug     = true;

input group "=== RISK / SIZING ==="
// [audit-fix 2026-04-22] InpRiskPct here is INDEPENDENT of config/settings.py
// RISK.risk_percent on the Python side. Python brain sizes Python-side risk
// decisions; this value only governs EA-side sizing. Keep them in sync
// manually until a shared config is introduced.
input double  InpRiskPct        = 1.0;        // Risk per trade (%)
input bool    InpAdaptiveSize   = true;       // Kelly-scaled sizing
input double  InpMaxRiskPct     = 2.0;        // Hard cap when adaptive
input double  InpMaxDailyLossPc = 3.0;        // Daily loss kill-switch (%)
input int     InpMaxOpenPerSym  = 1;
input double  InpMinLot         = 0.01;
input double  InpMaxLot         = 5.00;

input group "=== CONFIRMATION LAYER ==="
input int     InpST_Period      = 10;         // SuperTrend ATR period
input double  InpST_Mult        = 3.0;        // SuperTrend ATR multiplier
input int     InpEMA_Fast       = 20;
input int     InpEMA_Slow       = 50;
input int     InpEMA_Trend      = 200;
input int     InpADX_Period     = 14;
input double  InpADX_Min        = 22.0;       // [R11] 40 -> 22 after zero-trades audit; per-pair override via signal JSON
input int     InpBB_Period      = 20;
input double  InpBB_Dev         = 2.0;
input int     InpMACD_Fast      = 12;
input int     InpMACD_Slow      = 26;
input int     InpMACD_Sig       = 9;
input int     InpATR_Period     = 14;
input bool    InpRequireAll3    = false;      // [R11] true -> false: 2-of-3 OK (overnight 3/3 rare)

input group "=== EXIT / MANAGEMENT ==="
// [R7 2026-04-23] 1:3 RR sustainable mode. Backtest on 50K bars XAUUSD M5
// proved that 80% WR @ 1:3 RR is NOT achievable with technical filters
// on real data (trader's triangle math). Best 1:3 config:
//   ADX40 filter + SL 1.0 / TP 3.0 = 32.5% WR, +0.266 exp/trade, +78R total.
// Every filter that boosts WR on 1:3 RR made the strategy LOSE money
// because filtering reduced edge more than it reduced loss count.
// This config is PROFITABLE 1:3 mode with 295 trades on 50K bars.
// Accept the 32.5% WR — math shows it's profitable via the 3:1 payoff.
// Previous 80%+ WR experiment (4.0/1.0) moved to archive.
input double  InpSL_AtrMult     = 1.0;
input double  InpTP_AtrMult     = 3.0;        // Base TP — true 1:3 RR
input bool    InpUsePartial1    = true;       // +1R close 40% + BE
input bool    InpUsePartial2    = true;       // +2R close 30% + lock +1R
input double  InpPartial1Pct    = 0.40;
input double  InpPartial2Pct    = 0.30;
input bool    InpUseChandelier  = true;       // Trailing for runner
input int     InpChandelierLook = 10;
input double  InpChandelierAtr  = 2.0;
input double  InpBeBufferAtr    = 0.10;       // Break-even buffer (x ATR)
input bool    InpUsePyramid       = true;     // add-on tranche at +1R
input double  InpPyramidR         = 1.0;      // R-multiple trigger for pyramid
input double  InpPyramidSizePct   = 0.5;      // size as fraction of ORIGINAL lots
input bool    InpPyramidNeedTrend = true;     // require SuperTrend still favorable

input group "=== AI / PYTHON GATE ==="
input bool    InpUseAIGate      = true;       // Read signals.json?
input string  InpAISignalFile   = "trendmaster_signals.json";
input bool    InpAIAutoPerSymbol = true;      // Auto-derive signal filename from _Symbol (multi-symbol mode)
input string  InpAIPrimarySymbol = "XAUUSD";  // Primary symbol that keeps the legacy signal filename
input int     InpAIStaleSecs    = 60;         // Skip AI if older than N sec
input bool    InpAIRequired     = false;      // true = no AI, no trade

input group "=== HTF GATE (M30 + H1 + H4 alignment) ==="
input bool    InpUseHTFGate     = true;        // Require HTF trend + momentum alignment
input ENUM_TIMEFRAMES InpHTFTrendTF    = PERIOD_H4;  // Trend context TF
input ENUM_TIMEFRAMES InpHTFMomentumTF = PERIOD_H1;  // Momentum context TF
input ENUM_TIMEFRAMES InpHTFTimingTF   = PERIOD_M30; // Entry-timing TF
input int     InpHTF_EMA_Fast   = 20;
input int     InpHTF_EMA_Slow   = 50;
input int     InpHTF_EMA_Trend  = 200;
input int     InpHTF_ADX_Period = 14;
input double  InpHTF_ADX_Min    = 20.0;        // Trend strength gate on H4
input int     InpHTF_RSI_Period = 14;
input int     InpHTF_MACD_Fast  = 12;
input int     InpHTF_MACD_Slow  = 26;
input int     InpHTF_MACD_Sig   = 9;

input group "=== TIMING / SESSIONS ==="
input bool    InpUseSessionFilt = true;
input int     InpLondonStartUtc = 7;
input int     InpNYEndUtc       = 20;
input int     InpCooldownSecs   = 90;         // Between entries
input bool    InpBlockNewsWin   = false;      // [2026-04-28] DISABLED — :55-:05 proxy was structurally blocking every H1-bar entry (bar close lands at :00 ≤ :05). Brain's profit_filters.news_blackout uses real calendar; EA proxy was redundant.

input group "=== SAFETY ==="
input double  InpMaxSpreadAtrPc = 0.40;       // [R11] 0.20 -> 0.40: overnight spreads blocked every pair
input int     InpSlippagePts    = 20;

// [R5 2026-04-23] Auto-attach MT5 built-in indicators on OnInit(). No
// more invisible polyline objects — these appear as proper chart
// indicators (thick visible lines, right-axis labels, tooltips).
input bool    InpAutoAddStdIndicators = true;  // Auto-add MT5 native BB/EMA/MACD/RSI/ADX on init

input group "=== VISUAL (chart overlays) ==="
input bool    InpShowEMAs        = true;      // Draw EMA20 / EMA50 / EMA200
input bool    InpShowBB          = true;      // Draw Bollinger upper/mid/lower
input bool    InpShowSuperTrend  = true;      // Draw SuperTrend line (color = direction)
input bool    InpShowArrows      = true;      // Draw BUY / SELL arrows at 3/3 bars
input bool    InpShowSLTPLines   = true;      // Draw SL/TP H-lines on open positions
input int     InpDrawBars        = 300;       // How many bars of history to draw
input color   InpColEMAFast      = clrGold;
input color   InpColEMASlow      = clrDodgerBlue;
input color   InpColEMATrend     = clrMagenta;
input color   InpColBBUpper      = clrDeepSkyBlue;
input color   InpColBBMid        = clrDimGray;
input color   InpColBBLower      = clrDeepSkyBlue;
input color   InpColSTUp         = clrLime;
input color   InpColSTDown       = clrRed;
input color   InpColArrowBuy     = clrLime;
input color   InpColArrowSell    = clrRed;

//====================================================================
//  STATE
//====================================================================
int    h_st_atr, h_ema_f, h_ema_s, h_ema_t;
int    h_adx, h_bb, h_macd, h_atr;
// HTF gate handles
int    h_htf_ema_f = INVALID_HANDLE, h_htf_ema_s = INVALID_HANDLE, h_htf_ema_t = INVALID_HANDLE;
int    h_htf_adx   = INVALID_HANDLE;
int    h_h1_macd   = INVALID_HANDLE;
int    h_m30_ema_f = INVALID_HANDLE, h_m30_rsi = INVALID_HANDLE;

datetime g_last_bar      = 0;
datetime g_last_entry    = 0;
datetime g_day_start     = 0;
double   g_day_start_bal = 0.0;
ulong    g_last_tick_us  = 0;

// SuperTrend state (hand-computed — MT5 has no native ST)
double g_st_line[];     // SuperTrend line value per bar
int    g_st_dir[];      // +1 up / -1 down
int    g_st_size = 0;

// Trade-level state tracked on positions (via PositionGetString COMMENT tag)
struct TradeFlags
{
    ulong  ticket;
    bool   p1_done;      // +1R partial done?
    bool   p2_done;      // +2R partial done?
    bool   be_done;      // break-even shift done?
    bool   lock1r_done;  // +1R lock done?
    bool   pyramid_done; // true once pyramid tranche was opened for this ticket
    ulong  pyramid_ticket; // ticket of the add-on position, 0 if none
    double initial_sl;
    double initial_risk; // price distance of initial SL
};
TradeFlags g_flags[];

// Rolling win/loss memory for Kelly sizing
int    g_wins    = 0;
int    g_losses  = 0;
double g_avgWinR = 1.5;
double g_avgLossR= 1.0;

#define PFX "TMV14_"

//====================================================================
//  UTIL
//====================================================================
void DBG(string s){ if(InpPrintDebug) Print("[TMv14] ", s); }

// BLK() — block-reason logging that ALWAYS prints (independent of
// InpPrintDebug) but is rate-limited per reason so a long flat market
// doesn't fill the Experts log. Added 2026-04-22. Use for any "we
// would have entered but..." path so the user can answer "why isn't
// my EA trading?" by glancing at the Experts tab.
datetime g_blk_last[16];
string   g_blk_key [16];
int      g_blk_n = 0;
void BLK(string reason, string key)
{
    int slot = -1;
    for(int i = 0; i < g_blk_n; i++)
        if(g_blk_key[i] == key){ slot = i; break; }
    datetime now = TimeCurrent();
    if(slot >= 0 && (now - g_blk_last[slot]) < 60) return; // 60s dedup
    if(slot < 0)
    {
        if(g_blk_n < 16){ slot = g_blk_n; g_blk_n++; g_blk_key[slot] = key; }
        else { slot = 0; g_blk_key[slot] = key; } // overwrite oldest slot
    }
    g_blk_last[slot] = now;
    Print("[TMv14 BLOCK] ", reason);
}

double NP(double price){ return NormalizeDouble(price, _Digits); }

double PointVal(){ return SymbolInfoDouble(_Symbol, SYMBOL_POINT); }

double GetPipSize()
{
    // Gold / silver / indices: treat "pip" as point*10 for most
    string sym = _Symbol;
    if(StringFind(sym, "XAU") >= 0 || StringFind(sym, "GOLD") >= 0) return 0.10;
    if(StringFind(sym, "XAG") >= 0 || StringFind(sym, "SILVER")>= 0) return 0.01;
    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    if(digits == 3 || digits == 5) return PointVal() * 10.0;
    return PointVal();
}

double MinStopDistance()
{
    int stop_lvl = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
    return (stop_lvl + 5) * PointVal();   // +5 point safety
}

//--- cache safe copy buffer
bool CopyOne(int h, int bufIdx, int shift, double &out)
{
    double b[1];
    if(CopyBuffer(h, bufIdx, shift, 1, b) < 1) return false;
    out = b[0];
    return true;
}

//====================================================================
//  SUPERTREND (hand-rolled, non-repainting on closed bars)
//====================================================================
void EnsureSuperTrend(int rates_total, const double &high[], const double &low[],
                     const double &close[], const datetime &time[])
{
    if(rates_total < InpST_Period + 5) return;

    // resize arrays
    if(g_st_size != rates_total)
    {
        ArrayResize(g_st_line, rates_total);
        ArrayResize(g_st_dir,  rates_total);
        g_st_size = rates_total;
        // Force full recompute
        for(int i = 0; i < rates_total; ++i){ g_st_line[i] = 0.0; g_st_dir[i] = 0; }
    }

    // Work from oldest to newest (series arrays have index 0 = newest after AsSeries=true)
    // We'll use non-series logic: iterate normal array order.
    // Because OnCalculate gave us AsSeries(true), we index with (rates_total - 1 - k).
    // It's easier to convert into chronological index ci = rates_total - 1 - i where i series.

    // Precompute ATR via handle
    double atrSer[];
    ArraySetAsSeries(atrSer, true);
    if(CopyBuffer(h_st_atr, 0, 0, rates_total, atrSer) < rates_total) return;

    // Find first chronological index we still need to compute.
    // Simple approach: recompute last 400 bars each time — cheap.
    int back = MathMin(400, rates_total - 2);
    int start_chrono = rates_total - 1 - back;
    if(start_chrono < InpST_Period + 1) start_chrono = InpST_Period + 1;

    for(int ci = start_chrono; ci <= rates_total - 1; ++ci)
    {
        int ser = rates_total - 1 - ci;             // series idx
        if(ser < 0) continue;
        double hp = high[ser], lp = low[ser], cp = close[ser];
        double atr = atrSer[ser];
        if(atr <= 0) continue;

        double hl2 = (hp + lp) / 2.0;
        double st_mult_eff = EffectiveSTMult();
        double upperBasic = hl2 + st_mult_eff * atr;
        double lowerBasic = hl2 - st_mult_eff * atr;

        // final upper/lower
        double prevUpper = (ci > 0 && g_st_dir[ci-1] != 0) ? g_st_line[ci-1] : upperBasic;
        double prevLower = (ci > 0 && g_st_dir[ci-1] != 0) ? g_st_line[ci-1] : lowerBasic;
        double prevClose = 0.0;
        if(ci - 1 >= 0)
        {
            int pser = rates_total - 1 - (ci - 1);
            if(pser >= 0 && pser < rates_total) prevClose = close[pser];
        }

        double upperFinal = (upperBasic < prevUpper || prevClose > prevUpper) ? upperBasic : prevUpper;
        double lowerFinal = (lowerBasic > prevLower || prevClose < prevLower) ? lowerBasic : prevLower;

        int prevDir = (ci > 0) ? g_st_dir[ci-1] : 1;
        int dir;
        double stLine;

        if(prevDir == 1)
        {
            if(cp < lowerFinal) { dir = -1; stLine = upperFinal; }
            else                { dir =  1; stLine = lowerFinal; }
        }
        else
        {
            if(cp > upperFinal) { dir =  1; stLine = lowerFinal; }
            else                { dir = -1; stLine = upperFinal; }
        }

        g_st_line[ci] = stLine;
        g_st_dir[ci]  = dir;
    }
}

int SuperTrendDirAt(int seriesShift, int rates_total)
{
    int ci = rates_total - 1 - seriesShift;
    if(ci < 0 || ci >= g_st_size) return 0;
    return g_st_dir[ci];
}

double SuperTrendLineAt(int seriesShift, int rates_total)
{
    int ci = rates_total - 1 - seriesShift;
    if(ci < 0 || ci >= g_st_size) return 0;
    return g_st_line[ci];
}

// Returns true when the latest completed bar's SuperTrend direction agrees
// with `dir` (+1 BUY / -1 SELL). Safe to call from any context once
// EnsureSuperTrend has populated g_st_dir at least once. On warm-up / empty
// buffer, fails OPEN (returns true) so we don't block pyramid unnecessarily.
bool SuperTrendAgrees(int dir)
{
    if(g_st_size <= 1) return true;
    // Use shift=1 (last closed bar) to match entry-side convention.
    int ci = g_st_size - 1 - 1;
    if(ci < 0 || ci >= g_st_size) return true;
    int st = g_st_dir[ci];
    if(st == 0) return true;
    return (st == dir);
}

//====================================================================
//  CONFIRMATIONS
//====================================================================
struct ConfSet
{
    int  trend_dir;     // +1 / -1 / 0
    bool c1_trend;
    bool c2_vola;
    bool c3_momo;
    int  agreed;        // count
    double atr;
    double ema_fast, ema_slow, ema_trend;
    double adx;
    double bb_upper, bb_mid, bb_lower, bb_width_med;
    double macd_main, macd_sig, macd_hist, macd_hist_prev;
    double st_line;
    int    st_dir;
};

bool FillConfirmations(int rates_total, const double &close[], ConfSet &c, int shift = 1)
{
    // shift = 1 means last closed bar
    c.trend_dir = 0;
    c.c1_trend = c.c2_vola = c.c3_momo = false;
    c.agreed = 0;

    double atr, eF, eS, eT, adx;
    double bbU, bbM, bbL;
    double macd_m_now, macd_m_prev, macd_s_now;
    if(!CopyOne(h_atr,   0, shift,     atr))         return false;
    if(!CopyOne(h_ema_f, 0, shift,     eF))          return false;
    if(!CopyOne(h_ema_s, 0, shift,     eS))          return false;
    if(!CopyOne(h_ema_t, 0, shift,     eT))          return false;
    if(!CopyOne(h_adx,   0, shift,     adx))         return false;
    if(!CopyOne(h_bb,    1, shift,     bbU))         return false;
    if(!CopyOne(h_bb,    0, shift,     bbM))         return false;
    if(!CopyOne(h_bb,    2, shift,     bbL))         return false;
    if(!CopyOne(h_macd,  0, shift,     macd_m_now))  return false;
    if(!CopyOne(h_macd,  0, shift + 1, macd_m_prev)) return false;
    if(!CopyOne(h_macd,  1, shift,     macd_s_now))  return false;

    // BB width median over last 50 bars
    double bbu_buf[50], bbl_buf[50];
    if(CopyBuffer(h_bb, 1, shift, 50, bbu_buf) < 50) return false;
    if(CopyBuffer(h_bb, 2, shift, 50, bbl_buf) < 50) return false;
    double widths[50];
    for(int i = 0; i < 50; ++i) widths[i] = bbu_buf[i] - bbl_buf[i];
    ArraySort(widths);
    double width_med = widths[25];

    c.atr          = atr;
    c.ema_fast     = eF;
    c.ema_slow     = eS;
    c.ema_trend    = eT;
    c.adx          = adx;
    c.bb_upper     = bbU;
    c.bb_mid       = bbM;
    c.bb_lower     = bbL;
    c.bb_width_med = width_med;
    c.macd_main    = macd_m_now;
    c.macd_sig     = macd_s_now;
    c.macd_hist    = macd_m_now - macd_s_now;
    {
        double macd_s_prev;
        if(!CopyOne(h_macd, 1, shift + 1, macd_s_prev)) return false;
        c.macd_hist_prev = macd_m_prev - macd_s_prev;
    }

    double px  = close[shift];
    c.st_dir   = SuperTrendDirAt(shift, rates_total);
    c.st_line  = SuperTrendLineAt(shift, rates_total);

    // ── C1 TREND ────────────────────────────────────────────────
    bool ema_bull = (eF > eS) && (eS > eT);
    bool ema_bear = (eF < eS) && (eS < eT);
    bool adx_ok   = adx >= InpADX_Min;
    bool st_bull  = (c.st_dir ==  1);
    bool st_bear  = (c.st_dir == -1);

    if(ema_bull && st_bull && adx_ok && px > eS) { c.c1_trend = true; c.trend_dir =  1; }
    if(ema_bear && st_bear && adx_ok && px < eS) { c.c1_trend = true; c.trend_dir = -1; }

    // ── C2 VOLATILITY (BB context) ──────────────────────────────
    double bb_width_now = bbU - bbL;
    bool width_ok = bb_width_now >= width_med * EffectiveBBFloorPct();   // [v14.5] per-team override via signal JSON
    if(c.trend_dir == 1)
    {
        if(px > bbM && width_ok) c.c2_vola = true;
    }
    else if(c.trend_dir == -1)
    {
        if(px < bbM && width_ok) c.c2_vola = true;
    }

    // ── C3 MOMENTUM (MACD) ──────────────────────────────────────
    bool hist_up   = c.macd_hist > c.macd_hist_prev && c.macd_hist > 0;
    bool hist_dn   = c.macd_hist < c.macd_hist_prev && c.macd_hist < 0;
    bool macd_up   = c.macd_main > c.macd_sig && c.macd_main > 0;
    bool macd_dn   = c.macd_main < c.macd_sig && c.macd_main < 0;

    if(c.trend_dir ==  1 && (hist_up || macd_up)) c.c3_momo = true;
    if(c.trend_dir == -1 && (hist_dn || macd_dn)) c.c3_momo = true;

    c.agreed = (c.c1_trend?1:0) + (c.c2_vola?1:0) + (c.c3_momo?1:0);
    return true;
}

//====================================================================
//  AI GATE (reads JSON written by Python brain)
//====================================================================
// Resolve the per-symbol signal filename. The Python brain now writes
// per-symbol files (e.g. trendmaster_signals_GBPJPY.json) for non-primary
// symbols, while the primary symbol keeps the legacy filename. This helper
// lets a single EA binary work correctly across multiple charts/symbols.
string ResolveAISignalFile()
{
    if(!InpAIAutoPerSymbol) return InpAISignalFile;
    if(_Symbol == InpAIPrimarySymbol) return InpAISignalFile;
    string stem   = InpAISignalFile;
    string suffix = "";
    int dot = StringFind(InpAISignalFile, ".json");
    if(dot >= 0)
    {
        stem   = StringSubstr(InpAISignalFile, 0, dot);
        suffix = StringSubstr(InpAISignalFile, dot);
    }
    return StringFormat("%s_%s%s", stem, _Symbol, suffix);
}

// [R8 2026-04-23] Globals populated by ReadAIGate — per-symbol SL/TP/ADX
// overrides from the signal file. The order-placement + entry-filter
// paths consult these via the PairSL/PairTP/PairADX() helpers below.
double   g_ai_sl_atr_mult   = 0.0;
double   g_ai_tp_atr_mult   = 0.0;
double   g_ai_adx_min       = 0.0;
// [R11 2026-04-23] Runtime override for require_all_3 (3-vote strictness)
// and max_spread_atr_pct (spread cap). Brain writes these in the per-symbol
// signal JSON so we don't need to re-attach the EA on 18 charts every time
// gating policy changes. -1 (int) or 0.0 (double) = "not provided, fall back
// to Inp*".
int      g_ai_require_all_3     = -1;   // -1 = not set; 0 = false; 1 = true
double   g_ai_max_spread_atr_pc = 0.0;  // 0 = not set
// [v14.5 2026-04-25] Per-team SuperTrend mult + BB width floor pct.
// Brain writes from team_params.py TEAM_PARAMS[team]. 0 = not provided.
double   g_ai_st_mult           = 0.0;
double   g_ai_bb_floor_pct      = 0.0;

double EffectiveSLAtrMult() { return g_ai_sl_atr_mult > 0 ? g_ai_sl_atr_mult : InpSL_AtrMult; }
double EffectiveTPAtrMult() { return g_ai_tp_atr_mult > 0 ? g_ai_tp_atr_mult : InpTP_AtrMult; }
double EffectiveADXMin()    { return g_ai_adx_min     > 0 ? g_ai_adx_min     : InpADX_Min;    }
bool   EffectiveRequireAll3()     { return g_ai_require_all_3 >= 0 ? (g_ai_require_all_3 > 0) : InpRequireAll3; }
double EffectiveMaxSpreadAtrPct() { return g_ai_max_spread_atr_pc > 0 ? g_ai_max_spread_atr_pc : InpMaxSpreadAtrPc; }
double EffectiveSTMult()     { return g_ai_st_mult       > 0 ? g_ai_st_mult       : InpST_Mult; }
double EffectiveBBFloorPct() { return g_ai_bb_floor_pct  > 0 ? g_ai_bb_floor_pct  : 0.9;        }


// File format (kept intentionally simple — parse manually, no json lib):
//   {"direction":"BUY","confidence":0.73,"ts":1712345678,"symbol":"XAUUSD",
//    "sl_atr_mult":1.5,"tp_atr_mult":3.0,"adx_min":30}
int ReadAIGate(string &direction, double &conf)
{
    direction = "NONE"; conf = 0.0;
    // Reset per-symbol overrides — if the signal file doesn't include
    // them we fall back to the EA's input defaults via Effective* helpers.
    g_ai_sl_atr_mult = 0.0;
    g_ai_tp_atr_mult = 0.0;
    g_ai_adx_min     = 0.0;
    g_ai_require_all_3     = -1;
    g_ai_max_spread_atr_pc = 0.0;
    g_ai_st_mult           = 0.0;
    g_ai_bb_floor_pct      = 0.0;
    int fh = FileOpen(ResolveAISignalFile(), FILE_READ | FILE_TXT | FILE_ANSI);
    if(fh == INVALID_HANDLE)
    {
        fh = FileOpen(ResolveAISignalFile(), FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
        if(fh == INVALID_HANDLE) return -1;  // no file
    }
    string all = "";
    while(!FileIsEnding(fh)) all += FileReadString(fh);
    FileClose(fh);

    // Direction
    int p = StringFind(all, "\"direction\"");
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int q1 = StringFind(all, "\"", colon + 1);
        int q2 = StringFind(all, "\"", q1 + 1);
        if(q1 > 0 && q2 > q1) direction = StringSubstr(all, q1 + 1, q2 - q1 - 1);
    }
    // Confidence
    p = StringFind(all, "\"confidence\"");
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int comma = StringFind(all, ",", colon);
        if(comma < 0) comma = StringFind(all, "}", colon);
        string num = StringSubstr(all, colon + 1, comma - colon - 1);
        conf = StringToDouble(num);
    }
    // Timestamp
    p = StringFind(all, "\"ts\"");
    long ts = 0;
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int comma = StringFind(all, ",", colon);
        if(comma < 0) comma = StringFind(all, "}", colon);
        string num = StringSubstr(all, colon + 1, comma - colon - 1);
        ts = (long)StringToInteger(num);
    }

    // [R8 2026-04-23] Per-symbol sl_atr_mult / tp_atr_mult / adx_min
    // overrides (brain writes these when pair_params.py has an entry).
    p = StringFind(all, "\"sl_atr_mult\"");
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int comma = StringFind(all, ",", colon);
        if(comma < 0) comma = StringFind(all, "}", colon);
        string num = StringSubstr(all, colon + 1, comma - colon - 1);
        g_ai_sl_atr_mult = StringToDouble(num);
    }
    p = StringFind(all, "\"tp_atr_mult\"");
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int comma = StringFind(all, ",", colon);
        if(comma < 0) comma = StringFind(all, "}", colon);
        string num = StringSubstr(all, colon + 1, comma - colon - 1);
        g_ai_tp_atr_mult = StringToDouble(num);
    }
    p = StringFind(all, "\"adx_min\"");
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int comma = StringFind(all, ",", colon);
        if(comma < 0) comma = StringFind(all, "}", colon);
        string num = StringSubstr(all, colon + 1, comma - colon - 1);
        g_ai_adx_min = StringToDouble(num);
    }

    // [R11 2026-04-23] Runtime gate policy overrides — avoids re-attaching
    // the EA on every chart when we tune strictness.
    p = StringFind(all, "\"require_all_3\"");
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int comma = StringFind(all, ",", colon);
        if(comma < 0) comma = StringFind(all, "}", colon);
        string num = StringSubstr(all, colon + 1, comma - colon - 1);
        StringTrimLeft(num); StringTrimRight(num);
        // Accept true/false or 0/1
        if(StringFind(num, "true")  >= 0) g_ai_require_all_3 = 1;
        else if(StringFind(num, "false") >= 0) g_ai_require_all_3 = 0;
        else g_ai_require_all_3 = (int)StringToInteger(num);
    }
    p = StringFind(all, "\"max_spread_atr_pct\"");
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int comma = StringFind(all, ",", colon);
        if(comma < 0) comma = StringFind(all, "}", colon);
        string num = StringSubstr(all, colon + 1, comma - colon - 1);
        g_ai_max_spread_atr_pc = StringToDouble(num);
    }

    // [v14.5 2026-04-25] Per-team SuperTrend mult (st_mult) and BB-width
    // floor (bb_width_floor_pct) overrides. Brain reads from team_params.py
    // TEAM_PARAMS[team] and writes into the per-symbol signal JSON. 0 = not
    // provided => fall back to compiled InpST_Mult / 0.9 default.
    p = StringFind(all, "\"st_mult\"");
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int comma = StringFind(all, ",", colon);
        if(comma < 0) comma = StringFind(all, "}", colon);
        string num = StringSubstr(all, colon + 1, comma - colon - 1);
        g_ai_st_mult = StringToDouble(num);
    }
    p = StringFind(all, "\"bb_width_floor_pct\"");
    if(p >= 0)
    {
        int colon = StringFind(all, ":", p);
        int comma = StringFind(all, ",", colon);
        if(comma < 0) comma = StringFind(all, "}", colon);
        string num = StringSubstr(all, colon + 1, comma - colon - 1);
        g_ai_bb_floor_pct = StringToDouble(num);
    }

    // Stale check
    // [audit-fix 2026-04-22] boundary: age == InpAIStaleSecs is already stale;
    // switched > to >= so a signal exactly at the cap is rejected, not kept.
    if(ts > 0 && TimeCurrent() - (datetime)ts >= InpAIStaleSecs)
    {
        BLK(StringFormat("AI gate stale: age=%d s (cap %d s)",
                         (int)(TimeCurrent() - (datetime)ts), (int)InpAIStaleSecs),
            "ai_age");
        return -2;
    }
    return 0;
}

//====================================================================
//  SESSION / NEWS / SPREAD FILTERS
//====================================================================
bool SessionOK()
{
    if(!InpUseSessionFilt) return true;
    MqlDateTime dt;
    TimeToStruct(TimeCurrent(), dt);
    int h = dt.hour;
    return (h >= InpLondonStartUtc && h < InpNYEndUtc);
}

bool NewsWindowOK()
{
    if(!InpBlockNewsWin) return true;
    MqlDateTime dt;
    TimeToStruct(TimeCurrent(), dt);
    // skip :55-:05 around each hour as a cheap proxy (real news calendar via Python brain)
    return !(dt.min >= 55 || dt.min <= 5);
}

bool SpreadOK(double atr)
{
    if(atr <= 0) return true;
    double sp_pts  = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
    double sp_pr   = sp_pts * PointVal();
    double ratio   = sp_pr / atr;
    double cap = EffectiveMaxSpreadAtrPct();
    if(ratio > cap)
    {
        BLK(StringFormat("Spread/ATR %.1f%% > %.1f%% cap",
                         ratio * 100.0, cap * 100.0), "spread");
        return false;
    }
    return true;
}

//====================================================================
//  RISK / SIZING
//====================================================================
double KellyFraction()
{
    int total = g_wins + g_losses;
    if(total < 10) return 1.0;                    // not enough data
    double p = (double)g_wins / total;
    double b = (g_avgLossR > 0) ? (g_avgWinR / g_avgLossR) : 1.0;
    if(b <= 0) return 1.0;
    double f = p - (1.0 - p) / b;
    if(f < 0.2) f = 0.2;
    if(f > 2.0) f = 2.0;
    return f;
}

double ComputeLot(double sl_distance_price)
{
    if(sl_distance_price <= 0) return InpMinLot;
    double eq = AccountInfoDouble(ACCOUNT_EQUITY);

    double risk_pct = InpRiskPct;
    if(InpAdaptiveSize)
    {
        risk_pct *= KellyFraction();
        if(risk_pct > InpMaxRiskPct) risk_pct = InpMaxRiskPct;
    }
    double risk_money = eq * risk_pct / 100.0;

    double tick_sz  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    if(tick_sz <= 0 || tick_val <= 0) return InpMinLot;

    double loss_per_lot = (sl_distance_price / tick_sz) * tick_val;
    if(loss_per_lot <= 0) return InpMinLot;

    double lot = risk_money / loss_per_lot;

    double step  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double minl  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxl  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    if(step > 0) lot = MathFloor(lot / step) * step;
    if(lot < minl) lot = minl;
    if(lot < InpMinLot) lot = InpMinLot;
    if(lot > MathMin(maxl, InpMaxLot)) lot = MathMin(maxl, InpMaxLot);
    return NormalizeDouble(lot, 2);
}

bool DailyLossKillHit()
{
    datetime today = (datetime)(TimeCurrent() - TimeCurrent() % 86400);
    if(g_day_start != today)
    {
        g_day_start     = today;
        g_day_start_bal = AccountInfoDouble(ACCOUNT_BALANCE);
    }
    double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
    double dd  = (g_day_start_bal - eq) / MathMax(1.0, g_day_start_bal) * 100.0;
    return dd >= InpMaxDailyLossPc;
}

//====================================================================
//  POSITION STATE LOOKUP
//====================================================================
int CountOpenForSym()
{
    int n = 0;
    for(int i = PositionsTotal() - 1; i >= 0; --i)
    {
        if(!Pos.SelectByIndex(i)) continue;
        if(Pos.Symbol()    != _Symbol)   continue;
        if(Pos.Magic()     != InpMagic)  continue;
        n++;
    }
    return n;
}

int FindFlagIdx(ulong ticket)
{
    for(int i = 0; i < ArraySize(g_flags); ++i)
        if(g_flags[i].ticket == ticket) return i;
    return -1;
}

void AddFlag(ulong ticket, double initial_sl, double initial_risk)
{
    int sz = ArraySize(g_flags);
    ArrayResize(g_flags, sz + 1);
    g_flags[sz].ticket         = ticket;
    g_flags[sz].p1_done        = false;
    g_flags[sz].p2_done        = false;
    g_flags[sz].be_done        = false;
    g_flags[sz].lock1r_done    = false;
    g_flags[sz].pyramid_done   = false;
    g_flags[sz].pyramid_ticket = 0;
    g_flags[sz].initial_sl     = initial_sl;
    g_flags[sz].initial_risk   = initial_risk;
}

void PurgeClosedFlags()
{
    for(int i = ArraySize(g_flags) - 1; i >= 0; --i)
    {
        if(!PositionSelectByTicket(g_flags[i].ticket))
            ArrayRemove(g_flags, i, 1);
    }
}

//====================================================================
//  ENTRY
//====================================================================
bool TrySendOrder(int dir, double px, double sl, double tp, double lots)
{
    // [audit-fix 2026-04-22] magic-number audit: CTrade.SetExpertMagicNumber
    // is set in OnInit and re-set here, so every Trade.Buy/Sell and every
    // subsequent Trade.PositionModify / Trade.PositionClosePartial in
    // ManagePositions carries InpMagic automatically. No per-call request
    // struct is built — the class owns it. Verified OK.
    Trade.SetExpertMagicNumber(InpMagic);
    Trade.SetDeviationInPoints(InpSlippagePts);
    string cmt = StringFormat("%s_%s", InpComment, dir == 1 ? "L" : "S");

    // [audit-fix 2026-04-22] SL/TP sanity clamp — reject if SL is on the
    // wrong side of entry (BUY SL above px / SELL SL below px) or if the
    // stop is too close to entry (< 10 points). Prevents a malformed
    // signal or an ATR hiccup from producing an instantly-triggering SL
    // or, worse, an inverted SL that would be rejected broker-side
    // after the fill.
    double min_sl_gap = _Point * 10.0;
    if(dir == 1)
    {
        if(sl >= px || (px - sl) < min_sl_gap ||
           (tp > 0.0 && tp <= px))
        {
            Print(StringFormat("[TMv14 SAFETY] BUY rejected: px=%.5f sl=%.5f tp=%.5f (sl must be < px by >= %.5f)",
                               px, sl, tp, min_sl_gap));
            return false;
        }
    }
    else
    {
        if(sl <= px || (sl - px) < min_sl_gap ||
           (tp > 0.0 && tp >= px))
        {
            Print(StringFormat("[TMv14 SAFETY] SELL rejected: px=%.5f sl=%.5f tp=%.5f (sl must be > px by >= %.5f)",
                               px, sl, tp, min_sl_gap));
            return false;
        }
    }

    bool ok = false;
    if(dir == 1)  ok = Trade.Buy (lots, _Symbol, 0.0, NP(sl), NP(tp), cmt);
    else          ok = Trade.Sell(lots, _Symbol, 0.0, NP(sl), NP(tp), cmt);

    if(!ok)
    {
        DBG(StringFormat("Order FAILED ret=%d desc=%s", Trade.ResultRetcode(), Trade.ResultComment()));
        return false;
    }
    ulong tk = Trade.ResultOrder();
    ulong pos_tk = Trade.ResultDeal();
    // Best-effort: resolve position ticket after fill
    if(PositionSelectByTicket(pos_tk)) {}
    else
    {
        // walk positions to find newest one
        for(int i = PositionsTotal() - 1; i >= 0; --i)
        {
            if(!Pos.SelectByIndex(i)) continue;
            if(Pos.Symbol() == _Symbol && Pos.Magic() == InpMagic)
            {
                pos_tk = Pos.Ticket(); break;
            }
        }
    }
    double risk = MathAbs(px - sl);
    AddFlag(pos_tk, sl, risk);
    g_last_entry = TimeCurrent();
    DBG(StringFormat("ENTRY %s lots=%.2f px=%.5f SL=%.5f TP=%.5f risk=%.5f",
                     dir==1?"BUY":"SELL", lots, px, sl, tp, risk));
    return true;
}

//====================================================================
//  HTF GATE — unanimous alignment across M30 (timing) / H1 (momentum)
//             / H4 (trend).  dir_want: +1 BUY / -1 SELL
//             reason: on non-empty failure, contains why we rejected.
//  Returns true when the gate says "go". Fails OPEN on warm-up (only
//  if handles are ready and buffers non-NaN do we actually block).
//====================================================================
bool CheckHTFGate(int dir_want, string &reason)
{
    reason = "";
    if(!InpUseHTFGate) return true;
    if(dir_want != 1 && dir_want != -1){ reason = "dir_want invalid"; return false; }

    // Handles might be INVALID during initial cold start — fail-open,
    // don't block valid setups just because H4 data hasn't arrived yet.
    if(h_htf_ema_f == INVALID_HANDLE || h_htf_ema_s == INVALID_HANDLE ||
       h_htf_ema_t == INVALID_HANDLE || h_htf_adx   == INVALID_HANDLE ||
       h_h1_macd   == INVALID_HANDLE || h_m30_ema_f == INVALID_HANDLE ||
       h_m30_rsi   == INVALID_HANDLE)
    {
        reason = "HTF handles not ready (fail-open)";
        return true;
    }

    // --- H4 trend vote: EMA fan + ADX strength + price side ---
    double e20=0, e50=0, e200=0, adx_h4=0, px_h4=0;
    if(!CopyOne(h_htf_ema_f, 0, 1, e20))   { reason = "H4 ema20 NaN";  return true; }
    if(!CopyOne(h_htf_ema_s, 0, 1, e50))   { reason = "H4 ema50 NaN";  return true; }
    if(!CopyOne(h_htf_ema_t, 0, 1, e200))  { reason = "H4 ema200 NaN"; return true; }
    if(!CopyOne(h_htf_adx,   0, 1, adx_h4)){ reason = "H4 adx NaN";    return true; }
    MqlRates r4[]; ArraySetAsSeries(r4, true);
    if(CopyRates(_Symbol, InpHTFTrendTF, 0, 3, r4) < 2)
    { reason = "H4 rates NaN"; return true; }
    px_h4 = r4[1].close;

    if(adx_h4 < InpHTF_ADX_Min)
    { reason = StringFormat("H4 ADX too weak %.1f<%.1f", adx_h4, InpHTF_ADX_Min); return false; }

    int h4_vote = 0;
    if(e20 > e50 && e50 > e200 && px_h4 > e20) h4_vote =  1;
    if(e20 < e50 && e50 < e200 && px_h4 < e20) h4_vote = -1;
    if(h4_vote == 0)
    { reason = StringFormat("H4 no clean fan (e20=%.2f e50=%.2f e200=%.2f px=%.2f)",
                            e20,e50,e200,px_h4); return false; }
    if(h4_vote != dir_want)
    { reason = StringFormat("H4 trend=%s wants=%s", h4_vote==1?"BUY":"SELL",
                            dir_want==1?"BUY":"SELL"); return false; }

    // --- H1 momentum vote: MACD hist direction ---
    double hist_now=0, hist_prev=0;
    double m_now=0, m_prev=0, s_now=0, s_prev=0;
    if(!CopyOne(h_h1_macd, 0, 1, m_now)  ||
       !CopyOne(h_h1_macd, 0, 2, m_prev) ||
       !CopyOne(h_h1_macd, 1, 1, s_now)  ||
       !CopyOne(h_h1_macd, 1, 2, s_prev))
    { reason = "H1 MACD NaN"; return true; }
    hist_now  = m_now  - s_now;
    hist_prev = m_prev - s_prev;
    int h1_vote = 0;
    if(hist_now > 0 && hist_now > hist_prev) h1_vote =  1;
    if(hist_now < 0 && hist_now < hist_prev) h1_vote = -1;
    if(h1_vote == 0)
    { reason = StringFormat("H1 MACD flat hist=%.4f", hist_now); return false; }
    if(h1_vote != dir_want)
    { reason = StringFormat("H1 momo=%s wants=%s", h1_vote==1?"BUY":"SELL",
                            dir_want==1?"BUY":"SELL"); return false; }

    // --- M30 timing vote: price vs EMA20 + RSI not extreme ---
    double em30=0, rsi_m30=0;
    if(!CopyOne(h_m30_ema_f, 0, 1, em30))    { reason = "M30 ema NaN"; return true; }
    if(!CopyOne(h_m30_rsi,   0, 1, rsi_m30)) { reason = "M30 rsi NaN"; return true; }
    MqlRates r30[]; ArraySetAsSeries(r30, true);
    if(CopyRates(_Symbol, InpHTFTimingTF, 0, 3, r30) < 2)
    { reason = "M30 rates NaN"; return true; }
    double px_m30 = r30[1].close;

    int m30_vote = 0;
    if(px_m30 > em30 && rsi_m30 > 45.0 && rsi_m30 < 70.0) m30_vote =  1;
    if(px_m30 < em30 && rsi_m30 > 30.0 && rsi_m30 < 55.0) m30_vote = -1;
    if(m30_vote == 0)
    { reason = StringFormat("M30 no trigger rsi=%.1f px_vs_ema=%.4f",
                            rsi_m30, px_m30 - em30); return false; }
    if(m30_vote != dir_want)
    { reason = StringFormat("M30 timing=%s wants=%s", m30_vote==1?"BUY":"SELL",
                            dir_want==1?"BUY":"SELL"); return false; }

    reason = StringFormat("PASS H4 adx=%.1f H1 hist=%.4f M30 rsi=%.1f",
                          adx_h4, hist_now, rsi_m30);
    return true;
}


void TryEntry(int rates_total, const double &close[])
{
    if(!SessionOK())          return;
    if(!NewsWindowOK())       return;
    if(DailyLossKillHit())    return;
    if(CountOpenForSym() >= InpMaxOpenPerSym) return;
    if(TimeCurrent() - g_last_entry < InpCooldownSecs) return;

    ConfSet c;
    if(!FillConfirmations(rates_total, close, c, 1)) return;
    if(!SpreadOK(c.atr)) return;

    // 3-of-3 requirement (runtime-override via signal JSON, R11)
    int need = EffectiveRequireAll3() ? 3 : 2;
    if(c.trend_dir == 0 || c.agreed < need)
    {
        BLK(StringFormat("3-of-3 fail: dir=%d agreed=%d/%d C1=%d C2=%d C3=%d adx=%.1f",
            c.trend_dir, c.agreed, need, c.c1_trend, c.c2_vola, c.c3_momo, c.adx),
            "3of3");
        return;
    }
    if(c.trend_dir ==  1 && !InpAllowLong)  return;
    if(c.trend_dir == -1 && !InpAllowShort) return;

    // HTF gate (M30 + H1 + H4 unanimous alignment)
    if(InpUseHTFGate)
    {
        string htf_why;
        if(!CheckHTFGate(c.trend_dir, htf_why))
        {
            BLK("HTF gate BLOCK: " + htf_why, "htf");
            return;
        }
        DBG("HTF gate " + htf_why);
    }

    // AI gate
    if(InpUseAIGate)
    {
        string ai_dir; double ai_conf;
        int rc = ReadAIGate(ai_dir, ai_conf);
        if(rc == 0)
        {
            string want = c.trend_dir == 1 ? "BUY" : "SELL";
            if(ai_dir != want || ai_conf < 0.55)
            {
                BLK(StringFormat("AI gate disagrees: EA wants=%s brain=%s conf=%.2f",
                                 want, ai_dir, ai_conf), "ai_dis");
                return;
            }
            DBG(StringFormat("AI gate PASS: dir=%s conf=%.2f", ai_dir, ai_conf));
        }
        else if(InpAIRequired)
        {
            BLK("AI gate signal missing/stale and InpAIRequired=true", "ai_stale");
            return;
        }
    }

    // Compute SL / TP
    double px  = (c.trend_dir == 1) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                    : SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double sl_dist = InpSL_AtrMult * c.atr;
    double tp_dist = InpTP_AtrMult * c.atr;
    double min_sd  = MinStopDistance();
    if(sl_dist < min_sd) sl_dist = min_sd;

    double sl, tp;
    if(c.trend_dir == 1){ sl = px - sl_dist; tp = px + tp_dist; }
    else                { sl = px + sl_dist; tp = px - tp_dist; }

    double lots = ComputeLot(sl_dist);
    TrySendOrder(c.trend_dir, px, sl, tp, lots);
}

//====================================================================
//  MANAGEMENT (runs on every tick — this is the millisecond layer)
//====================================================================
void ManagePositions()
{
    ulong tnow = GetMicrosecondCount();
    if(g_last_tick_us != 0 && tnow - g_last_tick_us < 1000) return;   // 1 ms min gap
    g_last_tick_us = tnow;

    PurgeClosedFlags();

    double atr_now;
    if(!CopyOne(h_atr, 0, 0, atr_now)) return;

    for(int i = PositionsTotal() - 1; i >= 0; --i)
    {
        if(!Pos.SelectByIndex(i)) continue;
        if(Pos.Symbol() != _Symbol || Pos.Magic() != InpMagic) continue;

        ulong  tk      = Pos.Ticket();
        int    ptype   = (int)Pos.PositionType();
        int    dir     = (ptype == POSITION_TYPE_BUY) ? 1 : -1;
        double entry   = Pos.PriceOpen();
        double cur     = (dir == 1) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                    : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl      = Pos.StopLoss();
        double tp      = Pos.TakeProfit();
        double vol     = Pos.Volume();

        int flg = FindFlagIdx(tk);
        if(flg < 0)
        {
            // orphan (EA restarted) — synthesize
            double risk = MathAbs(entry - sl);
            if(risk <= 0) risk = InpSL_AtrMult * atr_now;
            AddFlag(tk, sl, risk);
            flg = FindFlagIdx(tk);
        }
        double risk = g_flags[flg].initial_risk;
        if(risk <= 0) continue;

        double gain      = (dir == 1) ? (cur - entry) : (entry - cur);
        double R         = gain / risk;

        double buf = InpBeBufferAtr * atr_now;

        //── +1R: close partial 40% + break-even ─────────────────
        if(InpUsePartial1 && !g_flags[flg].p1_done && R >= 1.0)
        {
            double close_vol = NormalizeDouble(vol * InpPartial1Pct, 2);
            double minl  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
            if(close_vol < minl) close_vol = minl;
            if(close_vol > vol)  close_vol = vol;
            if(Trade.PositionClosePartial(tk, close_vol))
            {
                g_flags[flg].p1_done = true;
                DBG(StringFormat("+1R partial %.2f lots closed ticket=%I64u", close_vol, tk));
            }

            double new_sl = (dir == 1) ? entry + buf : entry - buf;
            Trade.PositionModify(tk, NP(new_sl), tp);
            g_flags[flg].be_done = true;
        }

        //── +1R: PYRAMID add-on tranche (ride the winner) ───────
        if(InpUsePyramid && !g_flags[flg].pyramid_done &&
           g_flags[flg].p1_done && R >= InpPyramidR)
        {
            // Guard: require SuperTrend still favorable if configured.
            bool trend_ok = true;
            if(InpPyramidNeedTrend)
                trend_ok = SuperTrendAgrees(dir);

            if(trend_ok)
            {
                // We only have the CURRENT (post-partial) volume, so back out
                // the original lot size via the remaining fraction.
                //   add_lots = (Pos.Volume() / (1 - InpPartial1Pct)) * InpPyramidSizePct
                double remaining_frac = (1.0 - InpPartial1Pct);
                if(remaining_frac <= 0) remaining_frac = 0.6;   // safety
                double add_lots = NormalizeDouble(
                    (Pos.Volume() / remaining_frac) * InpPyramidSizePct, 2);

                double minl  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
                double maxl  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
                double stepl = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
                if(add_lots < minl) add_lots = minl;
                if(add_lots > maxl) add_lots = maxl;
                if(stepl > 0.0)
                    add_lots = MathFloor(add_lots / stepl) * stepl;

                // Market entry; SL at BE (same buf as partial#1); TP at the
                // original entry's 3R extension so this tranche rides the
                // runner to the same target.
                double add_entry = (dir == 1) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                              : SymbolInfoDouble(_Symbol, SYMBOL_BID);
                double add_sl    = (dir == 1) ? entry + buf : entry - buf;
                double add_tp    = (dir == 1) ? entry + 3.0 * risk
                                              : entry - 3.0 * risk;

                Trade.SetExpertMagicNumber(InpMagic);
                Trade.SetDeviationInPoints(InpSlippagePts);
                string add_cmt = StringFormat("%s_PYR_%s", InpComment,
                                              dir == 1 ? "L" : "S");
                bool ok = false;
                if(dir == 1)
                    ok = Trade.Buy (add_lots, _Symbol, 0.0, NP(add_sl),
                                    NP(add_tp), add_cmt);
                else
                    ok = Trade.Sell(add_lots, _Symbol, 0.0, NP(add_sl),
                                    NP(add_tp), add_cmt);

                if(ok)
                {
                    g_flags[flg].pyramid_done   = true;
                    g_flags[flg].pyramid_ticket = Trade.ResultOrder();
                    // Pre-register a flag for the new tranche with
                    // pyramid_done=true so it cannot spawn its own cascade
                    // pyramid on a subsequent +1R hit of its own entry.
                    ulong  pyr_deal = Trade.ResultDeal();
                    ulong  pyr_pos  = pyr_deal;
                    if(!PositionSelectByTicket(pyr_pos))
                    {
                        // fall back to newest position walk
                        for(int px = PositionsTotal() - 1; px >= 0; --px)
                        {
                            if(!Pos.SelectByIndex(px)) continue;
                            if(Pos.Symbol() == _Symbol && Pos.Magic() == InpMagic
                               && Pos.Ticket() != tk)
                            { pyr_pos = Pos.Ticket(); break; }
                        }
                    }
                    double pyr_risk = MathAbs(add_entry - add_sl);
                    if(pyr_risk <= 0) pyr_risk = risk;
                    AddFlag(pyr_pos, add_sl, pyr_risk);
                    int pflg = FindFlagIdx(pyr_pos);
                    if(pflg >= 0) g_flags[pflg].pyramid_done = true;

                    DBG(StringFormat("PYRAMID opened %.2f lots (parent=%I64u, tranche=%I64u) entry=%.5f SL=%.5f TP=%.5f",
                                     add_lots, tk, g_flags[flg].pyramid_ticket,
                                     add_entry, add_sl, add_tp));
                }
                else
                {
                    DBG(StringFormat("PYRAMID failed ticket=%I64u reason=%d desc=%s",
                                     tk, Trade.ResultRetcode(), Trade.ResultComment()));
                }
            }
            else
            {
                DBG(StringFormat("PYRAMID skipped — SuperTrend disagrees ticket=%I64u", tk));
                // Mark done so we don't keep retrying every tick on a
                // flipped regime. Operator can tune InpPyramidNeedTrend.
                g_flags[flg].pyramid_done = true;
            }
        }

        //── +2R: close partial 30% + lock at +1R ────────────────
        if(InpUsePartial2 && !g_flags[flg].p2_done && R >= 2.0)
        {
            double close_vol = NormalizeDouble(Pos.Volume() * InpPartial2Pct, 2);
            double minl  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
            if(close_vol < minl) close_vol = minl;
            if(close_vol > Pos.Volume())  close_vol = Pos.Volume();
            if(Trade.PositionClosePartial(tk, close_vol))
            {
                g_flags[flg].p2_done = true;
                DBG(StringFormat("+2R partial %.2f lots closed ticket=%I64u", close_vol, tk));
            }

            double lock_sl = (dir == 1) ? entry + risk : entry - risk;
            Trade.PositionModify(tk, NP(lock_sl), tp);
            g_flags[flg].lock1r_done = true;
        }

        //── CHANDELIER TRAIL (runner) ───────────────────────────
        if(InpUseChandelier && g_flags[flg].be_done)
        {
            MqlRates rt[];
            ArraySetAsSeries(rt, true);
            int got = CopyRates(_Symbol, _Period, 0, InpChandelierLook + 2, rt);
            if(got >= InpChandelierLook + 2)
            {
                double hh = rt[1].high, ll = rt[1].low;
                for(int k = 2; k <= InpChandelierLook; ++k)
                {
                    if(rt[k].high > hh) hh = rt[k].high;
                    if(rt[k].low  < ll) ll = rt[k].low;
                }
                double trail;
                if(dir == 1)
                {
                    trail = hh - InpChandelierAtr * atr_now;
                    if(trail > Pos.StopLoss() && trail < cur)
                        Trade.PositionModify(tk, NP(trail), tp);
                }
                else
                {
                    trail = ll + InpChandelierAtr * atr_now;
                    if((Pos.StopLoss() == 0 || trail < Pos.StopLoss()) && trail > cur)
                        Trade.PositionModify(tk, NP(trail), tp);
                }
            }
        }
    }
}

//====================================================================
//  TRADE HISTORY UPDATE (for Kelly)
//====================================================================
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest     &request,
                        const MqlTradeResult      &result)
{
    if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
    ulong deal = trans.deal;
    if(deal == 0) return;
    if(!HistoryDealSelect(deal)) return;

    long magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
    if(magic != InpMagic) return;

    int entry = (int)HistoryDealGetInteger(deal, DEAL_ENTRY);
    if(entry != DEAL_ENTRY_OUT) return;     // only closing deals

    double profit  = HistoryDealGetDouble(deal, DEAL_PROFIT)
                   + HistoryDealGetDouble(deal, DEAL_SWAP)
                   + HistoryDealGetDouble(deal, DEAL_COMMISSION);

    if(profit > 0){ g_wins++;   g_avgWinR  = 0.7 * g_avgWinR  + 0.3 * 1.5; }
    else          { g_losses++; g_avgLossR = 0.7 * g_avgLossR + 0.3 * 1.0; }
}

//====================================================================
//  CHART OVERLAYS — draw EMAs, BB, SuperTrend, arrows as real objects
//====================================================================
void DeleteTrendWithPrefix(const string p)
{
    // Remove all chart objects whose name starts with p
    int total = ObjectsTotal(0, 0, -1);
    for(int i = total - 1; i >= 0; --i)
    {
        string nm = ObjectName(0, i, 0, -1);
        if(StringLen(nm) >= StringLen(p) &&
           StringSubstr(nm, 0, StringLen(p)) == p)
            ObjectDelete(0, nm);
    }
}

void DrawSegment(const string name, datetime t1, double p1, datetime t2, double p2,
                 color col, int width = 1, ENUM_LINE_STYLE style = STYLE_SOLID)
{
    if(ObjectFind(0, name) < 0)
        ObjectCreate(0, name, OBJ_TREND, 0, t1, p1, t2, p2);
    ObjectSetInteger(0, name, OBJPROP_TIME,  0, t1);
    ObjectSetDouble (0, name, OBJPROP_PRICE, 0, p1);
    ObjectSetInteger(0, name, OBJPROP_TIME,  1, t2);
    ObjectSetDouble (0, name, OBJPROP_PRICE, 1, p2);
    ObjectSetInteger(0, name, OBJPROP_COLOR,    col);
    ObjectSetInteger(0, name, OBJPROP_WIDTH,    width);
    ObjectSetInteger(0, name, OBJPROP_STYLE,    style);
    ObjectSetInteger(0, name, OBJPROP_RAY_LEFT,  false);
    ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
    ObjectSetInteger(0, name, OBJPROP_BACK,      true);
    ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
    ObjectSetInteger(0, name, OBJPROP_HIDDEN,    true);
}

void DrawPolyline(const string key, const double &buf[], const datetime &tm[],
                  int count, color col, int width = 1)
{
    // buf / tm are AsSeries(true): buf[0] = newest
    string pfx = PFX + key + "_";
    for(int i = 1; i < count; ++i)
    {
        if(buf[i] == 0.0 || buf[i-1] == 0.0) continue;   // skip invalid
        if(buf[i] == EMPTY_VALUE || buf[i-1] == EMPTY_VALUE) continue;
        string nm = pfx + IntegerToString(i);
        DrawSegment(nm, tm[i], buf[i], tm[i-1], buf[i-1], col, width);
    }
}

void DrawSTPolyline(const datetime &tm[], int bars_to_draw, int rates_total)
{
    // Uses g_st_line / g_st_dir (indexed chronologically, ci = rates_total-1-ser)
    string pfx = PFX + "ST_";
    for(int ser = 1; ser < bars_to_draw; ++ser)
    {
        int ci_new = rates_total - 1 - ser;
        int ci_old = rates_total - 1 - (ser + 1);
        if(ci_old < 0 || ci_new < 0 || ci_new >= g_st_size) continue;
        double v_new = g_st_line[ci_new];
        double v_old = g_st_line[ci_old];
        if(v_new == 0.0 || v_old == 0.0) continue;
        int d = g_st_dir[ci_new];
        color col = (d == 1) ? InpColSTUp : (d == -1) ? InpColSTDown : clrGray;
        string nm = pfx + IntegerToString(ser);
        DrawSegment(nm, tm[ser], v_new, tm[ser+1], v_old, col, 2);
    }
}

void DrawArrowAt(const string key, datetime t, double price, bool is_buy)
{
    string nm = PFX + "ARR_" + key + "_" + IntegerToString((long)t);
    if(ObjectFind(0, nm) < 0)
        ObjectCreate(0, nm, is_buy ? OBJ_ARROW_BUY : OBJ_ARROW_SELL, 0, t, price);
    ObjectSetInteger(0, nm, OBJPROP_COLOR,
                     is_buy ? InpColArrowBuy : InpColArrowSell);
    ObjectSetInteger(0, nm, OBJPROP_WIDTH, 2);
    ObjectSetInteger(0, nm, OBJPROP_BACK,  false);
    ObjectSetInteger(0, nm, OBJPROP_HIDDEN, true);
    ObjectSetInteger(0, nm, OBJPROP_SELECTABLE, false);
}

void DrawSLTPLines()
{
    // If layer disabled, hard-wipe and bail.
    if(!InpShowSLTPLines)
    {
        DeleteTrendWithPrefix(PFX + "SLTP_");
        return;
    }

    // Build the set of currently-open ticket keys so we can prune stale
    // SLTP_ objects (closed positions) without nuking the live ones.
    // ObjectSet* on the surviving objects is a no-op redraw → no blink.
    string live_keys[];
    int live_n = 0;
    for(int j = 0; j < PositionsTotal(); ++j)
    {
        if(!Pos.SelectByIndex(j)) continue;
        if(Pos.Symbol() != _Symbol) continue;
        if(Pos.Magic()  != InpMagic) continue;
        ArrayResize(live_keys, live_n + 1);
        live_keys[live_n++] = PFX + "SLTP_" + IntegerToString((long)Pos.Ticket()) + "_";
    }

    int total = ObjectsTotal(0, 0, -1);
    string sltp_pfx = PFX + "SLTP_";
    int pfx_len = StringLen(sltp_pfx);
    for(int k = total - 1; k >= 0; --k)
    {
        string nm = ObjectName(0, k, 0, -1);
        if(StringLen(nm) < pfx_len) continue;
        if(StringSubstr(nm, 0, pfx_len) != sltp_pfx) continue;
        bool keep = false;
        for(int m = 0; m < live_n; ++m)
        {
            int klen = StringLen(live_keys[m]);
            if(StringLen(nm) >= klen &&
               StringSubstr(nm, 0, klen) == live_keys[m]) { keep = true; break; }
        }
        if(!keep) ObjectDelete(0, nm);
    }

    for(int i = 0; i < PositionsTotal(); ++i)
    {
        if(!Pos.SelectByIndex(i)) continue;
        if(Pos.Symbol() != _Symbol) continue;
        if(Pos.Magic()  != InpMagic) continue;
        double sl = Pos.StopLoss();
        double tp = Pos.TakeProfit();
        double op = Pos.PriceOpen();
        ulong tk = Pos.Ticket();
        string keyBase = PFX + "SLTP_" + IntegerToString((long)tk) + "_";
        // Entry
        string enm = keyBase + "E";
        if(ObjectFind(0, enm) < 0) ObjectCreate(0, enm, OBJ_HLINE, 0, 0, op);
        ObjectSetDouble (0, enm, OBJPROP_PRICE, op);
        ObjectSetInteger(0, enm, OBJPROP_COLOR, clrYellow);
        ObjectSetInteger(0, enm, OBJPROP_STYLE, STYLE_DOT);
        ObjectSetInteger(0, enm, OBJPROP_WIDTH, 1);
        ObjectSetInteger(0, enm, OBJPROP_BACK,  true);
        ObjectSetString (0, enm, OBJPROP_TEXT,  "ENTRY #" + IntegerToString((long)tk));
        if(sl > 0.0)
        {
            string snm = keyBase + "SL";
            if(ObjectFind(0, snm) < 0) ObjectCreate(0, snm, OBJ_HLINE, 0, 0, sl);
            ObjectSetDouble (0, snm, OBJPROP_PRICE, sl);
            ObjectSetInteger(0, snm, OBJPROP_COLOR, clrRed);
            ObjectSetInteger(0, snm, OBJPROP_STYLE, STYLE_DASH);
            ObjectSetInteger(0, snm, OBJPROP_WIDTH, 1);
            ObjectSetInteger(0, snm, OBJPROP_BACK,  true);
            ObjectSetString (0, snm, OBJPROP_TEXT,  "SL");
        }
        if(tp > 0.0)
        {
            string tnm = keyBase + "TP";
            if(ObjectFind(0, tnm) < 0) ObjectCreate(0, tnm, OBJ_HLINE, 0, 0, tp);
            ObjectSetDouble (0, tnm, OBJPROP_PRICE, tp);
            ObjectSetInteger(0, tnm, OBJPROP_COLOR, clrLime);
            ObjectSetInteger(0, tnm, OBJPROP_STYLE, STYLE_DASH);
            ObjectSetInteger(0, tnm, OBJPROP_WIDTH, 1);
            ObjectSetInteger(0, tnm, OBJPROP_BACK,  true);
            ObjectSetString (0, tnm, OBJPROP_TEXT,  "TP");
        }
    }
}

void DrawIndicatorLines()
{
    int bars_need = MathMax(InpDrawBars, InpEMA_Trend + 10);

    MqlRates rt[];
    ArraySetAsSeries(rt, true);
    int got = CopyRates(_Symbol, _Period, 0, bars_need, rt);
    if(got < 50) return;

    double high_a[], low_a[], close_a[];
    datetime tm[];
    ArraySetAsSeries(high_a,  true);
    ArraySetAsSeries(low_a,   true);
    ArraySetAsSeries(close_a, true);
    ArraySetAsSeries(tm,      true);
    ArrayResize(high_a,  got);
    ArrayResize(low_a,   got);
    ArrayResize(close_a, got);
    ArrayResize(tm,      got);
    for(int i = 0; i < got; ++i)
    {
        high_a[i]  = rt[i].high;
        low_a[i]   = rt[i].low;
        close_a[i] = rt[i].close;
        tm[i]      = rt[i].time;
    }

    int draw_count = MathMin(InpDrawBars, got - 1);

    // ---- EMAs
    // NOTE: DrawSegment already does ObjectFind→update-or-create, so we no
    // longer wipe the old segments before redrawing — that delete+create
    // churn was the source of the visible chart blink. Only the disabled
    // branches still call Delete*, to clean up if the user toggles a layer
    // off at runtime.
    if(InpShowEMAs)
    {
        double ef[], es[], et[];
        ArraySetAsSeries(ef, true); ArraySetAsSeries(es, true); ArraySetAsSeries(et, true);
        if(CopyBuffer(h_ema_f, 0, 0, draw_count + 2, ef) == draw_count + 2 &&
           CopyBuffer(h_ema_s, 0, 0, draw_count + 2, es) == draw_count + 2 &&
           CopyBuffer(h_ema_t, 0, 0, draw_count + 2, et) == draw_count + 2)
        {
            DrawPolyline("EMAF", ef, tm, draw_count, InpColEMAFast,  2);
            DrawPolyline("EMAS", es, tm, draw_count, InpColEMASlow,  2);
            DrawPolyline("EMAT", et, tm, draw_count, InpColEMATrend, 2);
        }
    }
    else
    {
        DeleteTrendWithPrefix(PFX + "EMAF_");
        DeleteTrendWithPrefix(PFX + "EMAS_");
        DeleteTrendWithPrefix(PFX + "EMAT_");
    }

    // ---- Bollinger
    if(InpShowBB)
    {
        double bu[], bm[], bl[];
        ArraySetAsSeries(bu, true); ArraySetAsSeries(bm, true); ArraySetAsSeries(bl, true);
        // buffer 0 = middle (BASE), 1 = upper, 2 = lower on iBands
        if(CopyBuffer(h_bb, 1, 0, draw_count + 2, bu) == draw_count + 2 &&
           CopyBuffer(h_bb, 0, 0, draw_count + 2, bm) == draw_count + 2 &&
           CopyBuffer(h_bb, 2, 0, draw_count + 2, bl) == draw_count + 2)
        {
            DrawPolyline("BBU", bu, tm, draw_count, InpColBBUpper, 1);
            DrawPolyline("BBM", bm, tm, draw_count, InpColBBMid,   1);
            DrawPolyline("BBL", bl, tm, draw_count, InpColBBLower, 1);
        }
    }
    else
    {
        DeleteTrendWithPrefix(PFX + "BBU_");
        DeleteTrendWithPrefix(PFX + "BBM_");
        DeleteTrendWithPrefix(PFX + "BBL_");
    }

    // ---- SuperTrend (use our hand-rolled buffer)
    if(InpShowSuperTrend)
    {
        EnsureSuperTrend(got, high_a, low_a, close_a, tm);
        DrawSTPolyline(tm, draw_count, got);
    }
    else
    {
        DeleteTrendWithPrefix(PFX + "ST_");
    }

    // ---- Arrows at 3-of-3 aligned bars (historical scan)
    if(InpShowArrows)
    {
        // Only add arrows for the last closed bar (shift=1) — avoids repaint.
        ConfSet c;
        if(FillConfirmations(got, close_a, c, 1) && c.agreed == 3 && c.trend_dir != 0)
        {
            datetime t1 = tm[1];
            double price = (c.trend_dir == 1) ? rt[1].low - c.atr * 0.25
                                              : rt[1].high + c.atr * 0.25;
            DrawArrowAt(IntegerToString((long)t1),
                        t1, price, c.trend_dir == 1);
        }
    }
    else
    {
        DeleteTrendWithPrefix(PFX + "ARR_");
    }

    // SL/TP lines are intentionally NOT drawn here — they live on the
    // 1-sec OnTimer beat so trailing-stop moves are visible immediately,
    // independent of bar-close cadence.
}

//====================================================================
//  DASHBOARD
//====================================================================
void DrawDashboard(const ConfSet &c)
{
    string lines[12];
    int n = 0;
    lines[n++] = "=== TRENDMASTER v14.0 ===";
    lines[n++] = StringFormat("%s M5  %.5f  ATR=%.4f", _Symbol, SymbolInfoDouble(_Symbol, SYMBOL_BID), c.atr);
    lines[n++] = StringFormat("Trend %s  ADX=%.1f  ST=%s",
                              c.trend_dir==1?"BULL":c.trend_dir==-1?"BEAR":"NONE",
                              c.adx, c.st_dir==1?"UP":c.st_dir==-1?"DN":"-");
    lines[n++] = StringFormat("EMA %.2f > %.2f > %.2f", c.ema_fast, c.ema_slow, c.ema_trend);
    lines[n++] = StringFormat("BB mid %.2f  width %.2f (med %.2f)",
                              c.bb_mid, c.bb_upper - c.bb_lower, c.bb_width_med);
    lines[n++] = StringFormat("MACD %.4f/%.4f hist %.4f",
                              c.macd_main, c.macd_sig, c.macd_hist);
    lines[n++] = StringFormat("C1=%s  C2=%s  C3=%s  agreed=%d/3",
                              c.c1_trend?"OK":"-",
                              c.c2_vola?"OK":"-",
                              c.c3_momo?"OK":"-",
                              c.agreed);
    lines[n++] = StringFormat("Open: %d  Wins/Loss %d/%d  Kelly=%.2f",
                              CountOpenForSym(), g_wins, g_losses, KellyFraction());

    int y = 20;
    for(int i = 0; i < n; ++i)
    {
        string nm = PFX + "LBL_" + IntegerToString(i);
        if(ObjectFind(0, nm) < 0) ObjectCreate(0, nm, OBJ_LABEL, 0, 0, 0);
        ObjectSetString (0, nm, OBJPROP_TEXT,      lines[i]);
        ObjectSetInteger(0, nm, OBJPROP_XDISTANCE, 10);
        ObjectSetInteger(0, nm, OBJPROP_YDISTANCE, y);
        ObjectSetInteger(0, nm, OBJPROP_COLOR,
             i == 0 ? clrGold : (i == 6 ? clrAqua : clrSilver));
        ObjectSetInteger(0, nm, OBJPROP_FONTSIZE,  i == 0 ? 10 : 9);
        ObjectSetInteger(0, nm, OBJPROP_CORNER,    CORNER_LEFT_UPPER);
        ObjectSetInteger(0, nm, OBJPROP_SELECTABLE, false);
        y += 16;
    }
}

//====================================================================
//  LIFECYCLE
//====================================================================
int OnInit()
{
    Trade.SetExpertMagicNumber(InpMagic);

    h_st_atr = iATR  (_Symbol, _Period, InpST_Period);
    h_ema_f  = iMA   (_Symbol, _Period, InpEMA_Fast,  0, MODE_EMA, PRICE_CLOSE);
    h_ema_s  = iMA   (_Symbol, _Period, InpEMA_Slow,  0, MODE_EMA, PRICE_CLOSE);
    h_ema_t  = iMA   (_Symbol, _Period, InpEMA_Trend, 0, MODE_EMA, PRICE_CLOSE);
    h_adx    = iADX  (_Symbol, _Period, InpADX_Period);
    h_bb     = iBands(_Symbol, _Period, InpBB_Period, 0, InpBB_Dev, PRICE_CLOSE);
    h_macd   = iMACD (_Symbol, _Period, InpMACD_Fast, InpMACD_Slow, InpMACD_Sig, PRICE_CLOSE);
    h_atr    = iATR  (_Symbol, _Period, InpATR_Period);

    if(h_st_atr==INVALID_HANDLE || h_ema_f==INVALID_HANDLE || h_ema_s==INVALID_HANDLE ||
       h_ema_t==INVALID_HANDLE  || h_adx==INVALID_HANDLE   || h_bb==INVALID_HANDLE   ||
       h_macd==INVALID_HANDLE   || h_atr==INVALID_HANDLE)
    {
        Print("[TMv14] Indicator handle failure");
        return INIT_FAILED;
    }

    // --- HTF gate handles (M30 timing + H1 momentum + H4 trend) ---
    if(InpUseHTFGate)
    {
        h_htf_ema_f = iMA (_Symbol, InpHTFTrendTF,    InpHTF_EMA_Fast,  0, MODE_EMA, PRICE_CLOSE);
        h_htf_ema_s = iMA (_Symbol, InpHTFTrendTF,    InpHTF_EMA_Slow,  0, MODE_EMA, PRICE_CLOSE);
        h_htf_ema_t = iMA (_Symbol, InpHTFTrendTF,    InpHTF_EMA_Trend, 0, MODE_EMA, PRICE_CLOSE);
        h_htf_adx   = iADX(_Symbol, InpHTFTrendTF,    InpHTF_ADX_Period);
        h_h1_macd   = iMACD(_Symbol, InpHTFMomentumTF, InpHTF_MACD_Fast,
                            InpHTF_MACD_Slow, InpHTF_MACD_Sig, PRICE_CLOSE);
        h_m30_ema_f = iMA (_Symbol, InpHTFTimingTF,   InpHTF_EMA_Fast,  0, MODE_EMA, PRICE_CLOSE);
        h_m30_rsi   = iRSI(_Symbol, InpHTFTimingTF,   InpHTF_RSI_Period, PRICE_CLOSE);

        if(h_htf_ema_f==INVALID_HANDLE || h_htf_ema_s==INVALID_HANDLE ||
           h_htf_ema_t==INVALID_HANDLE || h_htf_adx==INVALID_HANDLE   ||
           h_h1_macd==INVALID_HANDLE   || h_m30_ema_f==INVALID_HANDLE ||
           h_m30_rsi==INVALID_HANDLE)
        {
            Print("[TMv14] HTF handle failure — gate will fail-open until handles warm up");
        }
    }

    g_day_start     = (datetime)(TimeCurrent() - TimeCurrent() % 86400);
    g_day_start_bal = AccountInfoDouble(ACCOUNT_BALANCE);

    // [R5 2026-04-23] Auto-add MT5 native indicators to chart windows.
    // These replace the invisible polyline objects with proper thick
    // chart indicators (BB bands + EMA 20/50/200 on main pane; MACD,
    // ADX, RSI each in their own subwindow).
    if(InpAutoAddStdIndicators)
    {
        // Main window (0): Bollinger + EMA fan.
        ChartIndicatorAdd(0, 0, h_bb);
        ChartIndicatorAdd(0, 0, h_ema_f);
        ChartIndicatorAdd(0, 0, h_ema_s);
        ChartIndicatorAdd(0, 0, h_ema_t);

        // Subwindow 1: MACD.
        ChartIndicatorAdd(0, 1, h_macd);

        // Subwindow 2: ADX.
        ChartIndicatorAdd(0, 2, h_adx);

        // Subwindow 3: RSI — allocate a fresh handle purely for display.
        int h_rsi_display = iRSI(_Symbol, _Period, 14, PRICE_CLOSE);
        if(h_rsi_display != INVALID_HANDLE)
            ChartIndicatorAdd(0, 3, h_rsi_display);

        ChartRedraw(0);
    }

    DBG("Initialized " + _Symbol + " M5");
    EventSetTimer(1);                    // 1-sec dashboard heartbeat
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
    EventKillTimer();
    ObjectsDeleteAll(0, PFX);
}

// Track the last bar we redrew so we only do the heavy polyline redraw
// when a new bar forms — not on every 1-sec timer tick. This kills the
// blink without losing any visual fidelity (the lines didn't change
// between ticks anyway, since they're computed off closed-bar values).
static datetime g_last_draw_bar = 0;

void OnTimer()
{
    // dashboard refresh runs every second — labels use ObjectFind+update,
    // so they don't blink and the dashboard stays live.
    MqlRates rt[];
    ArraySetAsSeries(rt, true);
    int got = CopyRates(_Symbol, _Period, 0, 300, rt);
    if(got < 100) return;
    double close[];
    ArraySetAsSeries(close, true);
    ArrayResize(close, got);
    for(int i = 0; i < got; ++i) close[i] = rt[i].close;
    ConfSet c;
    if(FillConfirmations(got, close, c, 1)) DrawDashboard(c);

    // Heavy polyline redraw (EMAs / BB / SuperTrend) only when a new bar
    // closes. The lines are computed off closed-bar values so they don't
    // change between ticks anyway — running this every second was pure
    // delete/create churn (the visible chart blink).
    datetime cur_bar = (datetime)SeriesInfoInteger(_Symbol, _Period, SERIES_LASTBAR_DATE);
    if(cur_bar != g_last_draw_bar)
    {
        g_last_draw_bar = cur_bar;
        DrawIndicatorLines();
    }

    // SL/TP lines refresh every second so trailing-stop moves show up
    // immediately. Each line uses ObjectFind→update, so no blink.
    DrawSLTPLines();

    ChartRedraw(0);
}

void OnTick()
{
    // Always manage open positions on every tick (millisecond layer)
    ManagePositions();

    // Entry check only on new M5 bar close
    datetime cur_bar = (datetime)SeriesInfoInteger(_Symbol, _Period, SERIES_LASTBAR_DATE);
    if(cur_bar == g_last_bar) return;
    g_last_bar = cur_bar;

    MqlRates rt[];
    ArraySetAsSeries(rt, true);
    int got = CopyRates(_Symbol, _Period, 0, 500, rt);
    if(got < InpEMA_Trend + 5) return;

    double close[], high[], low[];
    datetime time_arr[];
    ArraySetAsSeries(close, true);
    ArraySetAsSeries(high, true);
    ArraySetAsSeries(low, true);
    ArraySetAsSeries(time_arr, true);
    ArrayResize(close, got);
    ArrayResize(high,  got);
    ArrayResize(low,   got);
    ArrayResize(time_arr, got);
    for(int i = 0; i < got; ++i)
    {
        close[i]    = rt[i].close;
        high[i]     = rt[i].high;
        low[i]      = rt[i].low;
        time_arr[i] = rt[i].time;
    }

    EnsureSuperTrend(got, high, low, close, time_arr);
    TryEntry(got, close);
}
//+------------------------------------------------------------------+
