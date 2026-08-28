' Hidden runner for signal_outcome_collector.py (every 5 min)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" tools\signal_outcome_collector.py", 0, False
