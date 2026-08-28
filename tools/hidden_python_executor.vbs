' Launch the python signal executor invisibly (no console window).
Set WshShell = CreateObject("WScript.Shell")
strRoot = "C:\Users\Ratanshila\Documents\autmated trading"
strCmd = """" & strRoot & "\.venv\Scripts\pythonw.exe"" -u """ & strRoot & "\tools\python_signal_executor.py"""
WshShell.CurrentDirectory = strRoot
WshShell.Run strCmd, 0, False
