@echo off
cd /d "C:\Users\Ratanshila\Documents\autmated trading"
python -c "from ai_trading_agents.trend_master_brain import _pair_sl_tp; [print(f'{s:8s}  team={t:12s}  SL={r[0]} TP={r[1]} ADX={int(r[2])}') for s,t,r in [(s, __import__('ai_trading_agents.team_params', fromlist=['SYMBOL_TO_TEAM']).SYMBOL_TO_TEAM.get(s,'?'), _pair_sl_tp(s)) for s in ['XAUUSD','XAGUSD','EURUSD','GBPJPY','USDCAD','BTCUSD','ETHUSD','XTIUSD','XNGUSD']]]"
