//+------------------------------------------------------------------+
//|  AI_AMD_SMC_Indicator.mq5  — VERSION 11.0  "4-LAYER CLEAN"     |
//|                                                                  |
//|  4 INDICATORS (unique shape per layer):                          |
//|                                                                  |
//|  L1. SuperTrend (ATR=10, Mult=3)                                 |
//|      → Tiny CIRCLE (size 1) on flip bars only                   |
//|      → Green line (bull) / Red line (bear)                       |
//|                                                                  |
//|  L2. MACD (12,26,9) — standard momentum                         |
//|      → Tiny DIAMOND (size 1) on zero-line cross only            |
//|                                                                  |
//|  L3. RSI (14) — overbought/oversold                              |
//|      → No separate shape; contributes to score only             |
//|                                                                  |
//|  L4. EMA20 + Candle body direction                               |
//|      → No separate shape; contributes to score only             |
//|                                                                  |
//|  FINAL ARROWS (confluence):                                      |
//|      2/4 score → size 2 Yellow triangle                         |
//|      3/4 score → size 3 Lime/Red triangle                       |
//|      4/4 score → size 5 Gold/Crimson triangle                   |
//|                                                                  |
//|  EMA200 master gate: BUY only above, SELL only below            |
//|  Cooldown: min 4 bars between same-direction signals             |
//|  Built-in backtest: last 500 bars                               |
//+------------------------------------------------------------------+
#property copyright   "AI Trading Agents v11.0"
#property version     "11.00"
#property description "4-Layer: SuperTrend+MACD+RSI+EMA20|Candle — Clean Signals"
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4

//── Plot 1: EMA200 (gold line) ──────────────────────────────────────
#property indicator_label1  "EMA 200"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrGold
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

//── Plot 2: SuperTrend Bull (lime line) ────────────────────────────
#property indicator_label2  "ST Bull"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrLime
#property indicator_style2  STYLE_SOLID
#property indicator_width2  2

//── Plot 3: SuperTrend Bear (red line) ─────────────────────────────
#property indicator_label3  "ST Bear"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrRed
#property indicator_style3  STYLE_SOLID
#property indicator_width3  2

//── Plot 4: EMA20 (orange dotted line) ─────────────────────────────
#property indicator_label4  "EMA 20"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrDarkOrange
#property indicator_style4  STYLE_DOT
#property indicator_width4  1

//── INPUTS ──────────────────────────────────────────────────────────
input group "=== L1: SuperTrend ==="
input int    InpST_Period    = 10;
input double InpST_Mult      = 3.0;

input group "=== L2: MACD ==="
input int    InpMACD_Fast    = 12;
input int    InpMACD_Slow    = 26;
input int    InpMACD_Signal  = 9;

input group "=== L3: RSI ==="
input int    InpRSI_Period   = 14;
input int    InpRSI_BullMin  = 55;   // RSI above this = bullish
input int    InpRSI_BearMax  = 45;   // RSI below this = bearish

input group "=== L4: EMA20 ==="
input int    InpEMA20_Period = 20;
input double InpBodyRatio    = 0.35; // min body/range for candle direction

input group "=== Master Gate ==="
input int    InpEMA200       = 200;  // Master trend EMA

input group "=== Signal Settings ==="
input int    InpMinScore     = 2;    // Min layers (2-4) for final arrow
input int    InpCooldown     = 4;    // Min bars between signals

input group "=== Backtest ==="
input bool   InpBacktest     = true;
input int    InpHistoryBars  = 500;  // History bars to scan
input double InpBT_SL        = 1.5;  // SL = ATR * this
input double InpBT_TP        = 2.0;  // TP = ATR * this
input int    InpBT_MaxWait   = 30;   // Max bars to check outcome

input group "=== Display ==="
input bool   InpShowDots     = true;  // ST flip dots (L1)
input bool   InpShowDiamonds = true;  // MACD cross diamonds (L2)
input bool   InpShowFinal    = true;  // Final score arrows
input bool   InpShowDash     = true;  // Dashboard

//── BUFFERS ─────────────────────────────────────────────────────────
double Buf_EMA200[], Buf_ST_Bull[], Buf_ST_Bear[], Buf_EMA20[];

//── HANDLES ─────────────────────────────────────────────────────────
int h_atr, h_macd, h_rsi, h_ema200, h_ema20;

