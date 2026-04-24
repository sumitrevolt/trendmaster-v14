import sys, traceback
sys.path.insert(0, ".")
try:
    import config.settings as s
    print("SETTINGS OK")
    print("RISK.max_open_trades=", s.RISK.get("max_open_trades"))
    print("RISK.max_open_per_team=", s.RISK.get("max_open_per_team"))
    print("SESSION_BOOST=", getattr(s, "SESSION_BOOST", "MISSING"))
    print("REENTRY=", getattr(s, "REENTRY", "MISSING"))
    print("PYRAMID=", getattr(s, "PYRAMID", "MISSING"))
except Exception:
    print("SETTINGS FAIL")
    traceback.print_exc()
try:
    import ai_trading_agents.reentry_tracker as rt
    print("REENTRY TRACKER OK:", rt.__file__)
except Exception:
    print("REENTRY TRACKER FAIL")
    traceback.print_exc()
try:
    import ai_trading_agents.trend_master_brain as b
    print("BRAIN IMPORT OK:", b.__file__)
    print("has _effective_min_conf:", hasattr(b, "_effective_min_conf"))
    print("has SESSION_BOOST_CFG:", hasattr(b, "SESSION_BOOST_CFG"))
except Exception:
    print("BRAIN IMPORT FAIL")
    traceback.print_exc()
