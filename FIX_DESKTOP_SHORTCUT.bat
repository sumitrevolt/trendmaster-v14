@echo off
REM ====================================================================
REM  FIX_DESKTOP_SHORTCUT.bat  (compat wrapper)
REM  ---------------------------------------------------------------
REM  This used to copy a pre-built .lnk to the desktop. The system
REM  now uses INSTALL_DESKTOP_ICON.bat which (a) cleans up duplicate
REM  / legacy shortcuts first, then (b) installs ONE clean icon.
REM
REM  Kept as a wrapper so old muscle-memory still works.
REM ====================================================================
setlocal
cd /d "%~dp0"
echo.
echo Forwarding to INSTALL_DESKTOP_ICON.bat ...
echo.
call "%~dp0INSTALL_DESKTOP_ICON.bat"
endlocal
exit /b %ERRORLEVEL%