//── GLOBAL STATE ────────────────────────────────────────────────────
double g_st_val[];
int    g_st_dir[];

bool   g_scanned   = false;
bool   g_bt_done   = false;
int    g_bt_sig    = 0;
int    g_bt_wins   = 0;
int    g_bt_losses = 0;
int    g_bt_open   = 0;
double g_bt_acc    = 0.0;

#define PREFIX "CL11_"

//+------------------------------------------------------------------+
//  HELPERS
//+------------------------------------------------------------------+
void SetLabel(string nm, string txt, int x, int y, color c, int sz=9)
{
    if(ObjectFind(0,nm)<0) ObjectCreate(0,nm,OBJ_LABEL,0,0,0);
    ObjectSetString (0,nm,OBJPROP_TEXT,       txt);
    ObjectSetInteger(0,nm,OBJPROP_XDISTANCE,  x);
    ObjectSetInteger(0,nm,OBJPROP_YDISTANCE,  y);
    ObjectSetInteger(0,nm,OBJPROP_COLOR,       c);
    ObjectSetInteger(0,nm,OBJPROP_FONTSIZE,    sz);
    ObjectSetInteger(0,nm,OBJPROP_CORNER,      CORNER_RIGHT_UPPER);
    ObjectSetInteger(0,nm,OBJPROP_ANCHOR,      ANCHOR_RIGHT_UPPER);
    ObjectSetInteger(0,nm,OBJPROP_SELECTABLE,  false);
}

void DrawShape(string nm, datetime t, double price,
               int code, color c, ENUM_ARROW_ANCHOR anchor, int w=1)
{
    if(ObjectFind(0,nm)>=0) return;
    ObjectCreate(0,nm,OBJ_ARROW,0,t,price);
    ObjectSetInteger(0,nm,OBJPROP_ARROWCODE,  code);
    ObjectSetInteger(0,nm,OBJPROP_COLOR,       c);
    ObjectSetInteger(0,nm,OBJPROP_WIDTH,       w);
    ObjectSetInteger(0,nm,OBJPROP_ANCHOR,      anchor);
    ObjectSetInteger(0,nm,OBJPROP_SELECTABLE,  false);
    ObjectSetInteger(0,nm,OBJPROP_BACK,        false);
}

//+------------------------------------------------------------------+
//  SUPERTREND — fills g_st_val[] and g_st_dir[] (non-series order)
//  index 0 = oldest bar
//+------------------------------------------------------------------+
bool CalcSuperTrend(const double &high[], const double &low[],
                    const double &close[], int rates_total)
{
    ArrayResize(g_st_val, rates_total);
    ArrayResize(g_st_dir, rates_total);

    // CopyBuffer gives series order (index 0 = newest bar)
    double atr_tmp[];
    if(CopyBuffer(h_atr, 0, 0, rates_total, atr_tmp) < rates_total) return false;

    // Build bands in non-series order (i=0 = oldest)
    double upper_band[], lower_band[];
    ArrayResize(upper_band, rates_total);
    ArrayResize(lower_band, rates_total);

    for(int i = 0; i < rates_total; i++)
    {
        int s = rates_total - 1 - i;  // series index (high/low/close are series)
        double atr = atr_tmp[s];
        double hl2 = (high[s] + low[s]) * 0.5;
        upper_band[i] = hl2 + InpST_Mult * atr;
        lower_band[i] = hl2 - InpST_Mult * atr;
    }

    // Init oldest bar
    g_st_val[0] = upper_band[0];
    g_st_dir[0] = -1;

    for(int i = 1; i < rates_total; i++)
    {
        int s      = rates_total - 1 - i;   // this bar (series)
        int s_prev = s + 1;                  // prev bar (series, one older)

        // Classic ST: bands only tighten
        double fl = lower_band[i];
        double fu = upper_band[i];

        if(lower_band[i-1] > 0.0 && close[s_prev] > lower_band[i-1])
            fl = MathMax(fl, lower_band[i-1]);
        if(upper_band[i-1] > 0.0 && close[s_prev] < upper_band[i-1])
            fu = MathMin(fu, upper_band[i-1]);

        lower_band[i] = fl;
        upper_band[i] = fu;

        if(g_st_dir[i-1] == -1)
        {
            if(close[s] > fu) { g_st_dir[i] = 1;  g_st_val[i] = fl; }
            else               { g_st_dir[i] = -1; g_st_val[i] = fu; }
        }
        else
        {
            if(close[s] < fl) { g_st_dir[i] = -1; g_st_val[i] = fu; }
            else               { g_st_dir[i] = 1;  g_st_val[i] = fl; }
        }
    }
    return true;
}

