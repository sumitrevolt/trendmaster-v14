@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Install cTrader Open API library ===
.venv\Scripts\pip.exe install ctrader-open-api
echo.
echo === Verify import ===
.venv\Scripts\python.exe -c "from ctrader_open_api import Client, Protobuf, TcpProtocol, Auth; print('  ctrader_open_api: import OK')"
