' Hidden runner for run_walkforward_lab.cmd
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "cmd /c tools\run_walkforward_lab.cmd >> logs\walkforward_wrapper.log 2>&1", 0, False
