@echo off
cd /d "%~dp0\.."
echo === Stale signal cleanup (Python, minute-level) ===
.venv\Scripts\python.exe -c "import os, time; from pathlib import Path; d = Path(r'C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files'); now = time.time(); deleted = []; [deleted.append(f.name) or f.unlink() for f in d.glob('trendmaster_signals*.json') if now - f.stat().st_mtime > 300]; print(f'Deleted {len(deleted)} stale signal files (>5 min old):'); [print(f'  - {n}') for n in deleted]; remaining = list(d.glob('trendmaster_signals*.json')); print(f'Remaining: {len(remaining)}'); [print(f'  + {f.name} ({int(now - f.stat().st_mtime)}s old)') for f in remaining]"
echo.
echo Done.
timeout /t 5 /nobreak > nul
