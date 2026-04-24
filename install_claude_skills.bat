@echo off
setlocal EnableDelayedExpansion
set "DST=C:\Users\Ratanshila\AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\ac9da0bf-2265-4958-af10-77875313af13\93695bdb-d13f-4084-a5d5-56b87d48a3b9\skills"
set "SRC=C:\skills-tmp\claude-trading-skills\skills"

echo === Installing mql-developer ===
robocopy "C:\skills-tmp\mql-developer" "!DST!\mql-developer" /E /XD .git /NFL /NDL /NJH /NJS
echo robocopy rc=!ERRORLEVEL!

for %%S in (backtest-expert position-sizer macro-regime-detector signal-postmortem economic-calendar-fetcher exposure-coach trader-memory-core market-news-analyst data-quality-checker) do (
    echo === Installing %%S ===
    robocopy "!SRC!\%%S" "!DST!\%%S" /E /XD .git /NFL /NDL /NJH /NJS
    echo robocopy rc=!ERRORLEVEL!
)

echo.
echo === FINAL INVENTORY ===
dir /b "!DST!"
endlocal
