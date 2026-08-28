@echo off
REM Test chart_scrape_ocr module: scrape EURUSD M15 chart, detect BUY/SELL via color.
REM Result goes to outputs\chart_ocr_test_result.txt for inspection.
cd /d "%~dp0\.."
echo Running OCR smoke test on EURUSD M15... > outputs\chart_ocr_test_result.txt
echo Start: %DATE% %TIME% >> outputs\chart_ocr_test_result.txt
echo. >> outputs\chart_ocr_test_result.txt

.venv\Scripts\python.exe -m ai_trading_agents.chart_scrape_ocr EURUSD --tf M15 >> outputs\chart_ocr_test_result.txt 2>&1

echo. >> outputs\chart_ocr_test_result.txt
echo End: %DATE% %TIME% >> outputs\chart_ocr_test_result.txt
echo Exit code: %ERRORLEVEL% >> outputs\chart_ocr_test_result.txt
echo Done. Check outputs\chart_ocr_test_result.txt
timeout /t 3 /nobreak > nul
