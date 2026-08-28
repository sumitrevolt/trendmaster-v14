@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Verify scripts compile ===
.venv\Scripts\python.exe -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in ['tools/ctrader_oauth.py','tools/ctrader_executor.py']]; print('  syntax OK')"
echo.
echo === Check current .env for cTrader keys ===
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); keys=['CTRADER_CLIENT_ID','CTRADER_CLIENT_SECRET','CTRADER_ACCESS_TOKEN','CTRADER_ACCOUNT_ID','CTRADER_HOST']; [print(f'  {k}: ' + ('SET' if os.getenv(k,'').strip() else 'MISSING')) for k in keys]"
echo.
echo === Setup guide path ===
echo   docs\IC_MARKETS_CTRADER_SETUP.md
