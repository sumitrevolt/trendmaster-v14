//+------------------------------------------------------------------+
//|  AI_TradingView_Replica_v1.mq5                                   |
//|  Replicates TradingView Setup on MT5:                            |
//|  L1: MACD Overlay (12,26,9) + SMA89                              |
//|  L2: SuperBollingerTrend (BB 12,2) — volatility engine           |
//|  L3: Phoenix (Stochastic wSMD 12,31,2,099)                       |
//|  L4: LuxAlgo ORB (09:30-09:45 UTC-5) + EMA20 Gate               |
//|  VISUALS: Session boxes, ORH/ORL lines, ZigZag, colored arrows   |
//|  ALERTS: Sound + MT5 alert when 2+ indicators agree              |
//+------------------------------------------------------------------+
#property copyright "AI Trading Agents - TV Replica v1.0"
#property version   "1.00"
#property description "TradingView Replica: MACD+SBT+ORB+Phoenix | Session Boxes | ORH/ORL | ZigZag"
#property indicator_chart_window
#property indicator_buffers 6
#property indicator_plots   6

//── PLOT 1: EMA 20 (orange line — LuxAlgo base) ─────────────────────
#property indicator_label1  "EMA 20"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDarkOrange
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2

//── PLOT 2: SMA 89 (blue line — trend gate) ──────────────────────────
#property indicator_label2  "SMA 89"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrDodgerBlue
#property indicator_style2  STYLE_SOLID
#property indicator_width2  2

//── PLOT 3: BUY Arrow Normal ─────────────────────────────────────────
#property indicator_label3  "BUY (2 ind)"
#property indicator_type3   DRAW_ARROW
#property indicator_color3  clrLime
#property indicator_style3  STYLE_SOLID
#property indicator_width3  3

//── PLOT 4: SELL Arrow Normal ────────────────────────────────────────
#property indicator_label4  "SELL (2 ind)"
#property indicator_type4   DRAW_ARROW
#property indicator_color4  clrRed
#property indicator_style4  STYLE_SOLID
#property indicator_width4  3

//── PLOT 5: BUY Arrow Strong (3-4 ind) ──────────────────────────────
#property indicator_label5  "STRONG BUY (3+)"
#property indicator_type5   DRAW_ARROW
#property indicator_color5  clrAqua
#property indicator_style5  STYLE_SOLID
#property indicator_width5  5

//── PLOT 6: SELL Arrow Strong ────────────────────────────────────────
#property indicator_label6  "STRONG SELL (3+)"
#property indicator_type6   DRAW_ARROW
#property indicator_color6  clrOrangeRed
#property indicator_style6  STYLE_SOLID
#property indicator_width6  5

//── BUFFERS ──────────────────────────────────────────────────────────
double Buf_EMA20[];
double Buf_SMA89[];
double Buf_BuyNorm[];
double Buf_SellNorm[];
double Buf_BuyStrong[];
double Buf_SellStrong[];

//── INPUTS ───────────────────────────────────────────────────────────
input group "=== L1: MACD ==="
input int    MACD_Fast   = 10;
input int    MACD_Slow   = 21;
input int    MACD_Signal = 10;

input group "=== L2: SuperBollingerTrend ==="
input int    BB_Period   = 12;
input double BB_Dev      = 2.0;

input group "=== L3: Phoenix (Stoch approx) ==="
input int    Stoch_K     = 12;
input int    Stoch_D     = 31;
input int    Stoch_Slow  = 2;

input group "=== L4: ORB (LuxAlgo) ==="
input int    ORB_StartHour = 9;
input int    ORB_StartMin  = 30;
input int    ORB_EndHour   = 9;
input int    ORB_EndMin    = 45;
input int    EMA20_Period  = 20;
input int    SMA89_Period  = 89;

