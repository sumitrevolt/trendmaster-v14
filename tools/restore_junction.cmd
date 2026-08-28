@echo off
REM =======================================================================
REM  RETIRED 2026-08-22: repo moved C:\Users\Ratanshila\Documents -> D:\
REM  and ai_trading_agents is now a REAL folder in the repo (no junction).
REM  The old rebuild logic would DELETE the real folder (rd /s /q on a
REM  non-junction path) - catastrophic. This stub now does nothing safely.
REM =======================================================================
echo [restore_junction] RETIRED - ai_trading_agents is a real folder on D:. No-op.
exit /b 0
