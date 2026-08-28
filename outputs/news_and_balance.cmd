@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

echo --- News calendar (proper read with utf-8) ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json; from datetime import datetime; p=Path('config/news_calendar.json'); cal=json.loads(p.read_text(encoding='utf-8')); age_days=(datetime.now().timestamp()-p.stat().st_mtime)/86400; print(f'  age: {age_days:.1f} days  ({\"STALE\" if age_days>7 else \"OK\"})'); print(f'  total events: {len(cal)}'); today=datetime.now().date(); todays=[e for e in cal if str(e.get(\"time\",\"\")).startswith(str(today))]; print(f'  today events: {len(todays)}'); next7=[e for e in cal if str(e.get(\"time\",\"\")) > datetime.now().isoformat()][:5]; print(f'  next 5 upcoming:'); [print(f'    {e.get(\"time\",\"?\"):20} {e.get(\"impact\",\"?\"):>4} {e.get(\"event\", e.get(\"title\",\"?\"))[:60]}') for e in next7]"
echo.

echo --- MT5 account state RIGHT NOW ---
.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv('config/.env'); import MetaTrader5 as mt5; mt5.initialize(login=int(os.getenv('MT5_LOGIN')), password=os.getenv('MT5_PASSWORD'), server=os.getenv('MT5_SERVER')); ai=mt5.account_info(); pos=mt5.positions_get() or []; print(f'  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}  free=${ai.margin_free:.2f}'); print(f'  floating P/L: ${ai.equity - ai.balance:+.2f}'); print(f'  DD vs balance: {((ai.balance - ai.equity) / ai.balance * 100):+.2f}%'); print('  POSITIONS:'); [print(f'    {p.symbol:7} {(\"BUY\" if p.type==0 else \"SELL\"):4} pnl=${p.profit:+7.2f} open={p.price_open:>10.4f} cur={p.price_current:>10.4f}') for p in pos]; mt5.shutdown()"
echo.

echo --- Brain log: any errors past hour? ---
powershell -NoProfile -Command "$cnt=(Select-String -Path 'logs\trend_master_brain.out' -Pattern 'ERROR|FATAL|Traceback' -ErrorAction SilentlyContinue | Where-Object { try { ([DateTime]::Parse($_.Line.Substring(0,19))) -gt (Get-Date).AddHours(-1) } catch { $false } }).Count; Write-Host ('  errors past hour: ' + $cnt)"
echo.

echo --- Latest TV signal pipeline activity ---
.venv\Scripts\python.exe -c "from pathlib import Path; import json, time; from datetime import datetime; lines=[json.loads(l) for l in Path('logs/tv_signals.jsonl').read_text().splitlines() if l.strip()]; recent=[r for r in lines if r.get('ts',0)>time.time()-3600]; print(f'  events past hour: {len(recent)}'); [print(f'    {datetime.fromtimestamp(r.get(\"ts\",0)).strftime(\"%%H:%%M:%%S\")} {r.get(\"event\",\"?\"):<18} {r.get(\"symbol\",\"-\"):8} dir={r.get(\"direction\",\"-\"):4} src={r.get(\"tv_strategy\",\"?\")[:25]}') for r in recent[-5:]]"
echo.

echo --- Plot direction logs (any since fix?) ---
powershell -NoProfile -Command "if (Test-Path 'logs\tv_plot_values.jsonl') { $lines=Get-Content 'logs\tv_plot_values.jsonl'; $real=$lines | Where-Object { $_ -notmatch 'symbol.*XAUUSD.*tf.*15.*p0.0|p1.0.*c=4685.50' }; Write-Host ('  total plot entries: ' + $lines.Count + ' (incl 5 dryrun tests)'); Write-Host ('  real Rocket Prime fires: ' + (if ($real.Count -gt 5) { $real.Count - 5 } else { 0 })) } else { '  no plot values log' }"
