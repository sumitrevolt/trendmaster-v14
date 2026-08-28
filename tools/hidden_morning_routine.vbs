' Hidden runner for trading-morning-routine (daily 09:00)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "cmd /c "".venv\Scripts\python.exe"" docs\skills\trading-morning-routine\routine.py --quiet >> logs\morning_routine.log 2>&1", 0, False
