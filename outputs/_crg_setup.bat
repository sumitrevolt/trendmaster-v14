@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
call :run > "outputs\_crg_setup.out" 2>&1
exit /b
:run
echo ===CRG VERSION===
"C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\Scripts\code-review-graph.exe" --version
echo.
echo ===HELP (discovering commands)===
"C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\Scripts\code-review-graph.exe" --help
echo.
echo ===INSTALL (for claude-code, auto-yes)===
"C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\Scripts\code-review-graph.exe" install --platform claude-code --yes
echo.
echo ===BUILD (parse the codebase)===
"C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\Scripts\code-review-graph.exe" build
echo.
echo ===STATS===
"C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\Scripts\code-review-graph.exe" stats 2>nul
echo.
echo ===DONE===
