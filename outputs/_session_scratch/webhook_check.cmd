@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === HEALTH ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/health', timeout=8); print(r.status, r.read().decode()[:300])"
echo.
echo === STATUS ===
.venv\Scripts\python.exe -c "import urllib.request as u; r=u.urlopen('https://shadow-cosmos-unending.ngrok-free.dev/status', timeout=8); print(r.status, r.read().decode()[:300])"
