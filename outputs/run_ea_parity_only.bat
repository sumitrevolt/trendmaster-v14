@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === EA-parity backtest (SL 1.5x / TP 3.0x = 1:2.0 R) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 1.5 --tp-atr-mult 3.0
