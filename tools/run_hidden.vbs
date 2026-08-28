' Run any command line completely hidden (no flashing cmd window).
' Used by TrendMaster scheduled tasks that fire frequently (Alert Bridge
' every 1min, Brain Liveness every 5min, Junction Guard every 15min).
'
' Usage from schtask:
'   wscript.exe "C:\Users\Ratanshila\Documents\autmated trading\tools\run_hidden.vbs" "<command line>"
'
' WindowStyle 0 = hidden (no flash), waitOnReturn = False (fire-and-forget).

If WScript.Arguments.Count = 0 Then
    WScript.Quit 1
End If

Set shell = CreateObject("WScript.Shell")
shell.Run WScript.Arguments(0), 0, False
