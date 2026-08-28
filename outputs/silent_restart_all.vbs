' Silent end-to-end restart: kill existing webhook+executor, respawn truly hidden.
' Runs entirely in background — no cmd window flash, no popup.
'
' Usage from Run dialog:
'   wscript.exe "C:\Users\Ratanshila\Documents\autmated trading\outputs\silent_restart_all.vbs"

Const ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Helper: run a command line hidden, wait for completion
Sub RunHidden(cmd, waitForExit)
    shell.Run cmd, 0, waitForExit
End Sub

' Step 1: kill any existing webhook/executor (use psutil-based Python for reliability)
killScript = ROOT & "\outputs\silent_kill.py"
Set f = fso.CreateTextFile(killScript, True)
f.WriteLine "import psutil"
f.WriteLine "for p in psutil.process_iter(['pid','name','cmdline']):"
f.WriteLine "    try:"
f.WriteLine "        cmd = ' '.join(p.info.get('cmdline') or [])"
f.WriteLine "        if 'tv_webhook_receiver' in cmd or 'python_signal_executor' in cmd:"
f.WriteLine "            print(f'killing PID {p.info[\""pid\""]}: {cmd[:100]}')"
f.WriteLine "            try: p.terminate()"
f.WriteLine "            except: pass"
f.WriteLine "    except: pass"
f.WriteLine "import time; time.sleep(3)"
f.WriteLine "# Force-kill any survivors"
f.WriteLine "for p in psutil.process_iter(['pid','cmdline']):"
f.WriteLine "    try:"
f.WriteLine "        cmd = ' '.join(p.info.get('cmdline') or [])"
f.WriteLine "        if 'tv_webhook_receiver' in cmd or 'python_signal_executor' in cmd:"
f.WriteLine "            try: p.kill()"
f.WriteLine "            except: pass"
f.WriteLine "    except: pass"
f.Close

RunHidden """" & ROOT & "\.venv\Scripts\python.exe"" """ & killScript & """ > """ & ROOT & "\outputs\silent_kill.log"" 2>&1", True

' Step 2: clean stale locks
On Error Resume Next
fso.DeleteFile ROOT & "\logs\python_executor.lock"
fso.DeleteFile ROOT & "\logs\.python_executor.lock"
On Error Goto 0

' Set cwd to ROOT so spawned children find logs/, config/, etc.
shell.CurrentDirectory = ROOT

' Step 3: spawn webhook hidden via pythonw (no console at all)
WScript.Sleep 1000
RunHidden """" & ROOT & "\.venv\Scripts\pythonw.exe"" -m ai_trading_agents.tv_webhook_receiver", False

' Step 4: spawn executor hidden via pythonw
WScript.Sleep 1500
RunHidden """" & ROOT & "\.venv\Scripts\pythonw.exe"" """ & ROOT & "\tools\python_signal_executor.py""", False

' Step 5: write completion marker so caller can verify
WScript.Sleep 5000
Set fOut = fso.CreateTextFile(ROOT & "\outputs\silent_restart_done.txt", True)
fOut.WriteLine "Silent restart completed at " & Now
fOut.Close
