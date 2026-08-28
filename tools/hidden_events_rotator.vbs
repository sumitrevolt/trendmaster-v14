' Hidden runner for trading-events-rotator (daily 03:30)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "cmd /c "".venv\Scripts\python.exe"" docs\skills\trading-events-rotator\rotator.py >> logs\events_rotator.log 2>&1", 0, False
