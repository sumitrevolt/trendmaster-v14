' Hidden runner for watch_pets.py (every ~1-2 min based on stagger)
' WindowStyle 0 = no flash. Fire-and-forget.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" tools\watch_pets.py --quiet", 0, False
