@echo off
setlocal EnableDelayedExpansion

echo === MT5 / MetaEditor search ===
echo.

set "ROOTS=C:\ C:\Program Files C:\Program Files (x86)"
for %%R in ("C:\" "C:\Program Files" "C:\Program Files (x86)") do (
    for /D %%D in (%%~R*) do (
        set "NM=%%~nxD"
        echo !NM! | findstr /I "MetaTrader Octa MT5 Exness" >nul
        if !errorlevel! EQU 0 (
            if exist "%%D\terminal64.exe"   echo terminal64 : %%D\terminal64.exe
            if exist "%%D\metaeditor64.exe" echo metaeditor : %%D\metaeditor64.exe
        )
    )
)

echo.
echo === MetaQuotes\Terminal\ ===
dir /B "%APPDATA%\MetaQuotes\Terminal" 2>nul

echo.
echo === origin.txt pointers ===
for /D %%T in ("%APPDATA%\MetaQuotes\Terminal\*") do (
    if exist "%%T\origin.txt" (
        echo --- %%~nxT ---
        type "%%T\origin.txt"
        echo.
    )
)
endlocal
