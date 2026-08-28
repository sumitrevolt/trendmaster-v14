' Hidden launcher for signal_pipeline_monitor.py - every 5 min
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" tools\signal_pipeline_monitor.py", 0, False
