' Hidden launcher for TV alert reactivation.
' 2026-05-13: switched to pythonw.exe (silent) + reactivate_wrapper.py
' which handles its own logging. Original was visible python.exe with
' broken shell redirect, AND pointed to wrong path (outputs/ vs tools/).
' Triggered by Windows Task Scheduler EVERY 5 MIN now (was hourly) so
' alerts get reactivated quickly after any webhook failure cascade.
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
WshShell.Run """C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\pythonw.exe"" """ & "C:\Users\Ratanshila\Documents\autmated trading\outputs\reactivate_wrapper.py" & """", 0, False
