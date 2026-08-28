import sys
try:
    import ai_trading_agents.tv_webhook_receiver
    print("IMPORT OK")
except Exception as e:
    print("IMPORT FAIL:", type(e).__name__, e)
    import traceback
    traceback.print_exc()
    sys.exit(1)
