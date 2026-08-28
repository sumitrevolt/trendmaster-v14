' Hidden runner for run_ea_parity_nightly.cmd
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "cmd /c tools\run_ea_parity_nightly.cmd >> logs\ea_parity_wrapper.log 2>&1", 0, False
