' Hidden runner for local_signal_generator.py (every 5 min)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "cmd /c "".venv\Scripts\python.exe"" tools\local_signal_generator.py >> logs\local_signal_generator_wrapper.log 2>&1", 0, False
