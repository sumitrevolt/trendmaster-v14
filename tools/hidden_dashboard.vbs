' Hidden launcher for dashboard_server.py - HTTP server on http://localhost:8765
' 2026-05-14: removed `cmd /c set PYTHONUTF8=1 &&` wrapper ?" cmd was passing
' an INVALID value (trailing space) to Python, causing:
'   "Fatal Python error: preconfig_init_utf8_mode: invalid PYTHONUTF8"
' Dashboard would crash within 1 second on every 5-min schtask spawn,
' silently. Logged to logs/dashboard_wrapper.log only when log file exists.
' Fix: invoke pythonw directly. Python 3.11 defaults to UTF-8 on Windows.
' 2026-08-25: blind spawn piled up duplicate dashboards (x4). Now routes
' through dashboard_singleton.py which spawns only if none is running.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" tools\dashboard_singleton.py", 0, False