//+------------------------------------------------------------------+
//  SCORE SIGNAL — 4 layers, each ±1
//  Returns total score (positive=buy, negative=sell)
//  score_out: absolute layer score
//  dir_out:   +1 buy / -1 sell / 0 neutral
//+------------------------------------------------------------------+
int ScoreSignal(int shift, int rates_total,
                const double &open[], const double &high[],
                const double &low[], const double &close[],
                double &atr_out, double &ema200_out)
{
    atr_out    = 0.0;
    ema200_out = 0.0;

    int ns_idx = rates_total - 1 - shift;
    if(ns_idx < 1 || ns_idx >= rates_total) return 0;

    //── L1: SuperTrend ──────────────────────────────────────────────
    int l1 = g_st_dir[ns_idx];  // +1 or -1

    //── ATR & EMA200 (needed for gate + arrows) ─────────────────────
    double atr_b[1], ema200_b[1];
    if(CopyBuffer(h_atr,    0, shift, 1, atr_b)    < 1) return 0;
    if(CopyBuffer(h_ema200, 0, shift, 1, ema200_b) < 1) return 0;
    atr_out    = atr_b[0];
    ema200_out = ema200_b[0];

    // EMA200 master gate
    bool above200 = (close[shift] > ema200_out);
    bool below200 = (close[shift] < ema200_out);
    if(l1 ==  1 && !above200) return 0;
    if(l1 == -1 && !below200) return 0;

    //── L2: MACD histogram direction ────────────────────────────────
    double macd_m[1], macd_s[1];
    if(CopyBuffer(h_macd, 0, shift, 1, macd_m) < 1) return 0;
    if(CopyBuffer(h_macd, 1, shift, 1, macd_s) < 1) return 0;
    int l2 = (macd_m[0] > macd_s[0]) ? 1 : (macd_m[0] < macd_s[0]) ? -1 : 0;

    //── L3: RSI ─────────────────────────────────────────────────────
    double rsi_b[1];
    if(CopyBuffer(h_rsi, 0, shift, 1, rsi_b) < 1) return 0;
    double rsi = rsi_b[0];
    int l3 = (rsi > InpRSI_BullMin) ? 1 : (rsi < InpRSI_BearMax) ? -1 : 0;

    //── L4: EMA20 + candle body ──────────────────────────────────────
    double ema20_b[1];
    if(CopyBuffer(h_ema20, 0, shift, 1, ema20_b) < 1) return 0;
    double ema20 = ema20_b[0];
    double body  = MathAbs(close[shift] - open[shift]);
    double range = high[shift] - low[shift];
    bool strong_candle = (range > 0.0 && (body / range) >= InpBodyRatio);
    bool bull_candle   = (close[shift] > open[shift] && strong_candle);
    bool bear_candle   = (close[shift] < open[shift] && strong_candle);
    bool above_ema20   = (close[shift] > ema20);
    bool below_ema20   = (close[shift] < ema20);
    int l4 = (bull_candle && above_ema20) ? 1 :
             (bear_candle && below_ema20) ? -1 : 0;

    //── Total score ──────────────────────────────────────────────────
    // l1 is always ±1 (never 0 since we passed gate above)
    int score = l1 + l2 + l3 + l4;
    return score;
}

