@echo off
:: Disables the "OpenClaw Gateway" scheduled task.
:: This task's ACL requires an elevated (Administrator) token to modify --
:: a normal-user session gets "Access is denied" even though the task
:: is owned by the same Windows account. Right-click this file and choose
:: "Run as administrator" (you'll get one UAC prompt -- click Yes).

schtasks /Change /TN "OpenClaw Gateway" /DISABLE
echo.
echo Result above. Current state:
schtasks /query /tn "OpenClaw Gateway" /fo LIST | findstr /i "TaskName Status"
echo.
pause
