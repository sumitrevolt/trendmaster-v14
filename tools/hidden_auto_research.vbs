' Hidden runner for auto_research.py (terminal popup eliminated)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "cmd /c "".venv\Scripts\python.exe"" tools\auto_research.py --symbols all --timeout 1800 >> logs\auto_research_wrapper.log 2>&1", 0, False
