@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === Iteration 1: SL 2.0 / TP 2.0 (1:1 RR, tighter TP) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 2.0 --tp-atr-mult 2.0

echo.
echo === Iteration 2: SL 2.5 / TP 1.5 (asymmetric, favours wins) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 2.5 --tp-atr-mult 1.5

echo.
echo === Iteration 3: SL 3.0 / TP 1.0 (very wide SL, quick TP) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 3.0 --tp-atr-mult 1.0

echo.
echo === Iteration 4: SL 4.0 / TP 0.8 (extreme — high WR, low RR) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 4.0 --tp-atr-mult 0.8
