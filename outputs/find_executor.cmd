@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === find tv_executor ===
dir /s /b ai_trading_agents\tv_executor.py 2>nul
dir /s /b C:\TrendMaster_aita_canonical\tv_executor.py 2>nul
echo.
echo === Show contents of write_tv_signal function ===
.venv\Scripts\python.exe -c "from pathlib import Path; t=Path('C:/TrendMaster_aita_canonical/tv_executor.py').read_text(); print(t[:200]); print('...'); print('LENGTH:', len(t), 'lines:', t.count(chr(10)))"
