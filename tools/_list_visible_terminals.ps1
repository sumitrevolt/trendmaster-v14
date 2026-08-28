# List ALL visible windows that are terminal-like
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Collections.Generic;
public class WinApi {
    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowTextW(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowTextLengthW(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@

$results = New-Object System.Collections.Generic.List[Object]
$proc = [WinApi]::EnumWindows({
    param($hwnd, $lparam)
    if ([WinApi]::IsWindowVisible($hwnd)) {
        $len = [WinApi]::GetWindowTextLengthW($hwnd)
        if ($len -gt 0) {
            $sb = New-Object System.Text.StringBuilder ($len + 1)
            [WinApi]::GetWindowTextW($hwnd, $sb, $sb.Capacity) | Out-Null
            $title = $sb.ToString()
            $pid = 0
            [WinApi]::GetWindowThreadProcessId($hwnd, [ref]$pid) | Out-Null
            $rect = New-Object WinApi+RECT
            [WinApi]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
            $w = $rect.Right - $rect.Left
            $h = $rect.Bottom - $rect.Top
            if ($w -gt 50 -and $h -gt 50) {
                $script:results.Add([PSCustomObject]@{
                    HWND = "0x{0:x}" -f $hwnd.ToInt64()
                    PID = $pid
                    Title = $title
                    Size = "${w}x${h}"
                })
            }
        }
    }
    return $true
}, [IntPtr]::Zero)

# Filter to terminal-like windows
$terminalLike = $results | ForEach-Object {
    $row = $_
    try {
        $procInfo = Get-Process -Id $row.PID -ErrorAction Stop
        $row | Add-Member -NotePropertyName ProcName -NotePropertyValue $procInfo.ProcessName -PassThru
    } catch {
        $row | Add-Member -NotePropertyName ProcName -NotePropertyValue "?" -PassThru
    }
} | Where-Object { $_.ProcName -in @("WindowsTerminal","cmd","conhost","powershell","pwsh","wt") -or $_.Title -match "OpenClaw|gateway|trading|bot" }

Write-Host "=== Currently VISIBLE terminal-like windows ==="
$terminalLike | Format-Table HWND,PID,ProcName,Title,Size -AutoSize -Wrap
Write-Host ""
Write-Host "Total: $($terminalLike.Count) visible terminal windows"