//+------------------------------------------------------------------+
//  BACKTEST
//+------------------------------------------------------------------+
void RunBacktest(int rates_total,
                 const double &open[], const double &high[],
                 const double &low[], const double &close[],
                 const datetime &time[])
{
    g_bt_sig = 0; g_bt_wins = 0; g_bt_losses = 0; g_bt_open = 0;

    int scan_end = MathMin(InpHistoryBars, rates_total - InpBT_MaxWait - InpEMA200 - 5);
    datetime last_bt = 0;

    for(int shift = scan_end; shift >= InpBT_MaxWait + 2; shift--)
    {
        double atr_v, ema200_v;
        int score = ScoreSignal(shift, rates_total, open, high, low, close, atr_v, ema200_v);
        int abs_score = MathAbs(score);
        if(abs_score < InpMinScore) continue;

        int dir = (score > 0) ? 1 : -1;

        // Cooldown
        if(last_bt > 0)
        {
            int gap = (int)Bars(_Symbol, PERIOD_CURRENT, time[shift], last_bt);
            if(gap < InpCooldown) continue;
        }
        last_bt = time[shift];
        if(atr_v <= 0.0) continue;

        double entry = close[shift];
        double sl, tp;
        if(dir == 1)  { sl = entry - atr_v * InpBT_SL; tp = entry + atr_v * InpBT_TP; }
        else          { sl = entry + atr_v * InpBT_SL; tp = entry - atr_v * InpBT_TP; }

        g_bt_sig++;
        bool resolved = false;

        for(int fw = shift - 1; fw >= shift - InpBT_MaxWait && fw >= 0; fw--)
        {
            if(dir == 1)
            {
                if(high[fw] >= tp) { g_bt_wins++;   resolved = true; break; }
                if(low[fw]  <= sl) { g_bt_losses++; resolved = true; break; }
            }
            else
            {
                if(low[fw]  <= tp) { g_bt_wins++;   resolved = true; break; }
                if(high[fw] >= sl) { g_bt_losses++; resolved = true; break; }
            }
        }
        if(!resolved) g_bt_open++;
    }

    int resolved = g_bt_wins + g_bt_losses;
    g_bt_acc  = (resolved > 0) ? (double)g_bt_wins / resolved * 100.0 : 0.0;
    g_bt_done = true;
}

//+------------------------------------------------------------------+
//  OnInit
//+------------------------------------------------------------------+
int OnInit()
{
    SetIndexBuffer(0, Buf_EMA200,  INDICATOR_DATA);
    SetIndexBuffer(1, Buf_ST_Bull, INDICATOR_DATA);
    SetIndexBuffer(2, Buf_ST_Bear, INDICATOR_DATA);
    SetIndexBuffer(3, Buf_EMA20,   INDICATOR_DATA);

    ArrayInitialize(Buf_ST_Bull, EMPTY_VALUE);
    ArrayInitialize(Buf_ST_Bear, EMPTY_VALUE);

    h_atr    = iATR (_Symbol, PERIOD_CURRENT, InpST_Period);
    h_macd   = iMACD(_Symbol, PERIOD_CURRENT,
                     InpMACD_Fast, InpMACD_Slow, InpMACD_Signal, PRICE_CLOSE);
    h_rsi    = iRSI (_Symbol, PERIOD_CURRENT, InpRSI_Period, PRICE_CLOSE);
    h_ema200 = iMA  (_Symbol, PERIOD_CURRENT, InpEMA200, 0, MODE_EMA, PRICE_CLOSE);
    h_ema20  = iMA  (_Symbol, PERIOD_CURRENT, InpEMA20_Period, 0, MODE_EMA, PRICE_CLOSE);

    if(h_atr    == INVALID_HANDLE || h_macd  == INVALID_HANDLE ||
       h_rsi    == INVALID_HANDLE || h_ema200 == INVALID_HANDLE ||
       h_ema20  == INVALID_HANDLE)
    {
        Print("ERROR: handle init failed");
        return INIT_FAILED;
    }

    g_scanned = false;
    g_bt_done = false;
    IndicatorSetString(INDICATOR_SHORTNAME,
        "AI 4-Layer v11.0 | ST+MACD+RSI+EMA20");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//  OnDeinit
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    ObjectsDeleteAll(0, PREFIX);
}

