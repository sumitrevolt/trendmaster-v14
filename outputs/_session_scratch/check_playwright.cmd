@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
.venv\Scripts\python.exe -c "import playwright; from playwright.sync_api import sync_playwright; print('playwright import OK, version:', playwright.__version__)"
echo.
echo === Chromium browser binary check ===
.venv\Scripts\python.exe -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.executable_path; print('Chromium at:', b); p.stop()"
