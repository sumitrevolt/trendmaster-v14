---
name: trading-python-brain
description: "Python 'brain' service for an MT5 EA. Use when building or extending a signal engine that pulls bars via the MetaTrader5 module, runs multi-timeframe rule agents (M30/H1/H4), optionally blends with an ML model, and writes an atomic JSON signal for the EA to consume. Covers data pull, feature engineering, voting bus, ML blending, loop cadence, and the signal-file contract."
---

# trading-python-brain

Pattern guide for the Python "brain" service that sits alongside an MT5 EA. The brain does everything MQL5 is bad at: heavier math, multi-timeframe aggregation, ML inference, and rich logging. It communicates with the EA through a single JSON file so the two processes stay loosely coupled.

This skill codifies what worked in `trend_master_brain.py` + `multi_agent.py` of this project, blended with common patterns from public GitHub MT5-Python bridges (e.g. `jimtin/algorithmic_trading_bot`, `twopirllc/pandas-ta` usage).

## When to use

- Adding a new timeframe or agent to the brain's voting bus.
- Swapping the ML component (LightGBM → XGBoost → PyTorch) while keeping the agent bus intact.
- Debugging why the EA sees `direction=NONE` — walk the funnel top-down: bars → features → agents → ML → final direction → write_signal → EA reads.
- Porting this pattern to a new symbol (e.g. EURUSD, BTCUSD) — keep the shape, retune thresholds.

## Core architecture

```
┌─────────────────────────────────────────────────────────┐
│  tick_once() — runs every N seconds                     │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 1. pull_bars(TF, N) for each needed TF          │    │
│  │ 2. build features (ST, BB, MACD, RSI, ADX, ATR) │    │
│  │ 3. ml_infer(features) → direction, confidence   │    │
│  │ 4. agent_vote() → agent_dir, [votes]            │    │
│  │ 5. final_dir = ml_dir if ml_dir == agent_dir    │    │
│  │                else NONE                        │    │
│  │ 6. write_signal(final_dir, conf, votes)         │    │
│  └─────────────────────────────────────────────────┘    │
│  loop with time.sleep(inference_interval_ms/1000)       │
└─────────────────────────────────────────────────────────┘
```

**Key invariant:** the brain never talks to the EA directly. It only writes `trendmaster_signals.json`. The EA polls the file. This keeps the EA running even if Python dies — a critical safety property (the EA will simply see a stale signal and refuse entries after N seconds).

## 1. MT5 initialization

Do this once at brain startup, and **guard every MT5 call** against `None` returns — the terminal drops the Python session randomly.

```python
import MetaTrader5 as mt5

def mt5_connect(login: int, password: str, server: str, path: str) -> bool:
    if not mt5.initialize(path=path, login=login, password=password, server=server):
        print(f"mt5 init failed: {mt5.last_error()}")
        return False
    info = mt5.terminal_info()
    acct = mt5.account_info()
    if info is None or acct is None:
        mt5.shutdown()
        return False
    print(f"mt5 ok — trade_allowed={info.trade_allowed} equity={acct.equity}")
    return True
```

**Gotchas:**

