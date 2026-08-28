@echo off
setlocal
set DUMP=%TEMP%\trendmaster_sched.txt
schtasks /Query /FO LIST /V > "%DUMP%" 2>&1

echo === TrendMaster scheduled tasks: name + executable ===
echo.
findstr /N "TaskName Task" "%DUMP%" | findstr /I "TrendMaster Health TaskName: TaskTo"

echo.
echo === Filtering: which use python.exe (visible console) ===
echo.
powershell -NoProfile -Command "$content = Get-Content '%DUMP%' -Raw; $blocks = $content -split '\r?\n\r?\n'; foreach ($b in $blocks) { if ($b -match 'TrendMaster|Watchdog' -and $b -match 'TaskName:\s+(\S.+?)\r?\n') { $name = $matches[1]; $run = ''; if ($b -match 'Task To Run:\s+(.+?)\r?\n') { $run = $matches[1] }; $isVisible = if ($run -match '\\python\.exe') { 'POPUP-PYTHON' } elseif ($run -match '\\pythonw\.exe') { 'silent-pythonw' } elseif ($run -match '\.cmd|\.bat') { 'POPUP-CMD' } else { 'other' }; Write-Host ('  [{0,-15}] {1}' -f $isVisible, $name); Write-Host ('                  -> ' + $run) } }"
