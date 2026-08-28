' Hidden runner for run_zero_trades_watchdog.cmd
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "cmd /c tools\run_zero_trades_watchdog.cmd >> logs\zero_trades_wrapper.log 2>&1", 0, False
