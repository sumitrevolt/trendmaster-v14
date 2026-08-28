@echo off
REM Re-point each popping schtask to its hidden VBS wrapper.

set ROOT=C:\Users\Ratanshila\Documents\autmated trading

echo === Auto Research ===
schtasks /Change /TN "TrendMaster Auto Research" /TR "wscript.exe \"%ROOT%\tools\hidden_auto_research.vbs\""

echo === EA Parity Nightly ===
schtasks /Change /TN "TrendMaster EA Parity Nightly" /TR "wscript.exe \"%ROOT%\tools\hidden_ea_parity_nightly.vbs\""

echo === Walkforward Lab ===
schtasks /Change /TN "TrendMaster Walkforward Lab" /TR "wscript.exe \"%ROOT%\tools\hidden_walkforward_lab.vbs\""

echo === Zero Trades Watchdog ===
schtasks /Change /TN "TrendMaster Zero Trades Watchdog" /TR "wscript.exe \"%ROOT%\tools\hidden_zero_trades_watchdog.vbs\""

echo.
echo === Verification ===
for %%t in ("TrendMaster Auto Research" "TrendMaster EA Parity Nightly" "TrendMaster Walkforward Lab" "TrendMaster Zero Trades Watchdog") do (
    echo.
    schtasks /Query /TN %%t /FO LIST | findstr /C:"TaskName:" /C:"Task To Run:"
)
