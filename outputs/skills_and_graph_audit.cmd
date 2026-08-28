@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ============== 1. SKILLS INVENTORY ==============
echo.
echo --- docs\skills\ subfolders (skill folders) ---
powershell -NoProfile -Command "if (Test-Path 'docs\skills') { Get-ChildItem 'docs\skills' -Directory | Select-Object Name | Sort-Object Name | Format-Table -HideTableHeaders } else { Write-Host '  docs\skills/ does not exist' }"
echo.
echo --- *.plugin files in workspace root ---
powershell -NoProfile -Command "Get-ChildItem '*.plugin' -ErrorAction SilentlyContinue | Select-Object Name, @{N='SizeKB';E={[math]::Round($_.Length/1024,1)}} | Format-Table -AutoSize"
echo.
echo --- Skills count ---
powershell -NoProfile -Command "$d='docs\skills'; if (Test-Path $d) { '  total skills:' + (Get-ChildItem $d -Directory | Measure-Object).Count }"
echo.
echo --- Last 3 skill SKILL.md mtimes (which used recently?) ---
powershell -NoProfile -Command "Get-ChildItem 'docs\skills\*\SKILL.md' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | Select-Object @{N='Skill';E={$_.Directory.Name}}, LastWriteTime | Format-Table"
echo.

echo ============== 2. CODE-REVIEW-GRAPH STATE ==============
echo.
echo --- graph.db exists? ---
powershell -NoProfile -Command "if (Test-Path 'graph.db') { $g=Get-Item 'graph.db'; '  graph.db: ' + [math]::Round($g.Length/1024/1024,1) + ' MB, last update: ' + $g.LastWriteTime } else { Write-Host '  graph.db NOT found' }"
echo.
echo --- crg_hook.cmd exists? ---
powershell -NoProfile -Command "if (Test-Path 'tools\crg_hook.cmd') { '  hook present: tools\crg_hook.cmd' } else { '  hook MISSING' }"
echo.
echo --- Hook configured in .claude\settings.json? ---
powershell -NoProfile -Command "if (Test-Path '.claude\settings.json') { $j=Get-Content '.claude\settings.json' -Raw; if ($j -match 'crg_hook|code.review.graph') { '  hook IS configured in .claude/settings.json' } else { '  hook NOT in .claude/settings.json' } } else { '  .claude\settings.json missing' }"
echo.
echo --- Test the graph (semantic_search_nodes works?) ---
powershell -NoProfile -Command "$exe='.venv\Scripts\code-review-graph.exe'; if (Test-Path $exe) { '  CLI present: code-review-graph.exe' } else { '  CLI not in venv path' }"
.venv\Scripts\python.exe -c "import code_review_graph; print('  python module: import OK, version:', getattr(code_review_graph, '__version__', '?'))" 2>&1 | findstr /v Traceback
echo.
echo --- Last graph rebuild log ---
powershell -NoProfile -Command "if (Test-Path 'logs\crg_hook.log') { Get-Content 'logs\crg_hook.log' -Tail 5 } else { '  no crg_hook.log' }"
