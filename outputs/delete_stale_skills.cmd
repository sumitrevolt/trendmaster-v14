@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Archiving 3 stale skills ===
if not exist "docs\skills\_archive_2026-05-06" mkdir "docs\skills\_archive_2026-05-06"
move "docs\skills\trading-alert-bridge" "docs\skills\_archive_2026-05-06\" 2>nul
move "docs\skills\trading-events-rotator" "docs\skills\_archive_2026-05-06\" 2>nul
move "docs\skills\trading-next-prompt" "docs\skills\_archive_2026-05-06\" 2>nul
echo.
echo === Verify (these 3 should be gone from docs\skills\) ===
powershell -NoProfile -Command "Get-ChildItem 'docs\skills' -Directory | Where-Object { $_.Name -in 'trading-alert-bridge','trading-events-rotator','trading-next-prompt' } | Select-Object Name | Format-Table"
echo.
echo === Remaining skills count ===
powershell -NoProfile -Command "$d='docs\skills'; '  ' + (Get-ChildItem $d -Directory | Where-Object { -not $_.Name.StartsWith('_') } | Measure-Object).Count + ' active skills, ' + (Get-ChildItem $d -Directory | Where-Object { $_.Name.StartsWith('_archive') } | ForEach-Object { (Get-ChildItem $_.FullName -Directory | Measure-Object).Count } | Measure-Object -Sum).Sum + ' archived'"
echo.
echo === Archive location ===
dir /b "docs\skills\_archive_2026-05-06"
