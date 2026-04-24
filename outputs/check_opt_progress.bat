@echo off
echo === Running python processes ===
tasklist /FI "IMAGENAME eq python.exe" /FO TABLE
echo.
echo === Output files produced so far ===
dir /B "C:\Users\Ratanshila\Documents\autmated trading\reports\PER_PAIR*" 2>nul
dir /B "C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents\pair_params.py" 2>nul
echo.
echo === Done ===
