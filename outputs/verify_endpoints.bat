@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo ======================================================================
echo   LIVE ENDPOINT VERIFICATION
echo ======================================================================

echo.
echo [1/4] /healthz
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8000/healthz' -TimeoutSec 5; Write-Host ('  HTTP ' + $r.StatusCode); Write-Host ('  ' + $r.Content) } catch { Write-Host ('  FAIL: ' + $_.Exception.Message) }"

echo.
echo [2/4] /metrics (first 30 lines)
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8000/metrics' -TimeoutSec 5; Write-Host ('  HTTP ' + $r.StatusCode); $r.Content.Split([Environment]::NewLine) | Select-Object -First 30 | ForEach-Object { Write-Host ('  ' + $_) } } catch { Write-Host ('  FAIL: ' + $_.Exception.Message) }"

echo.
echo [3/4] /signals
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8000/signals' -TimeoutSec 5; Write-Host ('  HTTP ' + $r.StatusCode); $c = $r.Content; if ($c.Length -gt 600) { $c = $c.Substring(0, 600) + '...' }; Write-Host ('  ' + $c) } catch { Write-Host ('  FAIL: ' + $_.Exception.Message) }"

echo.
echo [4/4] /pnl
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8000/pnl' -TimeoutSec 5; Write-Host ('  HTTP ' + $r.StatusCode); Write-Host ('  ' + $r.Content) } catch { Write-Host ('  FAIL: ' + $_.Exception.Message) }"

echo.
echo ======================================================================
