# =====================================================================
#  fix_desktop_shortcut.ps1  (DEPRECATED — kept as a thin redirect)
#  ---------------------------------------------------------------------
#  Use tools\install_desktop_icon.ps1 (or the friendlier double-click
#  INSTALL_DESKTOP_ICON.bat in the project root) instead.
#
#  This file just forwards so old documentation / muscle-memory works.
# =====================================================================
$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$newPath = Join-Path $here "install_desktop_icon.ps1"
if (-not (Test-Path $newPath)) {
    Write-Error "install_desktop_icon.ps1 missing next to this script."
    exit 1
}
Write-Host "[i] fix_desktop_shortcut.ps1 is deprecated — forwarding to install_desktop_icon.ps1"
& $newPath @args
exit $LASTEXITCODE
