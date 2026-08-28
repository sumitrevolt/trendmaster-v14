@echo off
setlocal
set NGROK="C:\Users\Ratanshila\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"
set TOKEN=3DFxTmM7V8s2FCoIektIMEDA0I9_7dSexxqLcemtcN7osQFC6
set DOMAIN=shadow-cosmos-unending.ngrok-free.dev
set LOGS=C:\Users\Ratanshila\Documents\autmated trading\logs

echo === current ngrok config ===
%NGROK% config check
echo.
echo === setting authtoken (idempotent) ===
%NGROK% config add-authtoken %TOKEN%
echo.
echo === killing any stale ngrok ===
taskkill /F /IM ngrok.exe 2>nul
timeout /T 2 /NOBREAK >nul

echo.
echo === launching tunnel detached ===
del /f /q "%LOGS%\ngrok.out" "%LOGS%\ngrok.err" 2>nul
start "ngrok-tunnel" /MIN cmd /c "title ngrok-tunnel && %NGROK% http 5005 --domain=%DOMAIN% --log=stdout 1>>\"%LOGS%\ngrok.out\" 2>>\"%LOGS%\ngrok.err\""

timeout /T 6 /NOBREAK >nul

echo.
echo === ngrok process state ===
tasklist /FI "IMAGENAME eq ngrok.exe" /NH

echo.
echo === ngrok.err tail ===
if exist "%LOGS%\ngrok.err" type "%LOGS%\ngrok.err"

echo.
echo === public health check ===
"C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\python.exe" -c "import urllib.request as u; r=u.Request('https://%DOMAIN%/health', headers={'ngrok-skip-browser-warning':'true'}); resp=u.urlopen(r, timeout=8); print('STATUS=', resp.status, 'BODY=', resp.read().decode())"
