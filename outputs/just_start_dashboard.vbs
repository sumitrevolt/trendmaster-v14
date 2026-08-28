' Minimal launcher: just spawn dashboard_server.py via pythonw.
' Fire-and-forget (waitOnReturn=False) so wscript exits immediately
' and dashboard runs detached.
Set sh = CreateObject("WScript.Shell")
ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
sh.CurrentDirectory = ROOT
sh.Run """" & ROOT & "\.venv\Scripts\pythonw.exe"" """ & ROOT & "\tools\dashboard_server.py""", 0, False
