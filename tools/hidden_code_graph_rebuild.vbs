' Hidden runner for scheduled_rebuild.cmd (Code Graph Rebuild)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Ratanshila\Documents\autmated trading"
sh.Run "tools\scheduled_rebuild.cmd", 0, False
