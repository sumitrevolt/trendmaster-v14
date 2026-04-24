@echo off
title AI Trading Agents — Starting...
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║       AI TRADING AGENTS COMMAND CENTER              ║
echo  ║       Metals · Forex · Crypto · MT5 Live            ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: ── Kill any old instance ──────────────────────────────────────────
echo  [1/4] Stopping any running agents...
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo        Done.

:: ── Navigate to project folder ─────────────────────────────────────
cd /d "C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents"

:: ── Start the Python server in background ──────────────────────────
echo  [2/4] Starting AI agents (MT5 live mode)...
start "" /B "C:\Users\Ratanshila\AppData\Local\Programs\Python\Python311\python.exe" main.py > agent_out.txt 2> agent_err.txt
echo        Agents launched.

:: ── Wait for server to boot ────────────────────────────────────────
echo  [3/4] Waiting for server to be ready...
timeout /t 6 /nobreak >nul

:: ── Open dashboard in default browser ─────────────────────────────
echo  [4/4] Opening dashboard in browser...
start "" "http://localhost:8000"
echo        Dashboard opening at http://localhost:8000
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║  ✅  AGENTS RUNNING — Dashboard is open in browser  ║
echo  ║  📄  Logs: agent_err.txt / agent_out.txt            ║
echo  ║  ❌  Close this window to keep agents running       ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
pause
