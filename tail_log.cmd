@echo off
set OUT=C:\Users\Ratanshila\Documents\autmated trading\outputs\tail_log.txt
echo [%DATE% %TIME%] tail openclaw log > "%OUT%"
echo. >> "%OUT%"

if exist "C:\tmp\openclaw\openclaw-2026-04-29.log" (
    powershell -command "Get-Content 'C:\tmp\openclaw\openclaw-2026-04-29.log' -Tail 30 | ForEach-Object { try { $j = $_ | ConvertFrom-Json; $msg = if ($j.'1' -is [string]) { $j.'1' } else { $j.'2' }; '[{0}] {1}' -f $j.time, $msg } catch { $_ } }" >> "%OUT%" 2>&1
) else (
    echo "[ERR] log not found" >> "%OUT%"
)

echo. >> "%OUT%"
echo === Last 5 fresh ports === >> "%OUT%"
netstat -ano | findstr "LISTENING" | findstr "18789\|55088\|18791" >> "%OUT%" 2>&1
