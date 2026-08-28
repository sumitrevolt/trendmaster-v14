@echo off
REM 2026-04-29 — smoke test trader agent on Sonnet 4.6 after model swap.
REM Writes output to %USERPROFILE%\.openclaw\sonnet_smoke_2026-04-29_3.txt
cd /d C:\oc
"C:\Program Files\nodejs\node.exe" node_modules\openclaw\openclaw.mjs agent --agent trader --thinking off --timeout 90 --json --message "ping" > "%USERPROFILE%\.openclaw\sonnet_smoke_2026-04-29_3.txt" 2>&1
echo. >> "%USERPROFILE%\.openclaw\sonnet_smoke_2026-04-29_3.txt"
echo exit=%ERRORLEVEL% >> "%USERPROFILE%\.openclaw\sonnet_smoke_2026-04-29_3.txt"
