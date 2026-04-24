# TrendMaster v14 - Real-Data Backtest

Source: `logs/brain_memory.json` (trade_history, 500 trades).
News calendar: `config/news_calendar.json` (58 high-impact events loaded).
Window: 2026-03-08 (one-day replay). Symbols: XAUUSD, ETHUSD.

## Baseline vs Gated

| metric | baseline | gated |
| --- | ---: | ---: |
| total_trades | 500 | 489 |
| wins | 327 | 321 |
| losses | 173 | 168 |
| win_rate | 65.40% | 65.64% |
| avg_win ($) | 16.36 | 16.49 |
| avg_loss ($) | -18.06 | -17.68 |
| expectancy / trade ($) | 4.4540 | 4.7495 |
| expectancy / trade (R) | 0.7943 | 0.8060 |
| total_pnl ($) | 2226.98 | 2322.51 |
| max_drawdown ($) | 927.05 | 927.05 |
| profit_factor | 1.7129 | 1.7821 |
| sharpe / trade | 0.1805 | 0.1929 |

## Cost breakdown per symbol

| symbol | arm | trades | total_cost_usd | per_trade_usd |
| --- | --- | ---: | ---: | ---: |
| ETHUSD | baseline | 259 | 414.40 | 1.6000 |
| XAUUSD | baseline | 241 | 1928.00 | 8.0000 |
| ETHUSD | gated | 255 | 408.00 | 1.6000 |
| XAUUSD | gated | 234 | 1872.00 | 8.0000 |

## Filters: gradeable vs not

| filter | status | reason |
| --- | --- | --- |
| confluence (>=6 of 15 features) | GRADED | features dict is stored per trade |
| news blackout (+/-30min) | GRADED (degenerate here) | calendar starts 2026-04-28; no overlap with 2026-03-08 trades |
| spread_guard | CANNOT BACKTEST | needs live spread snapshot at entry, not logged |
| vol_regime (ATR) | CANNOT BACKTEST | needs candle series, not logged |
| session filter | CANNOT BACKTEST standalone | already folded into features, not a separate gate |
| liquidity floor | CANNOT BACKTEST | needs tick volume at entry |
| equity / DD breaker | CANNOT BACKTEST here | per-account state, not per-trade replay |

## Caveats

- One-day window (2026-03-08). Not representative of regime variety.
- Only two symbols (XAUUSD, ETHUSD) - no forex, no other commodities.
- Replay is from the brain's own trade log, not raw market ticks: survivorship of the already-executed trades is baked in.
- Only 2 of 7 profit filters are replayable from the stored fields.
- Base class is heavily imbalanced (~86% win rate). That looks suspiciously high for real live trading and may reflect optimistic exit logic in the replay source.
- Not a walk-forward / out-of-sample test. No parameter was re-fit; this only measures whether a simple confluence+news gate would have improved the same trades.
- Costs are modeled, not observed - OctaFX real spreads fluctuate, especially around news.
