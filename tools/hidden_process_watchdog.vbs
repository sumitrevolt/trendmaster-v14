' Hidden runner for process_watchdog.py — every 2 min
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "cmd /c "".venv\Scripts\pythonw.exe"" -u tools\process_watchdog.py >> logs\process_watchdog_wrapper.log 2>&1", 0, False
