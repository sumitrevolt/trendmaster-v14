@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
echo === Test exact path executor uses ===
.venv\Scripts\python.exe -c "from ai_trading_agents.telegram_notifier import get_notifier; n=get_notifier(); print('  enabled:', n.enabled); print('  token end:', n.token[-8:] if n.token else 'EMPTY'); print('  chat_id:', n.chat_id); ok=n.send('TG test from notifier path 2026-05-07'); print('  send result:', ok)"
