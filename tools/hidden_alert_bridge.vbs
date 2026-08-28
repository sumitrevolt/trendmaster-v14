' Hidden runner for trading-alert-bridge (every 1 min)
' 2026-05-13: switched from python.exe + cmd wrapper to direct pythonw.
' Previous form was the biggest popup offender — python.exe creates a
' console window every minute, and cmd /c added a second one.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" docs\skills\trading-alert-bridge\bridge.py --quiet", 0, False
