# TrendMaster v14 — Multi-Timeframe Agents + HTF Gate

**Date:** 2026-04-22 11:03 IST
**Brain PID:** 20700 (alive, 3 s tick, writing signals w/ agent votes)
**MT5 PID:** 24496 (restarted 10:59:06, loaded new .ex5)
**Dashboard:** http://localhost:8000/ — HTTP 200, pushing agent votes to UI
**New EA .ex5:** 121,500 B, 0 errors, 0 warnings (was 103,186 B pre-HTF)

## What changed this session

Sumit's ask (Hinglish): *"m30 h1 timee frame bhi use karo and cot aur agents ko advance bano and sabhi chezze simple but profitable rakho"* —
i.e. use **M30 + H1 + H4** together, make the agents smarter, keep everything simple-but-profitable.

Two-part change, one on each side of the stack:

### 1. Python brain — `ai_trading_agents/multi_agent.py` (new)

Three independent rule-based specialist agents, each looking at one timeframe:

| Agent | TF | Rule |
|---|---|---|
| `trend_agent_h4` | H4 | EMA20 > EMA50 > EMA200 + ADX ≥ 20 + price on correct side of EMA20 |
| `momentum_agent_h1` | H1 | MACD histogram > 0 and rising (bull) / < 0 and falling (bear) |
| `timing_agent_m30` | M30 | Price vs EMA20 + RSI in 45-70 (bull) or 30-55 (bear) — blocks overbought/sold chase entries |

Each returns `AgentVote(name, vote, reason)`. The `vote_all(frames, min_votes=3)` bus requires **unanimous** non-zero agreement. Zero heavy ML, zero external APIs — every decision is auditable in one line of JSON.

### 2. `trend_master_brain.py` — wired agents into the main loop

- Added `USE_AGENTS` + `AGENT_MIN_VOTES` config flags (default ON, 3)
- `TrendMasterBrain.agent_vote()` pulls M30 + H1 + H4 bars and runs the bus
- `tick_once()` now requires **ML brain AND agent bus to agree** for a non-NONE direction
- `write_signal()` writes an `"agents"` block into `trendmaster_signals.json` with every vote + reason — fully visible in the dashboard

Sample live signal right now:
```json
{
  "direction": "NONE",
  "confidence": 0.5,
  "agents": {
    "dir": "NONE",
    "votes": [
      {"name":"trend_h4","vote":0,"reason":"no clean fan"},
      {"name":"momentum_h1","vote":1,"reason":"macd hist rising +6.42"},
      {"name":"timing_m30","vote":0,"reason":"no trigger rsi=83.8"}
    ]
  }
}
```
— correctly refusing to BUY at M30 RSI 83.8 even though H1 momentum is rising. This is the "simple but profitable" guard working.

### 3. `AI_SUPERBB_v14_TrendMaster.mq5` — HTF gate added

New input group **HTF GATE** (defaults ON):
- `InpUseHTFGate` (bool, true)
- `InpHTFTrendTF` = PERIOD_H4
- `InpHTFMomentumTF` = PERIOD_H1
- `InpHTFTimingTF` = PERIOD_M30
- `InpHTF_EMA_Fast/Slow/Trend`, `InpHTF_ADX_Period/Min`, `InpHTF_RSI_Period`, `InpHTF_MACD_*`

New handles: `h_htf_ema_f/s/t`, `h_htf_adx`, `h_h1_macd`, `h_m30_ema_f`, `h_m30_rsi` — created in `OnInit()` only when `InpUseHTFGate=true`.

New function `CheckHTFGate(dir_want, &reason)` — runs the same 3-agent voting logic directly in MQL5:
- H4 EMA fan + ADX ≥ 20 + price side
- H1 MACD histogram direction
- M30 price-vs-EMA20 + RSI in 45-70 (bull) or 30-55 (bear)

Called from `TryEntry()` **after the EA's 3-of-3 local check** and **before the AI gate**. Fails open on handle warm-up / NaN buffers (won't block valid setups during MT5 cold boot). Logs every decision with a human-readable reason via `DBG()`.

### 4. `config/settings.py` TRENDMASTER_V14 block

```python
'primary_timeframe':   'H1',          # trigger TF (mid-TF sweet spot)
'inference_interval_ms': 3000,        # 3s — agent checks are heavier than single-TF
'mtf_alignment':       {'M30': True, 'H1': True, 'H4': True},
'min_ml_confidence':    0.62,
'agent_min_votes':      3,
'use_multi_agent':      True,
```

## Double-gate architecture (current)

```
[ new bar close ]
   │
   ├─► EA computes 3 local confirmations (ST / BB / MACD) on its chart TF
   │   └─► agreed == 3 required
   │
   ├─► EA CheckHTFGate() — requires M30+H1+H4 unanimous alignment
   │   └─► any disagreement → BLOCK, log reason
   │
   └─► EA reads brain signal file
       └─► requires: signal.direction == entry dir
                     AND signal.confidence ≥ 0.55
                     AND signal.agents.dir == entry dir   (new — implicit via brain logic)
       └─► if AI gate PASS → send order
```

Translation: **every trade must pass four independent filters** (EA local 3/3, EA HTF gate, brain ML/rule direction, brain 3-agent vote). This is the "simple but profitable" — few signals, all of them high-conviction.

## Operational scripts (new/used)

- `C:\Users\Ratanshila\compile_ea.bat` — copy source → compile via metaeditor64
- `C:\Users\Ratanshila\restart_all.bat` — stop brain + MT5, restart both
- `C:\Users\Ratanshila\restart_brain_only.bat` — kill pythonw + restart brain + dashboard
- `C:\Users\Ratanshila\check_brain.bat` / `check_dash.ps1` / `check_ea.ps1` — health probes

## Verification snapshots

```
# Dashboard
HTTP 200, len=1875, MT5 connected, login 213796448, equity=545.70

# Signal file
age_sec=1.8  (brain tick = 3s → healthy)

# Agent votes in live signal
trend_h4:    vote=0  ("no clean fan")
momentum_h1: vote=+1 ("macd hist rising +6.42")
timing_m30:  vote=0  ("no trigger rsi=83.8") — correctly blocking chase

# EA binary
AI_SUPERBB_v14_TrendMaster.ex5  121,500 B  mtime 10:58:31
```

## Files touched

- `ai_trading_agents/multi_agent.py` (new, ~160 LOC)
- `ai_trading_agents/trend_master_brain.py` (edits: import, agent_vote(), tick_once(), write_signal())
- `config/settings.py` TRENDMASTER_V14 block (MTF + agent flags)
- `AI_SUPERBB_v14_TrendMaster.mq5` (HTF input group, handles, CheckHTFGate(), TryEntry() hook)
- `AI_SUPERBB_v14_TrendMaster.ex5` (recompiled 121 KB)
