# TrendMaster v14 — Multi-Market AI Trading System

Python brain + MetaTrader 5 Expert Advisor + multi-timeframe agent bus,
trading forex / metals / crypto / commodities on an OctaFX demo account.

Built-in double-gate architecture: **every trade must pass four
independent filters** — EA 3-of-3 local confirmation, EA HTF gate
(M30+H1+H4), Python brain direction, and 3-agent unanimous vote. Few
signals, all of them high-conviction. See `MTF_AGENTS_STATUS.md` and
`FINAL_UPGRADE_REPORT.md` for the deep detail; this README is the quick
start.

> **Historical note:** Earlier versions of this bot documented an
> "AMD Smart Money" strategy with self-learning weights. The v14 system
> replaced that with a transparent rule-based agent bus + EA 3-of-3
> confirmation. The authoritative design is `ARCHITECTURE.md` +
> `MTF_AGENTS_STATUS.md`.

## Architecture in one picture

```
  [ MT5 bars ]
        │
        ▼                                     (  Python brain + dashboard  )
  ┌───────────────────────────────────────────────────────────────────────┐
  │  main.py  ─────────────────────────────────────────────────────────▶  │
  │    scan / run / backtest / train / dashboard / supervise / health     │
  │                                                                       │
  │  ai_trading_agents/                                                   │
  │    trend_master_brain.py   ← inference loop, writes signal file       │
  │    multi_agent.py          ← trend_h4 + momentum_h1 + timing_m30 bus  │
  │    multi_market_dispatcher ← fan-out across TRADING_PAIRS             │
  │    risk_manager.py         ← sizing, daily-loss / concurrency / corr  │
  │                                                                       │
  │  tools/                                                               │
  │    backtest.py              ← walk-forward R-multiple report          │
  │    label_trades.py + retrain_from_trades.py + model_registry.py       │
  │    pull_history.py          ← M5 history for every pair               │
  │    dashboard.py (+ /healthz)                                          │
  │    supervisor.py            ← auto-restart brain + dashboard          │
  └───────────────────────────────────────────────────────────────────────┘
        │ writes                                      reads │
        ▼                                                    │
   trendmaster_signals.json  ◀── MetaTrader 5 EA ───────────┘
        (atomic file, refreshed every 250 ms – 3 s)
        AI_SUPERBB_v14_TrendMaster.mq5
```

## Quick start

### Prerequisites

* MetaTrader 5 (Windows) + an OctaFX demo account (or any broker)
* Python 3.10+
* Optional: LightGBM (`pip install lightgbm`) for the ML gate; without
  it the brain runs rule-based and is still fully functional.

### Install

```bash
cd "C:\Users\Ratanshila\Documents\autmated trading"
pip install -r requirements.txt

copy config\.env.example config\.env
notepad config\.env            # MT5_LOGIN / MT5_PASSWORD / MT5_SERVER
```

### Run

```bash
# One-shot multi-pair scan (offline-safe via CSVs in data/)
python main.py scan

# Live brain loop (needs MT5 running + EA attached on the chart)
python main.py run

# Or: supervisor that starts brain + dashboard and auto-restarts on crash
python main.py supervise

# Dashboard only (http://localhost:8000, /healthz for probe)
python main.py dashboard

# Backtest / train / pull history
python main.py backtest XAUUSD
python main.py pull-history --bars 50000
python main.py train XAUUSD

# Health probe (exit 0 if signal is fresh + dashboard up)
python main.py health
```

The legacy launchers still work:

```bash
START_TRENDMASTER_v14.bat       # start brain (detached)
STOP_TRENDMASTER_v14.bat        # stop brain
```

## Project layout

