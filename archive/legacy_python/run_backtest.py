"""
GOLD SCALPING BOT - Multi-Timeframe Backtest Script
=====================================================
Tests M3, M5, M15, H1, H4 entry strategies with their trend TFs on XAUUSD.
Each entry TF uses its configured higher-TF for trend context.
"""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '.')
from backtesting.backtest_engine import BacktestEngine
from config import settings


def _rates_to_df(rates) -> pd.DataFrame:
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df.columns = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
    df['volume'] = df['tick_volume']
    return df


# MT5 timeframe constants mapping
MT5_TF_MAP = {
    'M1': mt5.TIMEFRAME_M1,
    'M3': mt5.TIMEFRAME_M3,
    'M5': mt5.TIMEFRAME_M5,
    'M15': mt5.TIMEFRAME_M15,
    'M30': mt5.TIMEFRAME_M30,
    'H1': mt5.TIMEFRAME_H1,
    'H4': mt5.TIMEFRAME_H4,
    'D1': mt5.TIMEFRAME_D1,
}


def run_backtest():
    if not mt5.initialize():
        print("Failed to connect to MT5. Make sure it's running.")
        return

    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)

    entry_timeframes = getattr(settings, 'ENTRY_TIMEFRAMES', {
        'M5': {'trend_tf': 'H1', 'min_candles': 60, 'candle_seconds': 300, 'tf_multiplier': 1.0, 'max_candles_in_trade': 20}
    })

    print("=" * 70)
    print("GOLD SCALPING BOT - MULTI-TIMEFRAME BACKTEST")
    print("=" * 70)
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Starting Balance: $600 (Rs 50,000)")
    print(f"Risk Per Trade: {settings.RISK.get('risk_percent', 1.5)}%")
    print(f"Entry Timeframes: {', '.join(entry_timeframes.keys())}")
    print(f"Strategy: Multi-TF Scalp + Spike Detection + Trailing SL")
    print()

    pairs = settings.TRADING_PAIRS
    grand_total_trades = 0
    grand_total_wins = 0
    grand_results = {}

    for symbol in pairs:
        mt5.symbol_select(symbol, True)

        # Collect ALL unique timeframes needed (entry TFs + trend TFs)
        all_tfs_needed = set()
        for entry_tf, tf_config in entry_timeframes.items():
            all_tfs_needed.add(entry_tf)
            all_tfs_needed.add(tf_config.get('trend_tf', 'H1'))
        # Add M15 as setup TF for compatibility with run_multi_timeframe
        all_tfs_needed.add('M15')

        # Fetch all TF data
        data_by_tf = {}
        for tf_name in sorted(all_tfs_needed):
            tf_const = MT5_TF_MAP.get(tf_name)
            if tf_const is None:
                print(f"  Warning: Unknown TF {tf_name}, skipping")
                continue
            rates = mt5.copy_rates_range(symbol, tf_const, start_date, end_date)
            if rates is not None and len(rates) > 0:
                data_by_tf[tf_name] = _rates_to_df(rates)
                print(f"  {tf_name}: {len(data_by_tf[tf_name])} candles")
            else:
                print(f"  {tf_name}: No data available")

        if not data_by_tf:
            print(f"No data for {symbol}")
            continue

        # Run backtest for EACH entry timeframe
        for entry_tf, tf_config in entry_timeframes.items():
            trend_tf = tf_config.get('trend_tf', 'H1')
            setup_tf = trend_tf

            # Check required data exists
            if entry_tf not in data_by_tf:
                print(f"\n  Skipping {entry_tf} - no data")
                continue
            if trend_tf not in data_by_tf:
                print(f"\n  Skipping {entry_tf} - no {trend_tf} trend data")
                continue
            if setup_tf not in data_by_tf:
                setup_tf = trend_tf  # fallback

            print(f"\n{'='*50}")
            print(f"=== {symbol} {entry_tf} ENTRY (Trend: {trend_tf}) ===")
            print(f"{'='*50}")

            engine = BacktestEngine(
                initial_balance=600,
                risk_percent=settings.RISK.get('risk_percent', 1.5),
                commission_per_lot=7.0
            )

            results = engine.run_multi_timeframe(
                data_by_tf,
                symbol=symbol,
                trend_tf=trend_tf,
                setup_tf=setup_tf,
                entry_tf=entry_tf,
            )

            if 'error' in results:
                print(f"  Error: {results['error']}")
                continue

            engine.print_results(results)

            total_trades = results.get('total_trades', 0)
            wins = results.get('winners', 0)
            if total_trades > 0:
                days = (end_date - start_date).days
                tpd = total_trades / max(days, 1)
                print(f"  Trades/Day: {tpd:.1f}")
                grand_total_trades += total_trades
                grand_total_wins += wins
                grand_results[entry_tf] = results

    mt5.shutdown()

    # ============ COMBINED SUMMARY ============
    print("\n" + "=" * 70)
    print("MULTI-TIMEFRAME COMBINED SUMMARY")
    print("=" * 70)

    if grand_total_trades > 0:
        overall_wr = (grand_total_wins / grand_total_trades) * 100
        days = (end_date - start_date).days

        print(f"\n  {'TF':<6} {'Trades':>7} {'Wins':>6} {'WR%':>6} {'Return%':>9} {'T/Day':>6}")
        print(f"  {'-'*42}")
        for tf, res in grand_results.items():
            t = res.get('total_trades', 0)
            w = res.get('winners', 0)
            wr = (w / t * 100) if t > 0 else 0
            ret = res.get('return_pct', 0)
            tpd = t / max(days, 1)
            print(f"  {tf:<6} {t:>7} {w:>6} {wr:>5.1f}% {ret:>8.1f}% {tpd:>5.1f}")

        total_tpd = grand_total_trades / max(days, 1)
        print(f"  {'-'*42}")
        print(f"  {'TOTAL':<6} {grand_total_trades:>7} {grand_total_wins:>6} {overall_wr:>5.1f}% {'':>9} {total_tpd:>5.1f}")

        if overall_wr >= 85:
            print("\n  TARGET ACHIEVED! 85%+ Win Rate!")
        elif overall_wr >= 80:
            print("\n  EXCELLENT! 80%+ Win Rate!")
    else:
        print("  No trades across any timeframe")

    print("=" * 70)


if __name__ == "__main__":
    run_backtest()
