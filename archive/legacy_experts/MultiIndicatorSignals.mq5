//+------------------------------------------------------------------+
//|  Multi-Indicator Signal Display — Sumit's TV Indicators         |
//|  Shows MACD + SBT + ORB + Phoenix signals on MT5 chart          |
//|  Plays sound + sends MT5 push alert when 2+ indicators agree    |
//+------------------------------------------------------------------+
#property copyright "Automated Trading Project"
#property version   "1.0"
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4

// ── Arrow buffers ──
#property indicator_label1  "BUY Signal (2 ind)"
#property indicator_type1   DRAW_ARROW
#property indicator_color1  clrLime
#property indicator_style1  STYLE_SOLID
#property indicator_width1  3

#property indicator_label2  "SELL Signal (2 ind)"
#property indicator_type2   DRAW_ARROW
#property indicator_color2  clrRed
#property indicator_style2  STYLE_SOLID
#property indicator_width2  3

#property indicator_label3  "BUY Signal (3+ ind DOUBLE)"
#property indicator_type3   DRAW_ARROW
#property indicator_color3  clrAqua
#property indicator_style3  STYLE_SOLID
#property indicator_width3  5

#property indicator_label4  "SELL Signal (3+ ind DOUBLE)"
#property indicator_type4   DRAW_ARROW
#property indicator_color4  clrOrange
#property indicator_style4  STYLE_SOLID
#property indicator_width4  5

double BuyNormal[];
double SellNormal[];
double BuyDouble[];
double SellDouble[];

// ── Inputs ──
input int    MACD_Fast       = 12;
input int    MACD_Slow       = 26;
input int    MACD_Signal     = 9;
input int    SMA_Period      = 89;
input int    BB_Period       = 12;
input double BB_Dev          = 2.0;
input int    Stoch_K         = 12;
input int    Stoch_D         = 3;
input int    ORB_StartHour   = 9;    // 09:30 local (UTC-5)
input int    ORB_StartMin    = 30;
input int    ORB_EndHour     = 9;
input int    ORB_EndMin      = 45;
input bool   PlaySound       = true;
input string AlertSound      = "alert.wav";
input bool   SendPushAlert   = true;
input bool   SendMT5Alert    = true;
input int    CooldownBars    = 6;    // bars between alerts

// ── Indicator handles ──
int macd_handle;
int bb_handle;
int stoch_handle;
int sma_handle;

// ── State ──
int    last_alert_bar = -999;
double ORH = 0, ORL = 1e9;
bool   or_locked = false;
int    or_day = -1;