//+------------------------------------------------------------------+
//  OnCalculate
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[],  const double &low[],
                const double &close[], const long &tick_volume[],
                const long &volume[],  const int &spread[])
{
    int min_bars = InpEMA200 + InpST_Period + InpMACD_Slow + 10;
    if(rates_total < min_bars) return 0;

    ArraySetAsSeries(time,  true);
    ArraySetAsSeries(open,  true);
    ArraySetAsSeries(high,  true);
    ArraySetAsSeries(low,   true);
    ArraySetAsSeries(close, true);

    //── Compute SuperTrend (fills g_st_val / g_st_dir) ──────────────
    if(!CalcSuperTrend(high, low, close, rates_total)) return 0;

    //── Fill line plot buffers ───────────────────────────────────────
    {
        int start_i = (prev_calculated > 1) ? prev_calculated - 1 : 0;
        for(int i = start_i; i < rates_total; i++)
        {
            int s = rates_total - 1 - i;  // series index

            double e200[1], e20[1];
            if(CopyBuffer(h_ema200, 0, s, 1, e200) < 1) { Buf_EMA200[i] = EMPTY_VALUE; }
            else Buf_EMA200[i] = e200[0];

            if(CopyBuffer(h_ema20, 0, s, 1, e20) < 1) { Buf_EMA20[i] = EMPTY_VALUE; }
            else Buf_EMA20[i] = e20[0];

            if(i < rates_total)
            {
                if(g_st_dir[i] == 1)
                {
                    Buf_ST_Bull[i] = g_st_val[i];
                    Buf_ST_Bear[i] = EMPTY_VALUE;
                }
                else
                {
                    Buf_ST_Bear[i] = g_st_val[i];
                    Buf_ST_Bull[i] = EMPTY_VALUE;
                }
            }
        }
    }

    //── Run backtest once ────────────────────────────────────────────
    if(InpBacktest && !g_bt_done &&
       rates_total > InpHistoryBars + min_bars + InpBT_MaxWait)
    {
        RunBacktest(rates_total, open, high, low, close, time);
    }

    //── Arrow scan ──────────────────────────────────────────────────
    if(InpShowDots || InpShowDiamonds || InpShowFinal)
    {
        bool do_full = (!g_scanned && rates_total > min_bars + 10);
        int  from    = do_full ? MathMin(InpHistoryBars, rates_total - 3) : 1;
        if(do_full) g_scanned = true;

        datetime last_buy  = 0;
        datetime last_sell = 0;

        // Previous MACD histogram for zero-cross detection
        double macd_prev_m[1], macd_prev_s[1];

        for(int shift = from; shift >= 1; shift--)
        {
            int ns_idx = rates_total - 1 - shift;
            if(ns_idx < 1 || ns_idx >= rates_total) continue;

            datetime bt = time[shift];

            //── L1: ST flip dot (circle, size 1) ────────────────────
            if(InpShowDots)
            {
                bool flipped = (g_st_dir[ns_idx] != g_st_dir[ns_idx - 1]);
                if(flipped)
                {
                    double atr_d[1];
                    if(CopyBuffer(h_atr, 0, shift, 1, atr_d) == 1 && atr_d[0] > 0)
                    {
                        double off = atr_d[0] * 0.3;
                        if(g_st_dir[ns_idx] == 1)
                        {
                            // Bullish flip — circle below bar
                            DrawShape(PREFIX+"D1_"+IntegerToString((int)bt),
                                bt, low[shift] - off,
                                108, clrLime, ANCHOR_TOP, 1);
                        }
                        else
                        {
                            // Bearish flip — circle above bar
                            DrawShape(PREFIX+"D1_"+IntegerToString((int)bt),
                                bt, high[shift] + off,
                                108, clrRed, ANCHOR_BOTTOM, 1);
                        }
                    }
                }
            }

            //── L2: MACD zero-cross diamond (size 1) ────────────────
            if(InpShowDiamonds && shift + 1 < rates_total)
            {
                double macd_m[1], macd_s[1];
                double macd_pm[1], macd_ps[1];
                if(CopyBuffer(h_macd, 0, shift,     1, macd_m)  == 1 &&
                   CopyBuffer(h_macd, 1, shift,     1, macd_s)  == 1 &&
                   CopyBuffer(h_macd, 0, shift + 1, 1, macd_pm) == 1 &&
                   CopyBuffer(h_macd, 1, shift + 1, 1, macd_ps) == 1)
                {
                    double hist_now  = macd_m[0]  - macd_s[0];
                    double hist_prev = macd_pm[0] - macd_ps[0];
                    bool zero_cross_bull = (hist_prev <= 0.0 && hist_now > 0.0);
                    bool zero_cross_bear = (hist_prev >= 0.0 && hist_now < 0.0);

                    if(zero_cross_bull || zero_cross_bear)
                    {
                        double atr_d[1];
                        if(CopyBuffer(h_atr, 0, shift, 1, atr_d) == 1 && atr_d[0] > 0)
                        {
                            double off = atr_d[0] * 0.5;
                            if(zero_cross_bull)
                            {
                                DrawShape(PREFIX+"D2_"+IntegerToString((int)bt),
                                    bt, low[shift] - off,
                                    116, clrAqua, ANCHOR_TOP, 1);
                            }
                            else
                            {
                                DrawShape(PREFIX+"D2_"+IntegerToString((int)bt),
                                    bt, high[shift] + off,
                                    116, clrFuchsia, ANCHOR_BOTTOM, 1);
                            }
                        }
                    }
                }
            }

            //── Final score arrow ────────────────────────────────────
            if(InpShowFinal)
            {
                double atr_v, ema200_v;
                int score = ScoreSignal(shift, rates_total, open, high, low, close,
                                        atr_v, ema200_v);
                int abs_score = MathAbs(score);
                if(abs_score < InpMinScore) continue;
                if(atr_v <= 0.0) continue;

                int dir = (score > 0) ? 1 : -1;

                // Cooldown check
                if(dir == 1)
                {
                    if(last_buy > 0)
                    {
                        int gap = (int)Bars(_Symbol, PERIOD_CURRENT, bt, last_buy);
                        if(gap < InpCooldown) continue;
                    }
                }
                else
                {
                    if(last_sell > 0)
                    {
                        int gap = (int)Bars(_Symbol, PERIOD_CURRENT, bt, last_sell);
                        if(gap < InpCooldown) continue;
                    }
                }

                // Arrow size and color by score tier
                int    arrow_w;
                color  arrow_c;
                if(abs_score == 4)      { arrow_w = 5; arrow_c = (dir==1) ? clrGold   : clrCrimson; }
                else if(abs_score == 3) { arrow_w = 3; arrow_c = (dir==1) ? clrLime   : clrRed;     }
                else                    { arrow_w = 2; arrow_c = (dir==1) ? clrYellow : clrOrange;  }

                double off = atr_v * 0.6;
                string nm = PREFIX + "FA_" + IntegerToString((int)bt);

                if(dir == 1)
                {
                    DrawShape(nm, bt, low[shift] - off,
                        233, arrow_c, ANCHOR_TOP, arrow_w);
                    last_buy = bt;
                }
                else
                {
                    DrawShape(nm, bt, high[shift] + off,
                        234, arrow_c, ANCHOR_BOTTOM, arrow_w);
                    last_sell = bt;
                }
            }
        }
    }

    //── Dashboard ────────────────────────────────────────────────────
    if(InpShowDash)
    {
        double atr_d, ema200_d;
        int score_now = ScoreSignal(1, rates_total, open, high, low, close,
                                    atr_d, ema200_d);
        int abs_now = MathAbs(score_now);
        int dir_now = (score_now > 0) ? 1 : (score_now < 0) ? -1 : 0;

        // Layer values for display
        int ns1 = rates_total - 2;
        int st_now = (ns1 >= 0 && ns1 < rates_total) ? g_st_dir[ns1] : 0;

        double macd_m[1], macd_s[1], rsi_b[1], ema20_b[1];
        CopyBuffer(h_macd, 0, 1, 1, macd_m);
        CopyBuffer(h_macd, 1, 1, 1, macd_s);
        CopyBuffer(h_rsi,  0, 1, 1, rsi_b);
        CopyBuffer(h_ema20,0, 1, 1, ema20_b);

        double rsi_v   = (ArraySize(rsi_b)  > 0) ? rsi_b[0]  : 0.0;
        double ema20_v = (ArraySize(ema20_b)> 0) ? ema20_b[0]: 0.0;
        double macd_v  = (ArraySize(macd_m) > 0) ? macd_m[0] : 0.0;
        double sig_v   = (ArraySize(macd_s) > 0) ? macd_s[0] : 0.0;

        // Layer colors
        color l1_col = (st_now ==  1) ? clrLime  : (st_now == -1) ? clrRed  : clrGray;
        color l2_col = (macd_v > sig_v) ? clrLime : (macd_v < sig_v) ? clrRed : clrGray;
        color l3_col = (rsi_v > InpRSI_BullMin) ? clrLime :
                       (rsi_v < InpRSI_BearMax)  ? clrRed  : clrGray;
        color l4_col = (close[1] > ema20_v) ? clrLime : (close[1] < ema20_v) ? clrRed : clrGray;

        string dir_str;
        color  dir_col;
        if(abs_now >= 4)      { dir_str = (dir_now==1)?">>> STRONG BUY  (4/4) <<<"  :">>> STRONG SELL (4/4) <<<"; dir_col=(dir_now==1)?clrGold:clrCrimson; }
        else if(abs_now == 3) { dir_str = (dir_now==1)?"BUY  (3/4 layers)"           :"SELL (3/4 layers)";          dir_col=(dir_now==1)?clrLime:clrRed; }
        else if(abs_now == 2) { dir_str = (dir_now==1)?"WEAK BUY  (2/4)"             :"WEAK SELL (2/4)";            dir_col=clrYellow; }
        else                  { dir_str = "NO SIGNAL — waiting...";                                                   dir_col=clrDimGray; }

        int xr = 5;
        SetLabel(PREFIX+"H0", "=== AI 4-LAYER v11.0 ===",     xr, 8,  clrWhite, 9);
        SetLabel(PREFIX+"H1",
            StringFormat("%s M5  Price=%.2f  ATR=%.2f", _Symbol, close[0], atr_d),
            xr, 23, clrSilver, 8);

        SetLabel(PREFIX+"L1",
            StringFormat("L1 SuperTrend(ATR%d x%.1f)  %s",
                InpST_Period, InpST_Mult,
                st_now==1?"[BULL]":st_now==-1?"[BEAR]":"[-]"),
            xr, 38, l1_col, 8);

        SetLabel(PREFIX+"L2",
            StringFormat("L2 MACD(%d,%d,%d)  hist=%.4f  %s",
                InpMACD_Fast, InpMACD_Slow, InpMACD_Signal,
                macd_v - sig_v,
                macd_v > sig_v ? "[BULL]" : macd_v < sig_v ? "[BEAR]" : "[FLAT]"),
            xr, 53, l2_col, 8);

        SetLabel(PREFIX+"L3",
            StringFormat("L3 RSI(%d) = %.1f  %s",
                InpRSI_Period, rsi_v,
                rsi_v > InpRSI_BullMin ? "[BULL >55]" :
                rsi_v < InpRSI_BearMax  ? "[BEAR <45]" : "[NEUTRAL]"),
            xr, 68, l3_col, 8);

        SetLabel(PREFIX+"L4",
            StringFormat("L4 EMA20=%.2f  Price %s EMA20",
                ema20_v, close[1] > ema20_v ? "ABOVE" : "BELOW"),
            xr, 83, l4_col, 8);

        SetLabel(PREFIX+"SG", dir_str, xr, 100, dir_col, 11);

        SetLabel(PREFIX+"E2",
            StringFormat("EMA200=%.2f  Price %s gate",
                ema200_d, close[1] > ema200_d ? "ABOVE" : "BELOW"),
            xr, 115, close[1] > ema200_d ? clrGold : clrOrangeRed, 8);

        // Backtest results
        if(g_bt_done && g_bt_sig > 0)
        {
            color bc = (g_bt_acc >= 60.0) ? clrLime :
                       (g_bt_acc >= 50.0) ? clrYellow : clrRed;
            SetLabel(PREFIX+"B0",
                StringFormat("BACKTEST %d bars: %d signals", InpHistoryBars, g_bt_sig),
                xr, 130, clrWhite, 8);
            SetLabel(PREFIX+"B1",
                StringFormat("W:%d  L:%d  Open:%d  Acc=%.1f%%",
                    g_bt_wins, g_bt_losses, g_bt_open, g_bt_acc),
                xr, 143, bc, 10);
        }
        else if(g_bt_done)
        {
            SetLabel(PREFIX+"B0", "BACKTEST: 0 signals in range", xr, 130, clrYellow, 8);
        }
        else
        {
            SetLabel(PREFIX+"B0", "BACKTEST: loading...", xr, 130, clrGray, 8);
        }

        SetLabel(PREFIX+"FT",
            StringFormat("MinScore=%d  Cooldown=%d bars  v11.0",
                InpMinScore, InpCooldown),
            xr, 158, clrDimGray, 7);
    }

    return rates_total;
}
//+------------------------------------------------------------------+