input group "=== Sessions (background color boxes) ==="
input bool   ShowLondonBox  = true;   // 07:00-12:00 UTC
input bool   ShowNYBox       = true;   // 13:00-20:00 UTC
input bool   ShowAsianBox    = false;  // 00:00-07:00 UTC (usually skip)
input color  LondonColor     = 0xFFE8F4FD;   // light blue
input color  NYColor         = 0xFFFFE8E8;   // light pink/red
input color  AsianColor      = 0xFFEEFFEE;   // light green

input group "=== Signal / Alerts ==="
input int    MinScore        = 2;    // 2 = trade, 3+ = double
input int    CooldownBars    = 6;
input bool   PlaySound_      = true;
input bool   SendPushAlert_  = true;
input bool   SendMT5Alert_   = true;
input bool   ShowORHORL      = true;  // Draw ORH/ORL horizontal lines
input bool   ShowZigZag      = true;  // Draw ZigZag pivot labels
input bool   ShowDashboard   = true;

//── HANDLES ──────────────────────────────────────────────────────────
int h_macd, h_bb, h_stoch, h_ema20, h_sma89;

//── STATE ─────────────────────────────────────────────────────────────
double ORH = 0, ORL = 1e9;
bool   or_locked = false;
int    or_day    = -1;
int    last_alert_bar = -999;

// ZigZag last pivot tracking
double zz_last_high = 0, zz_last_low = 1e9;
int    zz_last_high_bar = -1, zz_last_low_bar = -1;

#define PRE "TVR_"

//+------------------------------------------------------------------+
void DrawHLine(string nm, double price, color c, int width, ENUM_LINE_STYLE style)
{
    if(ObjectFind(0, nm) >= 0) ObjectDelete(0, nm);
    ObjectCreate(0, nm, OBJ_HLINE, 0, 0, price);
    ObjectSetInteger(0, nm, OBJPROP_COLOR,     c);
    ObjectSetInteger(0, nm, OBJPROP_WIDTH,     width);
    ObjectSetInteger(0, nm, OBJPROP_STYLE,     style);
    ObjectSetInteger(0, nm, OBJPROP_SELECTABLE,false);
    ObjectSetInteger(0, nm, OBJPROP_BACK,      true);
}

