"""Auto-generated per-TEAM profit-max fallback.

Aggregated from tools/optimize_profit_max.py winners per team.
Used when a symbol is in a team but not in PAIR_PARAMS.
"""

TEAM_PARAMS = {
    "METALS": {
        "sl_atr_mult": 1.0,
        "tp_atr_mult": 5.0,
        "adx_min": 35,
        "expected_wr": 0.2291,
        "expected_exp": 0.1843,
        "trades_bt": 1547,
        "gross_r": 264.89,
        "sharpe": 0.0786,
    },
    "FOREX": {
        "sl_atr_mult": 0.75,
        "tp_atr_mult": 4.25,
        "adx_min": 26,
        "expected_wr": 0.2232,
        "expected_exp": 0.0990,
        "trades_bt": 7316,
        "gross_r": 598.69,
        "sharpe": 0.0438,
    },
    "CRYPTO": {
        "sl_atr_mult": 0.75,
        "tp_atr_mult": 5.0,
        "adx_min": 30,
        "expected_wr": 0.1825,
        "expected_exp": 0.1280,
        "trades_bt": 937,
        "gross_r": 119.96,
        "sharpe": 0.0509,
    },
    "COMMODITIES": {
        "sl_atr_mult": 0.75,
        "tp_atr_mult": 5.0,
        "adx_min": 30,
        "expected_wr": 0.1993,
        "expected_exp": 0.2380,
        "trades_bt": 913,
        "gross_r": 217.25,
        "sharpe": 0.0917,
    },
}

SYMBOL_TO_TEAM = {
    "XAUUSD": "METALS",
    "XAGUSD": "METALS",
    "GBPJPY": "FOREX",
    "USDCAD": "FOREX",
    "USDCHF": "FOREX",
    "EURUSD": "FOREX",
    "GBPUSD": "FOREX",
    "AUDUSD": "FOREX",
    "USDJPY": "FOREX",
    "NZDUSD": "FOREX",
    "EURJPY": "FOREX",
    "EURGBP": "FOREX",
    "AUDJPY": "FOREX",
    "CADJPY": "FOREX",
    "BTCUSD": "CRYPTO",
    "ETHUSD": "CRYPTO",
    "XTIUSD": "COMMODITIES",
    "XBRUSD": "COMMODITIES",
    "XNGUSD": "COMMODITIES",
}
