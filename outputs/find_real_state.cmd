@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === Search ALL brain_state*.json files ===
powershell -NoProfile -Command "Get-ChildItem 'C:\' -Recurse -Filter 'brain_state*.json' -ErrorAction SilentlyContinue 2>$null | Select-Object FullName, LastWriteTime, @{N='SizeKB';E={[math]::Round($_.Length/1024,2)}} | Sort-Object LastWriteTime -Descending | Select-Object -First 10 | Format-Table -AutoSize"

echo.
echo === Find what file brain ACTUALLY opens for state ===
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from ai_trading_agents._paths import project_root; print('project_root():', project_root()); from ai_trading_agents.state_store import _DEFAULT_PATH; print('_DEFAULT_PATH:', _DEFAULT_PATH); print('exists:', _DEFAULT_PATH.exists()); print('mtime:', _DEFAULT_PATH.stat().st_mtime if _DEFAULT_PATH.exists() else None)"

echo.
echo === Check canonical-side state file (alternate location) ===
powershell -NoProfile -Command "if (Test-Path 'C:\TrendMaster_aita_canonical\logs\brain_state.json') { 'EXISTS at canonical: ' + (Get-Item 'C:\TrendMaster_aita_canonical\logs\brain_state.json').LastWriteTime } else { 'no state file in canonical/logs' }"

echo.
echo === Check if brain has its working dir as canonical ===
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*trend_master_brain*' } | Select-Object ProcessId, @{N='WorkingDir';E={(Get-Process -Id $_.ProcessId).Path}} | Format-List"

echo.
echo === brain.pid + brain.lock locations ===
dir /b /s "logs\brain.pid" 2>nul
dir /b /s "logs\brain.lock" 2>nul
dir /b /s "C:\TrendMaster_aita_canonical\logs" 2>nul

echo.
echo === Process working directory of brain ===
powershell -NoProfile -Command "Get-WmiObject Win32_Process -Filter \"name='python.exe' AND CommandLine LIKE '%%trend_master_brain%%'\" | Select-Object ProcessId, @{N='cwd_via_handle';E={ try { (Get-Process -Id $_.ProcessId -ErrorAction Stop).Path } catch { 'n/a' } }} | Format-List"
