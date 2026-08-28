# Use Windows UIAutomation to find and invoke the MT5 AutoTrading toolbar button.
# UIA can interact with native controls without keyboard focus, may bypass UIPI for same-user processes.

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$root = [System.Windows.Automation.AutomationElement]::RootElement

# Find the MT5 main window
$mt5_cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "*OctaFX*")
# That's not quite right - PropertyCondition does exact match. Let's enumerate top-level windows.

$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$child = $walker.GetFirstChild($root)
$mt5 = $null
while ($child) {
    $name = $child.Current.Name
    if ($name -match "OctaFX|MetaTrader") {
        $mt5 = $child
        Write-Host "Found MT5 window: $name"
        break
    }
    $child = $walker.GetNextSibling($child)
}

if (-not $mt5) {
    Write-Host "MT5 window not found"
    exit 1
}

# Find all toolbar items by recursive search
function FindAllInvokable($element, $depth = 0) {
    if ($depth -gt 8) { return }
    try {
        $name = $element.Current.Name
        $cls = $element.Current.ClassName
        $type = $element.Current.ControlType.ProgrammaticName
        if ($name -match "[Aa]uto.?[Tt]rading|[Aa]lgo|[Aa]llow|[Tt]rading") {
            Write-Host "  Match: name='$name' class='$cls' type='$type'"
            try {
                $invoke = $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                if ($invoke) {
                    Write-Host "    >>> INVOKING this element"
                    $invoke.Invoke()
                    Start-Sleep -Milliseconds 500
                }
            } catch {
                Write-Host "    InvokePattern not supported: $_"
            }
            try {
                $toggle = $element.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
                if ($toggle) {
                    Write-Host "    >>> Toggle state: $($toggle.Current.ToggleState)"
                    $toggle.Toggle()
                    Start-Sleep -Milliseconds 500
                }
            } catch {}
        }
    } catch {}

    try {
        $c = $walker.GetFirstChild($element)
        while ($c) {
            FindAllInvokable $c ($depth + 1)
            $c = $walker.GetNextSibling($c)
        }
    } catch {}
}

Write-Host "`n=== Searching for AutoTrading control ==="
FindAllInvokable $mt5

Write-Host "`n=== Done ==="
