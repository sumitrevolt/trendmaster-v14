//+------------------------------------------------------------------+
//|  TrendMasterShared.mqh                                           |
//|  AUTO-GENERATED from config/trading_config.yaml                  |
//|  Do NOT edit by hand. Run: python tools/sync_config_to_mqh.py    |
//|                                                                  |
//|  Generated: 2026-04-29 05:50:42 UTC                                          |
//|  YAML version: 1                                         |
//+------------------------------------------------------------------+
#property strict
#ifndef __TM_SHARED_INCLUDED__
#define __TM_SHARED_INCLUDED__

// ---- Risk -----------------------------------------------------------------
#define TM_RISK_PERCENT                  0.5000
#define TM_MAX_DAILY_DRAWDOWN_PCT        3.0000
#define TM_MAX_OPEN_TRADES               8
#define TM_MAX_OPEN_PER_TEAM             2
#define TM_DEFAULT_SL_ATR_MULTIPLE       1.0000
#define TM_DEFAULT_TP_ATR_MULTIPLE       3.0000
#define TM_MIN_SL_PIPS                   5
#define TM_MIN_LOT_SIZE                  0.0100
#define TM_MAX_LOT_SIZE                  0.0300
#define TM_MIN_RR                        2.5000

// ---- EA bridge (MUST match Python brain) ----------------------------------
#define TM_MAGIC                         20260420
#define TM_SIGNAL_FILE                   "trendmaster_signals.json"
#define TM_USE_COMMON_FOLDER             false
#define TM_AI_STALE_SECS                 60
#define TM_AI_REQUIRED                   false
#define TM_AI_AUTO_PER_SYMBOL            true

// ---- EA indicator defaults ------------------------------------------------
#define TM_EMA_FAST                      20
#define TM_EMA_MID                       50
#define TM_EMA_SLOW                      200
#define TM_SUPERTREND_PERIOD             10
#define TM_SUPERTREND_FACTOR             3.0000
#define TM_ADX_PERIOD                    14
#define TM_ADX_MIN                       22
#define TM_BB_PERIOD                     20
#define TM_BB_DEV                        2.0000
#define TM_BB_WIDTH_FLOOR_RATIO          0.9000
#define TM_MACD_FAST                     12
#define TM_MACD_SLOW                     26
#define TM_MACD_SIGNAL                   9

#endif // __TM_SHARED_INCLUDED__
//+------------------------------------------------------------------+
