' Hidden runner for trading-brain-liveness (every 5 min)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" docs\skills\trading-brain-liveness\liveness.py", 0, False
