@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === verify tv_executor imports cleanly ===
.venv\Scripts\python.exe -c "from ai_trading_agents import tv_executor; print('  import OK')"
echo.
echo === verify gates appear in source ===
powershell -NoProfile -Command "Select-String -Path 'ai_trading_agents\tv_executor.py' -Pattern 'gate_block_news|gate_block_dd|gate_block_corr' | Measure-Object | Select-Object @{N='GateLines';E={$_.Count}}"
echo.
echo === restart webhook to load new tv_executor ===
call start_tv_webhook.cmd
