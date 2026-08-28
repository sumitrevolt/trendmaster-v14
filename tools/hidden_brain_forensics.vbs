' Hidden runner for brain_forensics_monitor.py — sample every 30s
' 2026-05-13: switched from `cmd /c pythonw ... >> log` to direct pythonw
' invocation. Previous form spawned a transient cmd.exe + conhost.exe even
' with WindowStyle 0 — visible flash every cycle. The Python script handles
' its own file logging internally (LOG_PATH in tools/brain_forensics_monitor.py),
' so the shell-level redirect was redundant. pythonw is GUI-subsystem so
' no console is allocated at all → zero popup.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run """.venv\Scripts\pythonw.exe"" tools\brain_forensics_monitor.py --once", 0, False
