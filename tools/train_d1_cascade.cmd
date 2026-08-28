@echo off
setlocal enabledelayedexpansion
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
set OUT=tools\train_d1_cascade_out.txt
echo [D1 CASCADE] Started %DATE% %TIME% > %OUT%

echo. >> %OUT%
echo ============================================================ >> %OUT%
echo [1/3] Phase D1-B3: Triple-barrier retrain with uniqueness weights >> %OUT%
echo ============================================================ >> %OUT%
.venv\Scripts\python.exe tools\train_v14_b3.py >> %OUT% 2>&1
set B3_RC=!ERRORLEVEL!
echo [B3 exit code: !B3_RC!] >> %OUT%

if !B3_RC! NEQ 0 (
    echo ERROR: B3 failed. Aborting cascade. >> %OUT%
    echo [D1 CASCADE ABORTED] >> %OUT%
    exit /b !B3_RC!
)

echo. >> %OUT%
echo ============================================================ >> %OUT%
echo [2/3] Phase D1-C1: Meta-label act/skip retrain with uniqueness weights >> %OUT%
echo ============================================================ >> %OUT%
.venv\Scripts\python.exe tools\train_v14_c1_metalabel.py >> %OUT% 2>&1
set C1_RC=!ERRORLEVEL!
echo [C1 exit code: !C1_RC!] >> %OUT%

if !C1_RC! NEQ 0 (
    echo ERROR: C1 failed. Aborting cascade. >> %OUT%
    echo [D1 CASCADE ABORTED] >> %OUT%
    exit /b !C1_RC!
)

echo. >> %OUT%
echo ============================================================ >> %OUT%
echo [3/3] Phase D1-C2: Per-team meta-label retrain with uniqueness weights >> %OUT%
echo ============================================================ >> %OUT%
.venv\Scripts\python.exe tools\train_v14_c2_metalabel_perteam.py >> %OUT% 2>&1
set C2_RC=!ERRORLEVEL!
echo [C2 exit code: !C2_RC!] >> %OUT%

echo. >> %OUT%
echo [D1 CASCADE DONE] B3=%B3_RC% C1=%C1_RC% C2=%C2_RC% >> %OUT%
echo Finished %DATE% %TIME% >> %OUT%
exit /b %C2_RC%
