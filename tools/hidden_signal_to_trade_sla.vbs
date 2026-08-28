' Hidden launcher for signal_to_trade_sla.py — every 1 min
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" tools\signal_to_trade_sla.py", 0, False
