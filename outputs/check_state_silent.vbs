' Run check_state.cmd hidden, output goes to outputs\state_check.txt
Set shell = CreateObject("WScript.Shell")
basePath = "C:\Users\Ratanshila\Documents\autmated trading"
shell.Run "cmd /c """ & basePath & "\outputs\check_state.cmd"" > """ & basePath & "\outputs\state_check.txt"" 2>&1", 0, True