void DrawRect(string nm, datetime t1, datetime t2, double p1, double p2,
              color fill_col, color border_col, int opacity = 10)
{
    if(ObjectFind(0, nm) >= 0) return;
    ObjectCreate(0, nm, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
    ObjectSetInteger(0, nm, OBJPROP_COLOR,       border_col);
    ObjectSetInteger(0, nm, OBJPROP_BGCOLOR,     fill_col);
    ObjectSetInteger(0, nm, OBJPROP_FILL,        true);
    ObjectSetInteger(0, nm, OBJPROP_BACK,        true);
    ObjectSetInteger(0, nm, OBJPROP_SELECTABLE,  false);
    ObjectSetInteger(0, nm, OBJPROP_WIDTH,       1);
    ObjectSetInteger(0, nm, OBJPROP_STYLE,       STYLE_SOLID);
}

void DrawText(string nm, string txt, datetime t, double price, color c, int sz = 7,
              ENUM_ANCHOR_POINT anchor = ANCHOR_LEFT_UPPER)
{
    if(ObjectFind(0, nm) >= 0) ObjectDelete(0, nm);
    ObjectCreate(0, nm, OBJ_TEXT, 0, t, price);
    ObjectSetString (0, nm, OBJPROP_TEXT,      txt);
    ObjectSetInteger(0, nm, OBJPROP_COLOR,     c);
    ObjectSetInteger(0, nm, OBJPROP_FONTSIZE,  sz);
    ObjectSetInteger(0, nm, OBJPROP_ANCHOR,    anchor);
    ObjectSetInteger(0, nm, OBJPROP_SELECTABLE,false);
    ObjectSetInteger(0, nm, OBJPROP_BACK,      false);
}

void SetLabel(string nm, string txt, int x, int y, color c, int sz = 9)
{
    if(ObjectFind(0, nm) < 0) ObjectCreate(0, nm, OBJ_LABEL, 0, 0, 0);
    ObjectSetString (0, nm, OBJPROP_TEXT,      txt);
    ObjectSetInteger(0, nm, OBJPROP_XDISTANCE, x);
    ObjectSetInteger(0, nm, OBJPROP_YDISTANCE, y);
    ObjectSetInteger(0, nm, OBJPROP_COLOR,     c);
    ObjectSetInteger(0, nm, OBJPROP_FONTSIZE,  sz);
    ObjectSetInteger(0, nm, OBJPROP_CORNER,    CORNER_RIGHT_UPPER);
    ObjectSetInteger(0, nm, OBJPROP_ANCHOR,    ANCHOR_RIGHT_UPPER);
    ObjectSetInteger(0, nm, OBJPROP_SELECTABLE,false);
}

//+------------------------------------------------------------------+
int OnInit()
{
    SetIndexBuffer(0, Buf_EMA20,     INDICATOR_DATA);
    SetIndexBuffer(1, Buf_SMA89,     INDICATOR_DATA);
    SetIndexBuffer(2, Buf_BuyNorm,   INDICATOR_DATA);
    SetIndexBuffer(3, Buf_SellNorm,  INDICATOR_DATA);
    SetIndexBuffer(4, Buf_BuyStrong, INDICATOR_DATA);
    SetIndexBuffer(5, Buf_SellStrong,INDICATOR_DATA);

    for(int i = 0; i < 6; i++)
        PlotIndexSetDouble(i, PLOT_EMPTY_VALUE, 0.0);

    PlotIndexSetInteger(2, PLOT_ARROW, 233);   // up arrow
    PlotIndexSetInteger(3, PLOT_ARROW, 234);   // down arrow
    PlotIndexSetInteger(4, PLOT_ARROW, 241);   // big up
    PlotIndexSetInteger(5, PLOT_ARROW, 242);   // big down

    h_macd  = iMACD      (NULL, 0, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE);
    h_bb    = iBands     (NULL, 0, BB_Period, 0, BB_Dev, PRICE_CLOSE);
    h_stoch = iStochastic(NULL, 0, Stoch_K, Stoch_D, Stoch_Slow, MODE_SMA, STO_LOWHIGH);
    h_ema20 = iMA        (NULL, 0, EMA20_Period, 0, MODE_EMA, PRICE_CLOSE);
    h_sma89 = iMA        (NULL, 0, SMA89_Period, 0, MODE_SMA, PRICE_CLOSE);

    if(h_macd  == INVALID_HANDLE || h_bb    == INVALID_HANDLE ||
       h_stoch == INVALID_HANDLE || h_ema20 == INVALID_HANDLE ||
       h_sma89 == INVALID_HANDLE)
    {
        Print("ERROR: Indicator handle failed");
        return INIT_FAILED;
    }

    IndicatorSetString(INDICATOR_SHORTNAME,
        "AI TV-REPLICA v1.0 [MACD+SBT+ORB+PHX]");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    ObjectsDeleteAll(0, PRE);
}

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double   &open[],
                const double   &high[],
                const double   &low[],
                const double   &close[],
                const long     &tick_volume[],
                const long     &volume[],
                const int      &spread[])
{
    if(rates_total < SMA89_Period + 30) return 0;

    ArraySetAsSeries(time,  true);
    ArraySetAsSeries(open,  true);
    ArraySetAsSeries(high,  true);
    ArraySetAsSeries(low,   true);
    ArraySetAsSeries(close, true);

    int scan_from = (prev_calculated < 2) ? rates_total - 2 : rates_total - prev_calculated + 1;
    if(scan_from >= rates_total - 1) scan_from = rates_total - 2;

    //── Today's ORH/ORL reset ────────────────────────────────────────
    MqlDateTime dt0;
    TimeToStruct(time[0], dt0);
    if(dt0.day_of_year != or_day)
    {
        or_day    = dt0.day_of_year;
        ORH       = 0;
        ORL       = 1e9;
        or_locked = false;
    }

    //── Main Bar Loop ─────────────────────────────────────────────────
    for(int i = scan_from; i >= 1; i--)
    {
        Buf_BuyNorm[i]    = 0;
        Buf_SellNorm[i]   = 0;
        Buf_BuyStrong[i]  = 0;
        Buf_SellStrong[i] = 0;

        //── Fill EMA20 and SMA89 buffers ─────────────────────────────
        double e20[1], s89[1];
        if(CopyBuffer(h_ema20, 0, i, 1, e20) == 1) Buf_EMA20[i] = e20[0]; else Buf_EMA20[i] = 0;
        if(CopyBuffer(h_sma89, 0, i, 1, s89) == 1) Buf_SMA89[i] = s89[0]; else Buf_SMA89[i] = 0;

        //── Session Box Drawing (once per new day) ───────────────────
        MqlDateTime dt;
        TimeToStruct(time[i], dt);
        int bar_min  = dt.hour * 60 + dt.min;
        int cur_day  = dt.day_of_year;

        // Draw session rectangles (only for bars before current bar)
        if(i >= 2)
        {
            // London open: 07:00 UTC = 420 min | close: 12:00 = 720 min
            if(ShowLondonBox && bar_min == 420)
            {
                // Find end of london session (12:00)
                string nm = PRE + "LON_" + IntegerToString(cur_day);
                datetime t_start = time[i];
                datetime t_end   = t_start + (5 * 3600); // +5 hours
                DrawRect(nm, t_start, t_end,
                         high[i] + 20, low[i] - 20,    // rough, will be overdrawn by price
                         LondonColor, clrSteelBlue);
            }
            // NY session: 13:00 UTC = 780 min | close: 20:00 = 1200 min
            if(ShowNYBox && bar_min == 780)
            {
                string nm = PRE + "NY_" + IntegerToString(cur_day);
                datetime t_start = time[i];
                datetime t_end   = t_start + (7 * 3600); // +7 hours
                DrawRect(nm, t_start, t_end,
                         high[i] + 20, low[i] - 20,
                         NYColor, clrIndianRed);
            }
            // Asian session: 00:00 UTC = 0 min | close: 07:00 = 420 min
            if(ShowAsianBox && bar_min == 0)
            {
                string nm = PRE + "ASIA_" + IntegerToString(cur_day);
                datetime t_start = time[i];
                datetime t_end   = t_start + (7 * 3600);
                DrawRect(nm, t_start, t_end,
                         high[i] + 20, low[i] - 20,
                         AsianColor, clrSeaGreen);
            }
        }

        //── ORB Tracking ─────────────────────────────────────────────
        int or_start = ORB_StartHour * 60 + ORB_StartMin;
        int or_end   = ORB_EndHour   * 60 + ORB_EndMin;

        if(cur_day != or_day)
        {
            or_day = cur_day; ORH = 0; ORL = 1e9; or_locked = false;
        }
        if(!or_locked && bar_min >= or_start && bar_min < or_end)
        {
            if(high[i] > ORH) ORH = high[i];
            if(low[i]  < ORL) ORL = low[i];
        }
        if(!or_locked && bar_min >= or_end && ORH > 0)
        {
            or_locked = true;
            // Draw ORH/ORL lines
            if(ShowORHORL)
            {
                DrawHLine(PRE + "ORH_" + IntegerToString(cur_day), ORH,
                          clrGold, 1, STYLE_DOT);
                DrawHLine(PRE + "ORL_" + IntegerToString(cur_day), ORL,
                          clrGold, 1, STYLE_DOT);
                DrawText(PRE + "ORH_T_" + IntegerToString(cur_day),
                         "ORH", time[i], ORH, clrGold, 7);
                DrawText(PRE + "ORL_T_" + IntegerToString(cur_day),
                         "ORL", time[i], ORL, clrGold, 7);
            }
        }

        //── Copy indicator buffers ────────────────────────────────────
        double macd_m[2], macd_s[2], bb_u[1], bb_l[1], bb_mid[1];
        double stk[2], std_[2];

        if(CopyBuffer(h_macd,  0, i, 2, macd_m)  < 2) continue;
        if(CopyBuffer(h_macd,  1, i, 2, macd_s)  < 2) continue;
        if(CopyBuffer(h_bb,    1, i, 1, bb_u)    < 1) continue;
        if(CopyBuffer(h_bb,    2, i, 1, bb_l)    < 1) continue;
        if(CopyBuffer(h_bb,    0, i, 1, bb_mid)  < 1) continue;
        if(CopyBuffer(h_stoch, 0, i, 2, stk)     < 2) continue;
        if(CopyBuffer(h_stoch, 1, i, 2, std_)    < 2) continue;

        double sma_now = Buf_SMA89[i];
        double ema_now = Buf_EMA20[i];

        //── L1: MACD ─────────────────────────────────────────────────
        int macd_dir = 0;
        bool macd_cross_up = (macd_m[0] > macd_s[0]) && (macd_m[1] <= macd_s[1]);
        bool macd_cross_dn = (macd_m[0] < macd_s[0]) && (macd_m[1] >= macd_s[1]);
        bool above_sma = close[i] > sma_now;

        if(macd_cross_up && above_sma)                             macd_dir =  1;
        else if(macd_cross_dn && !above_sma)                       macd_dir = -1;
        else if(macd_m[0] > macd_s[0] && above_sma)               macd_dir =  1;
        else if(macd_m[0] < macd_s[0] && !above_sma)              macd_dir = -1;

        //── L2: SuperBollingerTrend ───────────────────────────────────
        int sbt_dir = 0;
        bool price_above = close[i] > bb_mid[0];
        bool rising  = close[i] > close[i+1] && close[i+1] > close[i+2];
        bool falling = close[i] < close[i+1] && close[i+1] < close[i+2];
        bool bb_u_touch = close[i] >= bb_u[0] * 0.995;
        bool bb_l_touch = close[i] <= bb_l[0] * 1.005;

        if(price_above && rising)              sbt_dir =  1;
        else if(!price_above && falling)       sbt_dir = -1;
        if(bb_l_touch && rising)               sbt_dir =  1;
        if(bb_u_touch && falling)              sbt_dir = -1;

        //── L3: Phoenix (Stochastic) ──────────────────────────────────
        int phx_dir = 0;
        bool stk_cup = stk[0] > std_[0] && stk[1] <= std_[1];
        bool stk_cdn = stk[0] < std_[0] && stk[1] >= std_[1];
        bool stk_os  = stk[0] < 25;
        bool stk_ob  = stk[0] > 75;

        if(stk_cup && stk[0] < 50)        phx_dir =  1;
        else if(stk_cdn && stk[0] > 50)   phx_dir = -1;
        else if(stk_os && rising)          phx_dir =  1;
        else if(stk_ob && falling)         phx_dir = -1;

        //── L4: ORB + EMA20 Gate ────────────────────────────────────
        int orb_dir = 0;
        double orm = (ORH + ORL) / 2.0;
        if(or_locked && ORH > 0 && ORL < 1e8)
        {
            bool brk_up = close[i] > ORH && close[i+1] <= ORH;
            bool brk_dn = close[i] < ORL && close[i+1] >= ORL;
            if(brk_up)                 orb_dir =  1;
            else if(brk_dn)            orb_dir = -1;
            else if(close[i] > ORH)    orb_dir =  1;
            else if(close[i] < ORL)    orb_dir = -1;
            else if(close[i] > orm)    orb_dir =  1;
            else if(close[i] < orm)    orb_dir = -1;
        }

        // EMA20 gate: only BUY above EMA20, only SELL below
        if(orb_dir ==  1 && close[i] < ema_now) orb_dir = 0;
        if(orb_dir == -1 && close[i] > ema_now) orb_dir = 0;

        //── ZigZag Pivot Labels ──────────────────────────────────────
        if(ShowZigZag && i >= 3 && i <= rates_total - 5)
        {
            // Local high pivot
            if(high[i] > high[i+1] && high[i] > high[i+2] &&
               high[i] > high[i-1] && high[i] > high[i-2])
            {
                if(high[i] > zz_last_high * 1.001 || zz_last_high_bar < 0)
                {
                    zz_last_high = high[i]; zz_last_high_bar = i;
                    DrawText(PRE + "ZH_" + IntegerToString((int)time[i]),
                             "short\n-0.2", time[i], high[i] + 3.0,
                             clrTomato, 7);
                }
            }
            // Local low pivot
            if(low[i] < low[i+1] && low[i] < low[i+2] &&
               low[i] < low[i-1] && low[i] < low[i-2])
            {
                if(low[i] < zz_last_low * 0.999 || zz_last_low_bar < 0)
                {
                    zz_last_low = low[i]; zz_last_low_bar = i;
                    DrawText(PRE + "ZL_" + IntegerToString((int)time[i]),
                             "long\n+0.2", time[i], low[i] - 3.0,
                             clrLimeGreen, 7, ANCHOR_LEFT_LOWER);
                }
            }
        }

        //── Count Agreements ─────────────────────────────────────────
        int buy_count  = (macd_dir==1?1:0) + (sbt_dir==1?1:0) +
                         (orb_dir==1?1:0)  + (phx_dir==1?1:0);
        int sell_count = (macd_dir==-1?1:0) + (sbt_dir==-1?1:0) +
                         (orb_dir==-1?1:0)  + (phx_dir==-1?1:0);
        int agree = MathMax(buy_count, sell_count);
        int dir   = buy_count > sell_count ? 1 : sell_count > buy_count ? -1 : 0;

        if(agree < MinScore || dir == 0) continue;

        double bb_range = bb_u[0] - bb_l[0];
        double off      = bb_range * 0.25;
        if(off < 1.0) off = 1.0;

        if(dir == 1)
        {
            if(agree >= 3) Buf_BuyStrong[i] = low[i] - off;
            else           Buf_BuyNorm[i]   = low[i] - off;
        }
        else
        {
            if(agree >= 3) Buf_SellStrong[i] = high[i] + off;
            else           Buf_SellNorm[i]   = high[i] + off;
        }

        //── Alert on current forming bar ────────────────────────────
        if(i == 1 && (rates_total - 2) > last_alert_bar + CooldownBars)
        {
            last_alert_bar = rates_total - 2;
            string d    = dir == 1 ? "BUY" : "SELL";
            string lot  = agree >= 3 ? "DOUBLE LOT 💰💰" : "NORMAL LOT";
            string ind  = "";
            if(macd_dir == dir) ind += "MACD ";
            if(sbt_dir  == dir) ind += "SBT ";
            if(orb_dir  == dir) ind += "ORB ";
            if(phx_dir  == dir) ind += "Phoenix ";
            string msg = StringFormat("🔔 %s %s | %s | %d/4: %s| Price: %.2f",
                                      _Symbol, d, lot, agree, ind, close[0]);
            if(PlaySound_)
            {
                if(agree >= 3) PlaySound("alert2.wav");
                else           PlaySound("alert.wav");
            }
            if(SendMT5Alert_) Alert(msg);
            if(SendPushAlert_) SendNotification(msg);
            Print(msg);
        }
    }

    //── EMA20 / SMA89 for bar 0 ──────────────────────────────────────
    double e20_0[1], s89_0[1];
    if(CopyBuffer(h_ema20, 0, 0, 1, e20_0) == 1) Buf_EMA20[0] = e20_0[0];
    if(CopyBuffer(h_sma89, 0, 0, 1, s89_0) == 1) Buf_SMA89[0] = s89_0[0];

    //── Dashboard ────────────────────────────────────────────────────
    if(ShowDashboard)
    {
        double macd_d[1], macd_s_d[1], stk_d[1], bb_u_d[1], bb_l_d[1], bb_m_d[1];
        CopyBuffer(h_macd,  0, 1, 1, macd_d);
        CopyBuffer(h_macd,  1, 1, 1, macd_s_d);
        CopyBuffer(h_stoch, 0, 1, 1, stk_d);
        CopyBuffer(h_bb,    1, 1, 1, bb_u_d);
        CopyBuffer(h_bb,    2, 1, 1, bb_l_d);
        CopyBuffer(h_bb,    0, 1, 1, bb_m_d);

        double rsi_macd = ArraySize(macd_d)     > 0 ? macd_d[0]   : 0;
        double rsi_sig  = ArraySize(macd_s_d)   > 0 ? macd_s_d[0] : 0;
        double stk_val  = ArraySize(stk_d)      > 0 ? stk_d[0]    : 50;
        double bb_u_v   = ArraySize(bb_u_d)     > 0 ? bb_u_d[0]   : 0;
        double bb_l_v   = ArraySize(bb_l_d)     > 0 ? bb_l_d[0]   : 0;
        double bb_m_v   = ArraySize(bb_m_d)     > 0 ? bb_m_d[0]   : 0;

        color l1c = rsi_macd > rsi_sig ? clrLime : clrRed;
        color l2c = close[0] > bb_m_v  ? clrLime : clrRed;
        color l3c = stk_val  < 30      ? clrLime : stk_val > 70 ? clrRed : clrGray;
        color l4c = or_locked && ORH > 0 ?
                    (close[0] > ORH ? clrLime : close[0] < ORL ? clrRed : clrGray) : clrGray;

        int x = 5;
        SetLabel(PRE+"H0", "=== AI SNIPER v5.0 — TV-MATCH ===", x,  8, clrWhite, 10);
        SetLabel(PRE+"H1", StringFormat("XAUUSD  M5  %.2f", close[0]), x, 24, clrSilver, 8);
        SetLabel(PRE+"L1", StringFormat("L1 HTF Trend   [HTF ~]  M30 %s",
            rsi_macd > rsi_sig ? "BULL" : "BEAR"), x, 40, l1c, 8);
        SetLabel(PRE+"L2", StringFormat("L2 Volatility  [ATR]  BB Width=%.2f",
            bb_u_v - bb_l_v), x, 55, l2c, 8);
        SetLabel(PRE+"L3", StringFormat("L3 Candle:Pin  [STOCH %.1f]", stk_val),
            x, 70, l3c, 8);
        SetLabel(PRE+"L4", StringFormat("L4 EMA%d/21  [%s]  EMA=%.2f",
            EMA20_Period, Buf_EMA20[0] > 0 && close[0] > Buf_EMA20[0] ? "NEUTRAL" : "BELOW",
            Buf_EMA20[0]), x, 85, l4c, 8);
        SetLabel(PRE+"L5", StringFormat("L5 RSI14   [RSI]  Stoch=%.1f", stk_val),
            x, 100, l3c, 8);
        SetLabel(PRE+"ORH_L", StringFormat("ORH %.2f  |  ORL %.2f  [%s]",
            ORH, ORL, or_locked ? "LOCKED" : "BUILDING..."),
            x, 116, clrGold, 8);
        SetLabel(PRE+"BB_L", StringFormat("BB(%d,%.1f)  Upper=%.2f  Lower=%.2f",
            BB_Period, BB_Dev, bb_u_v, bb_l_v),
            x, 131, clrSkyBlue, 8);
        SetLabel(PRE+"FT", StringFormat("MinScore=%d  | v1.0 [TV-MATCH]", MinScore),
            x, 146, clrDimGray, 7);
    }

    return rates_total;
}
//+------------------------------------------------------------------+
