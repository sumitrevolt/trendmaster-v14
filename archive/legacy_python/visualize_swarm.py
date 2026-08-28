import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import logging
from datetime import datetime

# Import existing project modules
from config import settings
from src.data_fetcher import MT5Connection, DataFetcher, initialize_mt5
from src.indicators import AMDAnalyzer
import sys
import time

def create_market_dashboard():
    print("Connecting to MetaTrader 5 Data Streams...")
    mt5 = initialize_mt5()
    if not mt5:
        print("Error: Could not connect to MT5.")
        return

    fetcher = DataFetcher(mt5)
    analyzer = AMDAnalyzer()

    # Create subplot layout
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=('XAUUSD (Gold) - M15 Smart Money Chart', 'ETHUSD (Ethereum) - M15 Smart Money Chart'),
        row_heights=[0.5, 0.5]
    )

    pair_data = {}
    for i, symbol in enumerate(['XAUUSD', 'ETHUSD']):
        print(f"Agent 'DataOracle' fetching {symbol} footprint...")
        df = fetcher.refresh_data(symbol, 'M15')
        if df is None or df.empty:
            continue

        print(f"Agent 'StrategyBrain' analyzing {symbol} Liquidity/FVGs...")
        analyzed_df = analyzer.analyze(df)

        # Plot Candlestick
        recent_df = analyzed_df.tail(100)  # Last 100 candles

        fig.add_trace(go.Candlestick(
            x=recent_df.index,
            open=recent_df['open'],
            high=recent_df['high'],
            low=recent_df['low'],
            close=recent_df['close'],
            name=f'{symbol} Price'
        ), row=i+1, col=1)

        # Add EMA 50 (Trend Context)
        fig.add_trace(go.Scatter(
            x=recent_df.index,
            y=recent_df['ema_trend'],
            line=dict(color='orange', width=2),
            name=f'{symbol} Trend EMA (50)'
        ), row=i+1, col=1)

        # Annotate Fair Value Gaps (FVG) and Liquidity Sweeps detected by the Brain
        for idx, row in recent_df.iterrows():
            if row.get('bullish_fvg'):
                fig.add_annotation(
                    x=idx, y=row['low'],
                    text="FVG (Buy)", showarrow=True, arrowhead=1, arrowcolor="green",
                    row=i+1, col=1
                )
            if row.get('bullish_manipulation'):
                fig.add_annotation(
                    x=idx, y=row['low'],
                    text="Liq Sweep", showarrow=True, arrowhead=1, arrowcolor="blue",
                    row=i+1, col=1
                )

    fig.update_layout(
        title='Billionaire Swarm Intelligence - Live AI Market View',
        yaxis_title='Gold Price',
        yaxis2_title='Ethereum Price',
        xaxis_rangeslider_visible=False,
        xaxis2_rangeslider_visible=False,
        template="plotly_dark",
        height=1000
    )

    filename = "AI_Swarm_Live_Chart.html"
    fig.write_html(filename)
    print(f"\n✅ Live Data Map generated perfectly. Opened {filename}")

    # Open the generated HTML map
    import webbrowser
    import os
    webbrowser.open('file://' + os.path.realpath(filename))

if __name__ == "__main__":
    create_market_dashboard()
