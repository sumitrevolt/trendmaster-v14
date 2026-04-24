@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
".venv\Scripts\python.exe" "outputs\_brain_diag.py" > "outputs\_brain_diag.out" 2>&1
echo DONE >> "outputs\_brain_diag.out"
