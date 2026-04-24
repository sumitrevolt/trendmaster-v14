@echo off
REM =======================================================================
REM  tools\add_remote.cmd <git-url>
REM
REM  Adds a remote named "origin" to this repo and pushes main up. Use
REM  after creating an empty repo on GitHub/GitLab/Bitbucket.
REM
REM  Usage:
REM    tools\add_remote.cmd https://github.com/<you>/trendmaster-v14.git
REM    tools\add_remote.cmd git@github.com:<you>/trendmaster-v14.git
REM
REM  Why a script: the first push also needs -u (upstream) so future
REM  `git push` / `git pull` without args work. Easy to forget.
REM =======================================================================
setlocal
pushd "%~dp0\.."

if "%~1"=="" (
    echo Usage: %~nx0 ^<git-url^>
    echo   e.g. %~nx0 https://github.com/Sumit/trendmaster-v14.git
    popd
    exit /b 1
)

if not exist ".git" (
    echo [add_remote] No .git directory; run `git init` first.
    popd
    exit /b 1
)

set "URL=%~1"

git remote remove origin >nul 2>nul
git remote add origin "%URL%"
if errorlevel 1 (
    echo [add_remote] git remote add failed.
    popd
    exit /b 1
)

echo [add_remote] Remote "origin" set to %URL%
echo [add_remote] Pushing main upstream...
git push -u origin main
set "RC=%ERRORLEVEL%"

popd
endlocal & exit /b %RC%
