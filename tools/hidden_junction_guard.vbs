' Hidden runner for trading-junction-guard (every 15 min)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" docs\skills\trading-junction-guard\guard.py --quiet-on-healthy", 0, False
