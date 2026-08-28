@echo off
REM Recreate (delete + create) each popping schtask with VBS wrapper.
REM /Change was hanging — /Create /F is more reliable.

set ROOT=C:\Users\Ratanshila\Documents\autmated trading

echo === 1. Auto Research ===
schtasks /Delete /TN "TrendMaster Auto Research" /F 2>nul
schtasks /Create /F /TN "TrendMaster Auto Research" ^
  /TR "wscript.exe \"%ROOT%\tools\hidden_auto_research.vbs\"" ^
  /SC DAILY /ST 04:00 /RL LIMITED

echo === 2. EA Parity Nightly ===
schtasks /Delete /TN "TrendMaster EA Parity Nightly" /F 2>nul
schtasks /Create /F /TN "TrendMaster EA Parity Nightly" ^
  /TR "wscript.exe \"%ROOT%\tools\hidden_ea_parity_nightly.vbs\"" ^
  /SC DAILY /ST 02:30 /RL LIMITED

echo === 3. Walkforward Lab ===
schtasks /Delete /TN "TrendMaster Walkforward Lab" /F 2>nul
schtasks /Create /F /TN "TrendMaster Walkforward Lab" ^
  /TR "wscript.exe \"%ROOT%\tools\hidden_walkforward_lab.vbs\"" ^
  /SC DAILY /ST 02:30 /RL LIMITED

echo === 4. Zero Trades Watchdog ===
schtasks /Delete /TN "TrendMaster Zero Trades Watchdog" /F 2>nul
schtasks /Create /F /TN "TrendMaster Zero Trades Watchdog" ^
  /TR "wscript.exe \"%ROOT%\tools\hidden_zero_trades_watchdog.vbs\"" ^
  /SC DAILY /ST 09:00 /RL LIMITED

echo.
echo === Done ===