//+------------------------------------------------------------------+
int OnInit()
  {
   // Arrow buffers
   SetIndexBuffer(0, BuyNormal,  INDICATOR_DATA);
   SetIndexBuffer(1, SellNormal, INDICATOR_DATA);
   SetIndexBuffer(2, BuyDouble,  INDICATOR_DATA);
   SetIndexBuffer(3, SellDouble, INDICATOR_DATA);
   for(int i=0; i<4; i++) PlotIndexSetDouble(i, PLOT_EMPTY_VALUE, 0);

   // Arrow codes
   PlotIndexSetInteger(0, PLOT_ARROW, 233);   // up arrow (normal buy)
   PlotIndexSetInteger(1, PLOT_ARROW, 234);   // down arrow (normal sell)
   PlotIndexSetInteger(2, PLOT_ARROW, 241);   // big up arrow (double buy)
   PlotIndexSetInteger(3, PLOT_ARROW, 242);   // big down arrow (double sell)

   // Create indicator handles
   macd_handle  = iMACD(NULL, 0, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE);
   bb_handle    = iBands(NULL, 0, BB_Period, 0, BB_Dev, PRICE_CLOSE);
   stoch_handle = iStochastic(NULL, 0, Stoch_K, Stoch_D, 1, MODE_SMA, STO_LOWHIGH);
   sma_handle   = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE);

   if(macd_handle == INVALID_HANDLE || bb_handle == INVALID_HANDLE ||
      stoch_handle == INVALID_HANDLE || sma_handle == INVALID_HANDLE)
     {
      Print("Failed to create indicator handles!");
      return INIT_FAILED;
     }

   IndicatorSetString(INDICATOR_SHORTNAME,
     "MultiInd[MACD+SBT+ORB+PHX] 2sig=Trade 3sig=Double");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   if(rates_total < 50) return 0;

   int start = MathMax(prev_calculated - 1, 50);

   // Copy indicator data
   double macd_main[], macd_sig[], bb_upper[], bb_lower[], bb_mid[];
   double stoch_k[], stoch_d[], sma[];

   int copy_len = rates_total - start;
   if(copy_len <= 0) return rates_total;

   if(CopyBuffer(macd_handle,  0, 0, copy_len, macd_main) <= 0) return prev_calculated;
   if(CopyBuffer(macd_handle,  1, 0, copy_len, macd_sig)  <= 0) return prev_calculated;
   if(CopyBuffer(bb_handle,    1, 0, copy_len, bb_upper)  <= 0) return prev_calculated;
   if(CopyBuffer(bb_handle,    2, 0, copy_len, bb_lower)  <= 0) return prev_calculated;
   if(CopyBuffer(bb_handle,    0, 0, copy_len, bb_mid)    <= 0) return prev_calculated;
   if(CopyBuffer(stoch_handle, 0, 0, copy_len, stoch_k)   <= 0) return prev_calculated;
   if(CopyBuffer(stoch_handle, 1, 0, copy_len, stoch_d)   <= 0) return prev_calculated;
   if(CopyBuffer(sma_handle,   0, 0, copy_len, sma)       <= 0) return prev_calculated;

   ArraySetAsSeries(macd_main, true);
   ArraySetAsSeries(macd_sig,  true);
   ArraySetAsSeries(bb_upper,  true);
   ArraySetAsSeries(bb_lower,  true);
   ArraySetAsSeries(bb_mid,    true);
   ArraySetAsSeries(stoch_k,   true);
   ArraySetAsSeries(stoch_d,   true);
   ArraySetAsSeries(sma,       true);
   ArraySetAsSeries(time,      true);
   ArraySetAsSeries(high,      true);
   ArraySetAsSeries(low,       true);
   ArraySetAsSeries(close,     true);

   for(int i = start; i < rates_total - 1; i++)
     {
      int idx = rates_total - 1 - i;   // index into copied arrays (newest=0)
      if(idx < 0 || idx >= copy_len - 1) continue;

      BuyNormal[i]  = 0;
      SellNormal[i] = 0;
      BuyDouble[i]  = 0;
      SellDouble[i] = 0;

      // ── ORB Session Tracking ──
      MqlDateTime dt;
      TimeToStruct(time[i], dt);
      int cur_day = dt.day_of_year;
      int bar_min = dt.hour * 60 + dt.min;
      int or_start = ORB_StartHour * 60 + ORB_StartMin;
      int or_end   = ORB_EndHour   * 60 + ORB_EndMin;

      if(cur_day != or_day)
        {
         or_day    = cur_day;
         ORH       = 0;
         ORL       = 1e9;
         or_locked = false;
        }
      if(!or_locked && bar_min >= or_start && bar_min < or_end)
        {
         if(high[i] > ORH) ORH = high[i];
         if(low[i]  < ORL) ORL = low[i];
        }
      if(!or_locked && bar_min >= or_end && ORH > 0)
         or_locked = true;

      double orm = (ORH + ORL) / 2.0;
      double orw = ORH - ORL;

      // ── Indicator 1: MACD ──
      int macd_dir = 0;
      // BUY: macd crosses above signal OR macd > signal AND above SMA89
      bool macd_cross_up = (macd_main[idx] > macd_sig[idx]) &&
                           (macd_main[idx+1] <= macd_sig[idx+1]);
      bool macd_cross_dn = (macd_main[idx] < macd_sig[idx]) &&
                           (macd_main[idx+1] >= macd_sig[idx+1]);
      bool above_sma = close[i] > sma[idx];
      bool sma_rising = sma[idx] > sma[idx+1];

      if(macd_cross_up && above_sma)        macd_dir =  1;   // BUY
      else if(macd_cross_dn && !above_sma)  macd_dir = -1;   // SELL
      else if(macd_main[idx] > macd_sig[idx] && above_sma && sma_rising) macd_dir = 1;
      else if(macd_main[idx] < macd_sig[idx] && !above_sma && !sma_rising) macd_dir = -1;

      // ── Indicator 2: SuperBollingerTrend (BB-based) ──
      int sbt_dir = 0;
      // Bull: price above BB upper OR close > bb_mid and rising
      // Bear: price below BB lower OR close < bb_mid and falling
      bool price_above_bbmid = close[i] > bb_mid[idx];
      bool bb_upper_touch = close[i] >= bb_upper[idx] * 0.995;
      bool bb_lower_touch = close[i] <= bb_lower[idx] * 1.005;
      bool price_rising = close[i] > close[i+1] && close[i+1] > close[i+2];
      bool price_falling = close[i] < close[i+1] && close[i+1] < close[i+2];

      if(price_above_bbmid && price_rising)         sbt_dir =  1;
      else if(!price_above_bbmid && price_falling)  sbt_dir = -1;
      if(bb_upper_touch && price_rising)             sbt_dir =  1;
      if(bb_lower_touch && price_falling)            sbt_dir = -1;

      // ── Indicator 3: ORB ──
      int orb_dir = 0;
      if(or_locked && ORH > 0 && ORL > 0 && ORL < 1e8)
        {
         bool orb_break_up = (close[i] > ORH) && (close[i+1] <= ORH);
         bool orb_break_dn = (close[i] < ORL) && (close[i+1] >= ORL);
         if(orb_break_up)                orb_dir =  1;   // fresh breakout
         else if(orb_break_dn)           orb_dir = -1;
         else if(close[i] > ORH)         orb_dir =  1;   // already above
         else if(close[i] < ORL)         orb_dir = -1;
         else if(close[i] > orm)         orb_dir =  1;   // bullish bias
         else if(close[i] < orm)         orb_dir = -1;
        }

      // ── Indicator 4: Stochastic (Phoenix wSMD approx) ──
      int phx_dir = 0;
      bool stoch_cross_up = (stoch_k[idx] > stoch_d[idx]) &&
                            (stoch_k[idx+1] <= stoch_d[idx+1]);
      bool stoch_cross_dn = (stoch_k[idx] < stoch_d[idx]) &&
                            (stoch_k[idx+1] >= stoch_d[idx+1]);
      bool stoch_oversold  = stoch_k[idx] < 25;
      bool stoch_overbought= stoch_k[idx] > 75;

      if(stoch_cross_up && stoch_k[idx] < 50)      phx_dir =  1;
      else if(stoch_cross_dn && stoch_k[idx] > 50) phx_dir = -1;
      else if(stoch_oversold && price_rising)       phx_dir =  1;
      else if(stoch_overbought && price_falling)    phx_dir = -1;

      // ── Count agreements ──
      int buy_count  = (macd_dir==1?1:0) + (sbt_dir==1?1:0) +
                       (orb_dir==1?1:0)  + (phx_dir==1?1:0);
      int sell_count = (macd_dir==-1?1:0) + (sbt_dir==-1?1:0) +
                       (orb_dir==-1?1:0)  + (phx_dir==-1?1:0);

      int agree_count = MathMax(buy_count, sell_count);
      int direction   = buy_count > sell_count ? 1 :
                        sell_count > buy_count ? -1 : 0;

      if(agree_count < 2 || direction == 0) continue;

      // ── Arrow placement ──
      double arrow_offset = (bb_upper[idx] - bb_lower[idx]) * 0.3;
      if(direction == 1)
        {
         if(agree_count >= 3)
              BuyDouble[i]  = low[i]  - arrow_offset;
         else BuyNormal[i]  = low[i]  - arrow_offset;
        }
      else
        {
         if(agree_count >= 3)
              SellDouble[i] = high[i] + arrow_offset;
         else SellNormal[i] = high[i] + arrow_offset;
        }

      // ── Alerts (only on current bar, not historical) ──
      if(i == rates_total - 2 && (rates_total - 2) > last_alert_bar + CooldownBars)
        {
         last_alert_bar = rates_total - 2;
         string dir_str  = direction == 1 ? "BUY" : "SELL";
         string lot_str  = agree_count >= 3 ? "DOUBLE LOT" : "NORMAL LOT";
         string ind_list = "";
         if(macd_dir == direction) ind_list += "MACD ";
         if(sbt_dir  == direction) ind_list += "SBT ";
         if(orb_dir  == direction) ind_list += "ORB ";
         if(phx_dir  == direction) ind_list += "Phoenix ";

         string msg = StringFormat(
           "🔔 %s %s | %s | %d/4 indicators: %s| Price: %.2f",
           _Symbol, dir_str, lot_str, agree_count, ind_list, close[0]
         );

         if(PlaySound)
           {
            if(agree_count >= 3) PlaySound("alert2.wav");   // loud for double
            else                 PlaySound(AlertSound);
           }
         if(SendMT5Alert)
            Alert(msg);
         if(SendPushAlert)
            SendNotification(msg);

         Print(msg);
        }
     }

   return rates_total;
  }
//+------------------------------------------------------------------+
