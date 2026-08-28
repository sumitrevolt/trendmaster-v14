' ==========================================================================
' autostart_pipeline.vbs  --  TrendMaster boot-time pipeline kickoff
'
' Runs at every Windows logon (via "TrendMaster Auto-Start" scheduled task).
' Hidden window (wscript runs VBS without showing console).
'
' Order of operations (idempotent — safe if anything is already running):
'   1. Launch MT5 terminal64.exe (auto-logins from saved OctaFX credentials)
'   2. Wait 15 seconds for MT5 to bind to its files dir
'   3. Trigger TrendMaster Health Watchdog one-shot (it spawns webhook,
'      ngrok, executor, trailing if any are dead)
'   4. Trigger TrendMaster Live Dashboard launcher
'   5. Append a log line to logs/autostart.log
'
' Logs: C:\Users\Ratanshila\Documents\autmated trading\logs\autostart.log
' ==========================================================================
Option Explicit

Dim sh, fso, log, ts, line
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

Dim ROOT : ROOT = "C:\Users\Ratanshila\Documents\autmated trading"
Dim LOGF : LOGF = ROOT & "\logs\autostart.log"

' ----- helper: append timestamped log line (silent on failure) -----
Sub L(msg)
    Dim f
    On Error Resume Next
    Set f = fso.OpenTextFile(LOGF, 8, True)
    If Err.Number = 0 Then
        f.WriteLine "[" & Now() & "] " & msg
        f.Close
    End If
    On Error Goto 0
End Sub

L "=== autostart_pipeline.vbs START ==="

' ----- 1. MT5 -----
Dim mt5_running : mt5_running = False
On Error Resume Next
Dim wmi, procs, p
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set procs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='terminal64.exe'")
For Each p in procs
    mt5_running = True
Next
On Error Goto 0

If Not mt5_running Then
    L "MT5 not running -- launching terminal64.exe"
    sh.Run """C:\Program Files\MetaTrader 5\terminal64.exe""", 0, False
    WScript.Sleep 15000   ' wait 15s for MT5 to come up
Else
    L "MT5 already running -- skipping launch"
End If

' ----- 2. trigger Health Watchdog one-shot -----
On Error Resume Next
sh.Run "schtasks /Run /TN ""TrendMaster Health Watchdog""", 0, True
If Err.Number <> 0 Then L "watchdog trigger error: " & Err.Description
On Error Goto 0
L "Triggered TrendMaster Health Watchdog (will spawn webhook+ngrok+executor)"

' Wait a moment for watchdog to start its work
WScript.Sleep 5000

' ----- 3. trigger Live Dashboard one-shot -----
On Error Resume Next
sh.Run "schtasks /Run /TN ""TrendMaster Live Dashboard""", 0, True
If Err.Number <> 0 Then L "dashboard trigger error: " & Err.Description
On Error Goto 0
L "Triggered TrendMaster Live Dashboard"

' ----- 4. one more watchdog cycle 30s later, in case MT5 was slow to bind -----
WScript.Sleep 30000
On Error Resume Next
sh.Run "schtasks /Run /TN ""TrendMaster Health Watchdog""", 0, True
On Error Goto 0
L "Second Health Watchdog cycle (catches slow-MT5 case)"

L "=== autostart_pipeline.vbs DONE ==="
