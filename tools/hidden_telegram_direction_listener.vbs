' Hidden launcher for telegram_direction_listener — runs invisibly.
' Long-running process; watchdog ensures singleton + restart on death.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" tools\telegram_direction_listener.py", 0, False
