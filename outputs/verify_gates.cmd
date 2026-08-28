@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Searching tv_executor.py for each gate (junction view) ===
powershell -NoProfile -Command "Select-String -Path 'ai_trading_agents\tv_executor.py' -Pattern 'gate_block_news' -SimpleMatch | Measure-Object | Select-Object @{N='news_gate_lines';E={$_.Count}}"
powershell -NoProfile -Command "Select-String -Path 'ai_trading_agents\tv_executor.py' -Pattern 'gate_block_dd' -SimpleMatch | Measure-Object | Select-Object @{N='dd_gate_lines';E={$_.Count}}"
powershell -NoProfile -Command "Select-String -Path 'ai_trading_agents\tv_executor.py' -Pattern 'gate_block_corr' -SimpleMatch | Measure-Object | Select-Object @{N='corr_gate_lines';E={$_.Count}}"
echo.
echo === Same on canonical source ===
powershell -NoProfile -Command "Select-String -Path 'C:\TrendMaster_aita_canonical\tv_executor.py' -Pattern 'gate_block_news' -SimpleMatch | Measure-Object | Select-Object @{N='canon_news_lines';E={$_.Count}}"
echo.
echo === Junction status ===
powershell -NoProfile -Command "Get-Item 'ai_trading_agents' | Select-Object Name, LinkType, Target"
