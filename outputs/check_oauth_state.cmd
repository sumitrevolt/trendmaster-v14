@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Tokens captured? ===
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env', override=True); print('  CTRADER_ACCESS_TOKEN:', ('SET (len=' + str(len(os.getenv('CTRADER_ACCESS_TOKEN',''))) + ')') if os.getenv('CTRADER_ACCESS_TOKEN','').strip() else 'EMPTY'); print('  CTRADER_REFRESH_TOKEN:', 'SET' if os.getenv('CTRADER_REFRESH_TOKEN','').strip() else 'EMPTY'); print('  CTRADER_ACCOUNT_ID:', os.getenv('CTRADER_ACCOUNT_ID','') or 'EMPTY')"
echo.
echo === OAuth helper still running? ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*ctrader_oauth*' } | Select-Object ProcessId, @{N='AgeMin';E={[math]::Round((New-TimeSpan -Start $_.CreationDate -End (Get-Date)).TotalMinutes,1)}} | Format-Table"
echo.
echo === Local callback server (port 8766) listening? ===
netstat -ano 2>nul | findstr ":8766"
