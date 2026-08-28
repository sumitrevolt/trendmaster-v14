@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Graph DB at .code-review-graph\graph.db ===
powershell -NoProfile -Command "if (Test-Path '.code-review-graph\graph.db') { $g=Get-Item '.code-review-graph\graph.db'; '  EXISTS  ' + [math]::Round($g.Length/1024/1024,1) + ' MB  last update: ' + $g.LastWriteTime } else { '  MISSING' }"
echo.
echo === code-review-graph CLI ===
where code-review-graph 2>nul || echo   NOT on PATH
echo.
echo === Try graph_status.cmd ===
call graph_status.cmd 2>&1
echo.
echo === Plugin .plugin files breakdown ===
.venv\Scripts\python.exe -c "from pathlib import Path; import zipfile; [print(f'  {p.name}: {p.stat().st_size/1024:.1f} KB'); print('    Files inside:', sorted(zipfile.ZipFile(p).namelist())[:5], '...') for p in Path('.').glob('*.plugin')]" 2>&1 | findstr /v Traceback
