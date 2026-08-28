@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === capture_create_post.json size ===
.venv\Scripts\python.exe -c "from pathlib import Path; p=Path('tools/tv_alert_setup/capture_create_post.json'); print('exists:', p.exists(), 'bytes:', p.stat().st_size if p.exists() else 0)"
echo.
echo === captured URL + content-type ===
.venv\Scripts\python.exe -c "import json; d=json.load(open('tools/tv_alert_setup/capture_create_post.json')); print('count:', len(d)); print('url:', d[0].get('url')); h=d[0].get('headers') or {}; print('content-type:', h.get('content-type') or h.get('Content-Type'))"
echo.
echo === pine_alert_template.json check ===
.venv\Scripts\python.exe -c "import json; t=json.load(open('tools/tv_alert_setup/pine_alert_template.json')); print('pine_id:', t.get('condition',{}).get('series',[{}])[0].get('pine_id')); print('webhook:', t.get('web_hook'))"
