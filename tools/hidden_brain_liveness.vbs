' Hidden runner for trading-brain-liveness (every 5 min)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "cmd /c "".venv\Scripts\python.exe"" docs\skills\trading-brain-liveness\liveness.py >> logs\brain_liveness.log 2>&1", 0, False
