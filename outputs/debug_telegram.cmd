@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Test Telegram bot directly ===
.venv\Scripts\python.exe -c "import os, urllib.request as u, urllib.parse as up, json; from dotenv import load_dotenv; load_dotenv('config/.env'); bot=os.getenv('TELEGRAM_BOT_TOKEN','').strip(); chat=os.getenv('TELEGRAM_CHAT_ID','').strip(); print('  bot_token first/last 8:', bot[:8] + '...' + bot[-8:] if len(bot)>16 else bot); print('  chat_id:', chat); r=u.urlopen(f'https://api.telegram.org/bot{bot}/getMe', timeout=5); d=json.loads(r.read().decode()); print('  getMe:', d.get('ok'), d.get('result',{}).get('username') if d.get('ok') else d.get('description'))"
echo.
echo === Try sendMessage to confirm chat ===
.venv\Scripts\python.exe -c "import os, urllib.request as u, urllib.parse as up, json; from dotenv import load_dotenv; load_dotenv('config/.env'); bot=os.getenv('TELEGRAM_BOT_TOKEN'); chat=os.getenv('TELEGRAM_CHAT_ID'); body=up.urlencode({'chat_id':chat,'text':'TrendMaster TG test 2026-05-07'}).encode(); r=u.urlopen(u.Request(f'https://api.telegram.org/bot{bot}/sendMessage', data=body), timeout=8); d=json.loads(r.read().decode()); print('  sendMessage:', d.get('ok'), d.get('description') or 'OK')"
