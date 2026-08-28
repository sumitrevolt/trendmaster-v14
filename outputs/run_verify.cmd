@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
".venv\Scripts\python.exe" "outputs\verify_safeguards_changes.py" > "outputs\verify_output.txt" 2>&1
type "outputs\verify_output.txt"
echo --- results ---
type "outputs\verify_results.json"