```
autmated trading/
├── main.py                     # Unified CLI (scan/run/backtest/train/...)
├── config/
│   ├── settings.py             # TRADING_PAIRS, TRENDMASTER_V14, risk, sessions
│   ├── .env                    # Credentials (gitignored)
│   └── .env.example
├── ai_trading_agents/
│   ├── trend_master_brain.py   # Live inference loop + signal writer
│   ├── multi_agent.py          # Trend/momentum/timing agent bus
│   ├── multi_market_dispatcher.py   # Fan-out across 20+ pairs / 4 teams
│   ├── risk_manager.py         # Sizer + gates (daily loss, team cap, corr)
│   └── *.json                  # Persisted memory (gitignored)
├── tools/
│   ├── backtest.py             # Walk-forward backtester
│   ├── label_trades.py         # Trades → R-multiple labels
│   ├── retrain_from_trades.py  # Binary "take this setup?" LightGBM
│   ├── pull_history.py         # Fan-out M5 history pull
│   ├── model_registry.py       # Versioned model storage + rollback
│   ├── supervisor.py           # Auto-restart brain + dashboard
│   ├── dashboard.py            # http://localhost:8000 + /healthz
│   └── compile_ea.py           # MQL5 compile helper
├── tests/                      # pytest — MT5-free, runs in CI
├── data/                       # OHLCV CSVs + label files (gitignored)
├── models/                     # Versioned LightGBM artifacts (gitignored)
├── logs/                       # Runtime output (gitignored)
├── AI_SUPERBB_v14_TrendMaster.mq5  # EA source
├── requirements.txt
├── Dockerfile + docker-compose.yml
├── pytest.ini
├── CHANGELOG.md   (timeline of v14 changes)
├── DEVELOPER_GUIDE.md  (how to add pair / agent / gate)
└── README.md  (this file)
```

## Markets traded

Configured in `config/settings.py::TRADING_PAIRS`:

* **Metals** — XAUUSD, XAGUSD
* **Forex** — GBPJPY, USDCAD, USDCHF, EURUSD, GBPUSD, AUDUSD, USDJPY,
  NZDUSD, EURJPY, EURGBP, AUDJPY, CADJPY
* **Crypto** — BTCUSD, ETHUSD
* **Commodities** — USOIL, UKOIL, XNGUSD, CORN, WHEAT

The dispatcher iterates all four teams. The live brain loop currently
primary-symbol is XAUUSD — see `ARCHITECTURE.md` for why (star performer
per backtests). Add more primary symbols by running multiple brain
processes with different `TRENDMASTER_V14.primary_symbol` overrides.

## Development

```bash
pytest                          # full unit + integration suite (no MT5 needed)
python -m compileall .          # syntax-check everything

# Docker (headless brain + dashboard, no MT5 — CI / dispatcher / backtest)
docker compose up --build
```

See `DEVELOPER_GUIDE.md` for how to add a symbol, agent, or risk gate.

## Safety features

* Daily loss stop (`RiskConfig.max_daily_loss_pct`)
* Global + per-team concurrency caps
* Correlation cap (e.g. can't stack EURUSD + GBPUSD + AUDUSD longs)
* Four independent filters per trade (EA 3/3, HTF gate, brain, agents)
* Atomic signal file writes — EA never reads a torn JSON
* Stale-check on signal timestamp — EA ignores signals > 60 s old
* Rule-based fallback if LightGBM is missing or model fails to load

## Risk disclaimer

Trading forex, metals, crypto, and commodities carries substantial risk
of loss. This software is provided for educational and research purposes
only. Use demo accounts to validate changes before going anywhere near
real money. See `LICENSE` for the full disclaimer.

## Operate

* Start brain (detached):    `START_TRENDMASTER_v14.bat`
* Stop brain:                 `STOP_TRENDMASTER_v14.bat`
* Supervised start:           `python main.py supervise`
* Live brain log:             `Get-Content logs\trend_master_brain.err -Wait -Tail 20`
* Re-pull history:            `python main.py pull-history --bars 50000`

## Where to read next

* `ARCHITECTURE.md` — component-level architecture
* `MTF_AGENTS_STATUS.md` — agent bus + HTF gate details
* `TRENDMASTER_v14_GUIDE.md` — operational guide
* `FINAL_UPGRADE_REPORT.md` — what was tried for ML and why it reverted
* `CHANGELOG.md` — dated timeline
* `DEVELOPER_GUIDE.md` — how to extend
