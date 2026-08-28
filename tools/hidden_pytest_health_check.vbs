' Hidden runner for pytest_health_check.cmd
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "tools\pytest_health_check.cmd", 0, False
