@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === SWEETSPOT 1: SL 3.5 / TP 1.0 (80%+ WR target, better RR) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 3.5 --tp-atr-mult 1.0

echo.
echo === SWEETSPOT 2: SL 3.0 / TP 1.2 (balanced) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 3.0 --tp-atr-mult 1.2

echo.
echo === SWEETSPOT 3: SL 2.5 / TP 1.0 (tighter SL, same TP) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 2.5 --tp-atr-mult 1.0

echo.
echo === SWEETSPOT 4: SL 3.5 / TP 1.2 (reasonable RR + high WR target) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 3.5 --tp-atr-mult 1.2

echo.
echo === SWEETSPOT 5: SL 4.0 / TP 1.0 (ultra high WR mode) ===
python tools\backtest.py ea_parity data\xauusd_m5_history.csv --sl-atr-mult 4.0 --tp-atr-mult 1.0
