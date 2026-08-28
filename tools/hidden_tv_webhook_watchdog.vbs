' Hidden runner for tv_webhook_watchdog.py — every 5 min
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
' 2026-05-13: dropped cmd /c wrapper + stdout redirect (caused popup flash).
' Pythonw is GUI-subsystem so any print() is discarded but logging.FileHandler
' calls inside the script still write to disk.
sh.Run """.venv\Scripts\pythonw.exe"" tools\tv_webhook_watchdog.py", 0, False
