@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo === Targeted search for brain_state files ===
dir /b /s "logs\brain_state*.json" 2>nul
echo ---
dir /b /s "C:\TrendMaster_aita_canonical\logs\brain_state*.json" 2>nul
echo ---
echo === Brain's effective state path (per _paths) ===
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from ai_trading_agents._paths import project_root; r=project_root(); print('project_root:', r); from ai_trading_agents.state_store import _DEFAULT_PATH as p; print('state path:', p); print('mtime:', __import__('datetime').datetime.fromtimestamp(p.stat().st_mtime).isoformat() if p.exists() else 'missing')"
echo ---
echo === MTime of the file we keep editing ===
powershell -NoProfile -Command "Get-Item 'logs\brain_state.json' | Select-Object FullName, LastWriteTime, @{N='SizeKB';E={[math]::Round($_.Length/1024,2)}} | Format-List"
echo ---
echo === Sample state file contents check ===
.venv\Scripts\python.exe -c "from pathlib import Path; import json; p=Path('logs/brain_state.json'); s=json.loads(p.read_text()); print('lockout:', s.get('drawdown_lockout_until')); print('SoD:', s.get('start_of_day_equity')); print('recent count:', len(s.get('recent_results', []))); print('last_saved_at:', s.get('last_saved_at'))"