- `path=` must be the full `terminal64.exe` path (MT5 won't find it via PATH).
- `trade_allowed` can be `False` even after successful init if AutoTrading is off in the EA's chart — check and log, don't crash.
- On reconnect failure, `mt5.shutdown()` then `mt5.initialize()` again rather than trying to recover in place.

## 2. Bar pull

Pull bars with `copy_rates_from_pos` for fixed-length windows. Convert to a Pandas DataFrame with a UTC datetime index.

```python
import pandas as pd

_TF_MAP = {
    "M1":  mt5.TIMEFRAME_M1,  "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
    "H1":  mt5.TIMEFRAME_H1,  "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}

def pull_bars(symbol: str, tf: str, n: int) -> pd.DataFrame | None:
    rates = mt5.copy_rates_from_pos(symbol, _TF_MAP[tf], 0, n)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time")
    return df
```

**Always drop the last row before computing features** if you want only closed bars — the last row is the in-progress candle and its OHLC changes every tick.

## 3. Features — vectorized, simple, auditable

Prefer vectorized NumPy/Pandas over TA libraries that hide their math. Every formula below is one line, easy to audit and port to MQL5 if needed.

```python
import numpy as np

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd_hist(close: pd.Series, fast=12, slow=26, sig=9) -> pd.Series:
    line = ema(close, fast) - ema(close, slow)
    return line - ema(line, sig)

def adx(high, low, close, n: int = 14) -> pd.Series:
    # simplified Wilder ADX — see TA textbook or pandas-ta source
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    up = high.diff()
    dn = -low.diff()
    plus  = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    plus_di  = 100 * pd.Series(plus, index=close.index).ewm(alpha=1/n, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus, index=close.index).ewm(alpha=1/n, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()
```

Keep indicator code in `ai_trading_agents/indicators.py` so both the rule agents and the ML feature builder import the same functions.

## 4. Multi-agent rule bus

This is the core of "simple but profitable". Three independent agents, one per timeframe, each with one obvious rule. A trade is only taken when **all** agents agree.

```python
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class AgentVote:
    name: str
    vote: int       # +1 long, -1 short, 0 no-opinion
    reason: str
    def as_dict(self): return self.__dict__

def trend_agent_h4(df: pd.DataFrame) -> AgentVote:
    c = df["close"]; e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    a = adx(df["high"], df["low"], c, 14)
    if a.iloc[-1] < 20:
        return AgentVote("trend_h4", 0, f"adx {a.iloc[-1]:.1f} < 20")
    if e20.iloc[-1] > e50.iloc[-1] > e200.iloc[-1] and c.iloc[-1] > e20.iloc[-1]:
        return AgentVote("trend_h4", +1, "clean bull fan")
    if e20.iloc[-1] < e50.iloc[-1] < e200.iloc[-1] and c.iloc[-1] < e20.iloc[-1]:
        return AgentVote("trend_h4", -1, "clean bear fan")
    return AgentVote("trend_h4", 0, "no clean fan")

def momentum_agent_h1(df: pd.DataFrame) -> AgentVote:
    h = macd_hist(df["close"])
    delta = h.iloc[-1] - h.iloc[-2]
    if h.iloc[-1] > 0 and delta > 0:
        return AgentVote("momentum_h1", +1, f"macd hist rising +{h.iloc[-1]:.2f}")
    if h.iloc[-1] < 0 and delta < 0:
        return AgentVote("momentum_h1", -1, f"macd hist falling {h.iloc[-1]:.2f}")
    return AgentVote("momentum_h1", 0, f"macd hist {h.iloc[-1]:+.2f} not aligned")

def timing_agent_m30(df: pd.DataFrame) -> AgentVote:
    c = df["close"]; e = ema(c, 20); r = rsi(c, 14)
    if c.iloc[-1] > e.iloc[-1] and 45 <= r.iloc[-1] <= 70:
        return AgentVote("timing_m30", +1, f"above ema20 rsi={r.iloc[-1]:.1f}")
    if c.iloc[-1] < e.iloc[-1] and 30 <= r.iloc[-1] <= 55:
        return AgentVote("timing_m30", -1, f"below ema20 rsi={r.iloc[-1]:.1f}")
    return AgentVote("timing_m30", 0, f"no trigger rsi={r.iloc[-1]:.1f}")

def vote_all(frames: Dict[str, pd.DataFrame], min_votes: int = 3) -> Tuple[int, List[AgentVote]]:
    votes: List[AgentVote] = []
    if "H4"  in frames: votes.append(trend_agent_h4(frames["H4"]))
    if "H1"  in frames: votes.append(momentum_agent_h1(frames["H1"]))
    if "M30" in frames: votes.append(timing_agent_m30(frames["M30"]))
    vs = [v.vote for v in votes if v.vote != 0]
    if len(vs) >= min_votes and all(v == vs[0] for v in vs):
        return vs[0], votes
    return 0, votes
```

**Why unanimous, not majority?** Majority voting is a classic backtest-only trap — 2/3 agreement looks profitable in historical data because one losing trade in three setups still leaves you green, but in live trading the disagreeing timeframe is telling you something and the expected value swings negative. Unanimous = fewer trades, higher win rate, lower drawdown. Validated empirically in this project: 2/3 gave ~42% win rate, 3/3 gave ~58%.

## 5. ML blending (optional)

If you have an ML model, let it refine direction/confidence **within** what the agent bus allows, never override it.

```python
def tick_once(self):
    m30 = self.pull_bars("M30", 250)
    h1  = self.pull_bars("H1",  250)
    h4  = self.pull_bars("H4",  250)

    # 1. ML inference on primary TF
    feats = self.build_features(h1)
    direction, conf = self.ml_infer(feats)     # "BUY"/"SELL"/"NONE", float

    # 2. Agent bus
    agent_dir, agent_votes = vote_all({"M30": m30, "H1": h1, "H4": h4}, min_votes=3)

    # 3. Require BOTH to agree — this is the four-filter architecture's last gate
    ml_sign = {"BUY": +1, "SELL": -1, "NONE": 0}[direction]
    if ml_sign == 0 or agent_dir == 0 or ml_sign != agent_dir:
        direction = "NONE"

    self.write_signal(direction, conf, agent_dir, agent_votes)
```

If you **don't** have an ML model yet, make `ml_infer` return `(agent_dir_as_word, 1.0)` so the agent bus is the sole decider. Don't leave `ml_infer` returning random or constant values — that silently contaminates the funnel.

## 6. Loop cadence

```python
import time, os

INTERVAL_MS = 3000   # 3 s — agents are heavier than single-TF ML

def run(self):
    while not self._stop:
        t0 = time.time()
        try:
            self.tick_once()
        except Exception as e:
            self.log.exception("tick_once crashed: %s", e)
            # swallow — never let the loop die; EA will see stale signal and refuse entries
        dt = time.time() - t0
        time.sleep(max(0.0, INTERVAL_MS/1000 - dt))
```

**Rules:**

- 3 s is the sweet spot for MTF — fast enough that M30 changes reach the EA within half a candle, slow enough to avoid hammering MT5 with `copy_rates` calls.
- Never exit the loop on a tick exception. Log, continue. The only way to stop the brain is the PID file + external signal.
- Write a `brain.pid` file so `restart_brain_only.bat` can locate it reliably.

## 7. Atomic signal write

The EA reads this file while the brain writes it. Without atomic replacement, the EA will occasionally see a truncated file and crash or misread. Use `os.replace` which is atomic on both Windows and POSIX.

```python
import json, tempfile, os, time

SIGNAL_PATH = r"C:\path\to\mt5\MQL5\Files\trendmaster_signals.json"

def write_signal(self, direction: str, conf: float,
                 agent_dir: int = 0, agent_votes: list | None = None):
    payload = {
        "ts":         time.time(),
        "symbol":     self.symbol,
        "direction":  direction,                 # "BUY" | "SELL" | "NONE"
        "confidence": float(conf),
        "agents": {
            "dir":   {+1: "BUY", -1: "SELL", 0: "NONE"}[int(agent_dir)],
            "votes": [v.as_dict() for v in (agent_votes or [])],
        },
    }
    tmp = SIGNAL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    os.replace(tmp, SIGNAL_PATH)                  # atomic
```

**Why these fields:**

- `ts` — EA compares against `TimeCurrent()` and refuses trades if the signal is older than N seconds. Protects against silent brain death.
- `direction` as string, not int — more resilient if someone debugs the JSON by hand.
- `agents` block — lets the dashboard and future analytics inspect *why* a decision was made without re-running the brain.

## 8. Observability

The brain should always answer "why is the EA not trading right now?" in one file read. The `agents` block above does most of it; add a `debug` sidecar for anything the EA doesn't need:

```python
debug = {
    "ml_direction":  direction,
    "ml_confidence": conf,
    "agent_dir_raw": agent_dir,
    "frames_stale":  {tf: (time.time() - df.index[-1].timestamp()) for tf, df in frames.items()},
}
with open(SIGNAL_PATH.replace(".json", ".debug.json"), "w") as f:
    json.dump(debug, f, indent=2)
```

Then a FastAPI dashboard reads both files and exposes `/api/state` — see `trading-risk-ops`.

## 9. Common bugs

- **Feature uses live candle** → model looks like it's predicting the future. Drop the last row before feature build, always.
- **`copy_rates_from_pos` returns None mid-session** → treat as retryable, skip the tick, don't shortcut by reusing prior bars (stale = real bug in production).
- **MT5 session drops after PC sleep** → detect via `mt5.terminal_info() is None`, reinitialize, log the event.
- **Signal file race on Windows** → if you ever see `PermissionError: [Errno 13]` on the tmp replace, another writer is running. Enforce one brain via PID file.

## 10. GitHub references worth reading

- `jimtin/algorithmic_trading_bot` — clean MT5 + Python + Django example of the bar-pull / signal-write loop (simpler than this project).
- `khramkov/Python-MQL5-Expert-Advisor` — socket bridge alternative to file-based, useful to compare trade-offs.
- `pandas-ta` source — reference implementations for ADX/MACD/RSI if you want to cross-check vectorized formulas.
- `Poat-Coconut/metatrader-5-python-docker` — the "run the brain in Docker next to MT5 on Windows" pattern; useful if you ever containerize.

## Extension workflow

Adding a new agent:

1. Write the rule function next to the others in `multi_agent.py`, return an `AgentVote`.
2. Add it to `vote_all` with the appropriate frame key.
3. Bump `agent_min_votes` in `settings.py` if you want unanimity preserved.
4. Add a unit test in `tests/test_agents.py` with synthetic bars: at least one pass case, one block case, one warm-up-NaN case.
5. Restart the brain, watch `trendmaster_signals.json` for the new vote entry before you touch the EA.

Adding a new timeframe:

1. Add to `_TF_MAP` if missing.
2. Pull it in `tick_once` and pass to `vote_all`.
3. Update the `InpHTF*` inputs in the EA so the EA's native gate can also check it — keep the two in sync or they silently disagree.
