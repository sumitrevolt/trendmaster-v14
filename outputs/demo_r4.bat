@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ======================================================================
echo   R4 OPERATOR-GRADE FEATURE DEMO
echo ======================================================================

echo.
echo [A] main.py daily-report
python main.py daily-report
echo.

echo [B] main.py gates
python main.py gates --days 30
echo.

echo [C] Dashboard endpoints live?
echo.
echo [C.1] /performance
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing 'http://localhost:8000/performance' -TimeoutSec 5).Content.Substring(0, 400) } catch { Write-Host $_.Exception.Message }"
echo.
echo [C.2] /digest
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing 'http://localhost:8000/digest' -TimeoutSec 5).Content.Substring(0, 400) } catch { Write-Host $_.Exception.Message }"

echo.
echo ======================================================================
