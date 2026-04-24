@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
call :run > "outputs\_install_crg.out" 2>&1
exit /b
:run
echo ===PYTHON VERSION===
C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe --version
echo ===PIP INSTALL code-review-graph===
C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe -m pip install --upgrade code-review-graph
echo ===VERSION CHECK===
C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe -m code_review_graph.cli --version 2>nul
where code-review-graph
echo ===RUN INSTALL (will auto-detect claude-code, cursor etc.)===
C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe -m code_review_graph.cli install --platform claude-code --yes 2>&1
echo ===BUILD GRAPH FOR TRADING PROJECT===
C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe -m code_review_graph.cli build
echo ===STATS===
C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe -m code_review_graph.cli stats 2>nul
