# TrendMaster v14 — Setup & Operations Guide

**Date:** 2026-04-20  
**Purpose:** Fix the 36.4% M5 accuracy problem by replacing three conflicting entry systems with a single, tightly-integrated MT5 EA + Python ML brain, driven by a strict 3-of-3 confirmation gate.

---

## 1. What Changed (At a Glance)

Before, the same MT5 account was being driven by three Python scripts (`main.py`, `ai_swarm_main.py`, and `ai_trading_agents/main.py`) all writing orders under the same magic number, plus the `AI SUPERBB v13.0` indicator arrows that lit up on every small move. Losing 21 out of 36 signals on a 500-bar backtest was the expected outcome.

Now, there are exactly two moving parts:

- `AI_SUPERBB_v14_TrendMaster.mq5` — the EA that actually places and manages trades.
- `ai_trading_agents/trend_master_brain.py` — the ML brain that gates the EA.

Everything else (legacy scalper, swarm, and v13 indicator) is disabled via env-var guards. They still exist on disk for reference but refuse to start without a manual override.

---

## 2. The 3-of-3 Entry Rule

Every entry passes three independent checks on the last closed M5 bar, plus an optional fourth gate from the Python brain.

- **C1 — TREND.** SuperTrend(10, 3.0) direction, EMA(20) > EMA(50) > EMA(200), ADX(14) ≥ 22, price on the correct side of EMA(50). Long or short only.
- **C2 — VOLATILITY.** Price closes on the correct side of BB(20, 2.0) mid-line AND BB width is above its 50-bar median. This blocks squeeze / range entries — only trending expansion.
- **C3 — MOMENTUM.** MACD(12,26,9) histogram rising and positive for long (mirror for short) OR MACD line crossed above zero. Rejects counter-trend momentum.
- **AI gate (optional).** Python brain writes `trendmaster_signals.json` with `{"direction":"BUY","confidence":0.71,...}`. The EA only proceeds if direction matches AND confidence ≥ 0.58. If the file is missing or stale (> 60 s), the EA runs standalone.

Because all three are mandatory, the EA fires fewer signals — but each one has trend, volatility, and momentum pointing the same way.

---

## 3. Trade Management — Let Winners Run

The user's ask was "M5 trend pakadna, max profit lena." The EA rides each confirmed trend with a three-stage plan.

- **Entry.** SL = 1.5 × ATR(14). TP = 3.0 × ATR (1:2 R:R floor).
- **+1R.** Close 40% of position, move SL to break-even + a small ATR buffer.
- **+2R.** Close another 30%, lock SL at +1R.
- **Runner (30%).** Chandelier trail at HH(10) − 2 × ATR. Rides the trend until a clean trend-line break.

A dropping-ADX guard (added in `src/strategy.py::should_close_early`) closes early if ADX reverses against the position for three bars — that's the early-exit the analysis recommended.

---

## 4. The Millisecond Layer

The EA's `OnTick()` runs position management on every tick (throttled to one call per millisecond minimum). That covers trailing stops, break-even shifts, and partial closes. Entry signals stay on bar-close only to avoid repainting — but everything else reacts tick-by-tick.

The Python brain runs a sub-second inference loop (default 250 ms) via `TRENDMASTER_V14.inference_interval_ms`. On each tick it pulls fresh M5/M15/H1 bars, builds features, predicts, and atomically rewrites the signal file. The EA picks up the next read on the next bar close.

---

## 5. Install — One-Time Setup

### 5.1 Python side

Install the ML stack if you want the model gate (LightGBM is optional — the brain falls back to a rule-based classifier without it):

```
pip install lightgbm MetaTrader5 pandas numpy
```

### 5.2 MT5 side

1. Open MetaEditor (F4 in MT5). Copy `AI_SUPERBB_v14_TrendMaster.mq5` to `MQL5/Experts/` and compile (F7). Zero errors expected.
2. Drag the compiled EA onto an XAUUSD M5 chart.
3. Enable **Allow Algo Trading** in the MT5 toolbar.
4. In the EA inputs: set `InpMagic = 20260420`, `InpRiskPct = 1.0`, `InpUseAIGate = true`.

### 5.3 Start the brain

```
cd "C:\path\to\autmated trading"
python ai_trading_agents\trend_master_brain.py
```

The brain will connect to the running MT5 terminal, start writing `trendmaster_signals.json` into `MQL5/Files/`, and log inference each cycle.

---

## 6. Optional — Train a Real Model

The brain ships with a rule-based fallback so you can go live immediately. For a real edge, train a LightGBM model on your own history.

- Export OHLCV M5 bars to CSV (datetime index, columns `open,high,low,close,volume`).
- `python ai_trading_agents\trend_master_brain.py train bars.csv`
- The trained file `trend_master_model.lgb` is saved next to the brain and picked up automatically on next start.

The labeling rule is simple: look six bars ahead, label BUY if the forward move exceeds +1 × ATR, SELL if less than −1 × ATR, else NONE. Train-test split is 80/20 with early stopping on validation log-loss.

---

## 7. Go-Live Checklist

- OctaFX Demo account has ≥ $300 balance.
- `config/settings.py` shows the v14 FIX comments (confluences 6, ADX 22, volume 1.8, cooldown 7).
- `python main.py` and `python ai_swarm_main.py` both exit immediately with the legacy-disabled banner.
- EA attached to XAUUSD M5 with AutoTrading lit green.
- Brain process running and log line `TrendMaster brain online` visible.
- On the EA chart header, the `C1/C2/C3` line updates each minute.
- Signal file `MQL5/Files/trendmaster_signals.json` exists and refreshes.

If any of those fail, check the brain log and the MT5 Experts tab — both print the specific reason any entry was blocked.

---

## 8. Recommended First-Week Settings

- `InpRiskPct = 1.0` (per-trade risk, 1 %).
- `InpAdaptiveSize = false` for the first 40 trades — give Kelly a sample before enabling.
- `InpAIRequired = false` — run with AI gate as an advisor. Flip to true once you trust the brain.
- `InpBlockNewsWin = true` — the cheap :55–:05 filter. Later, feed news from `ai_trading_agents/geopolitical_agent.py`.

Review performance after ~50 trades. Target: ≥ 50% win rate with expectancy > 0.3R. If the brain + EA agree but the win rate is under 45%, shorten the cooldown or relax ADX from 22 → 20 — those are the two dials that most directly trade off frequency vs quality.

---

## 9. Files Touched in This Change

- `AI_SUPERBB_v14_TrendMaster.mq5` — new EA.
- `ai_trading_agents/trend_master_brain.py` — new ML brain.
- `config/settings.py` — tightened thresholds, added `TRENDMASTER_V14` block.
- `src/strategy.py` — raised cooldown, added M15 + ADX-reversal helpers.
- `main.py`, `ai_swarm_main.py` — legacy guards (fail-closed unless env var set).
- `TRENDMASTER_v14_GUIDE.md` — this document.

Everything else is untouched.
