# Trading Bot Skills

Codified best-practice guides for building and operating the TrendMaster v14 automated trading stack (MT5 EA + Python brain + MTF agents). Each folder is a self-contained skill with a single `SKILL.md` you can drop into any Cowork session for consistent scaffolding.

The guides blend patterns proven in this project with public GitHub reference repos (`freqtrade`, `EA31337`, `jimtin/algorithmic_trading_bot`, `pandas-ta`, `JAson.mqh`, `hudson-and-thames/mlfinlab`, `finautica/metatrader5-docker`, etc.).

## The 14 skills at a glance

Grouped by where they fit in the build / run lifecycle:

### Core build (5)

The minimum set to ship the project from scratch.

| Skill | Scope | When to use |
|---|---|---|
| [trading-mql5-ea](trading-mql5-ea/SKILL.md) | MQL5 Expert Advisor scaffolding | Building, extending, or reviewing an EA — file header, input groups, indicator handles, event handlers, `CheckHTFGate`, `TryEntry` funnel, CLI compile. |
| [trading-python-brain](trading-python-brain/SKILL.md) | Python signal engine | Bar pull via the MetaTrader5 module, vectorized features, multi-agent voting (M30/H1/H4), ML blending, loop cadence, atomic signal write. |
| [trading-risk-ops](trading-risk-ops/SKILL.md) | Risk + Windows ops | Percent-equity sizing, daily kill-switch, spread/session/news filters, break-even + trail, `.chr` template surgery, restart/health scripts, FastAPI dashboard. |
| [trading-backtest](trading-backtest/SKILL.md) | Training + evaluation | History pipeline, no-leakage features, ATR three-class labels, walk-forward LightGBM, equity/DD/Sharpe, A/B comparison, reproducibility. |
| [trading-bridge](trading-bridge/SKILL.md) | Brain ↔ EA contract | JSON schema + versioning, atomic writes, staleness checks, path resolution, debug sidecar, reverse `ea_state.json`, socket alternative. |

### Strategy & research (3)

Ideas, features, and signal recipes — the "what to trade" layer.

| Skill | Scope | When to use |
|---|---|---|
| [trading-strategies](trading-strategies/SKILL.md) | Named strategy recipes | Picking or combining strategies: Trend+Pullback, Breakout+Retest, Opening-Range, Mean-Reversion, Ichimoku, SuperTrend, Triple-Screen, MACD-Cross, Grid/Martingale danger-zones, ensemble voting. |
| [trading-indicators](trading-indicators/SKILL.md) | Indicator library — MQL5 + Python side-by-side | EMA/RSI/ADX/MACD/ATR/BBands/SuperTrend/Ichimoku/VWAP/Heikin-Ashi/Pivots/Order-Blocks/FVGs with matching Wilder smoothing so backtest ≈ live. |
| [trading-ml-features](trading-ml-features/SKILL.md) | Advanced ML feature engineering | Beyond EMA/RSI: alternative bars, fractional differentiation, triple-barrier + meta-labeling, regimes (HMM/GARCH), microstructure, feature selection. Based on mlfinlab / AFML. |

### Tuning & validation (2)

Turning signal ideas into statistically-real alpha.

| Skill | Scope | When to use |
|---|---|---|
| [trading-optimization](trading-optimization/SKILL.md) | Parameter search without overfitting | MT5 Strategy Tester modes, custom `OnTester()`, Optuna TPE, CPCV, deflated Sharpe, 5 overfitting-detection tests (parameter stability, time-robustness, similar-symbol, White's Reality Check, MC trade shuffling). |
| [trading-news-events](trading-news-events/SKILL.md) | Macro event handling | ForexFactory JSON feed, embargo windows, XAUUSD-sensitive event tiers (NFP/CPI/FOMC), weekend gap policy, MQL5 `LoadNews` / `NewsEmbargoed`. |

### Execution & portfolio (2)

The last 10 feet — getting fills and surviving multi-symbol.

| Skill | Scope | When to use |
|---|---|---|
| [trading-order-execution](trading-order-execution/SKILL.md) | `MqlTradeRequest` craftsmanship | `PickFilling()` via `SYMBOL_FILLING_MODE` bitmask, `ClampSLTP` against `STOPS_LEVEL`, retcode retry logic, deviation tuning, hedging vs netting, broker-specific quirks (OctaFX/ICMarkets/Exness/XM/FBS/FXCM/Pepperstone). |
| [trading-portfolio](trading-portfolio/SKILL.md) | Multi-symbol risk controls | Correlation matrix + clustering, per-cluster trade caps, natural-hedge detection, portfolio risk budget, concurrent-trade limits (brain + EA), margin-level kill-switch, brain↔terminal reconciliation. |

### Ops & diagnostics (2)

Keeping it running and debugging when it breaks.

| Skill | Scope | When to use |
|---|---|---|
| [trading-deploy-monitor](trading-deploy-monitor/SKILL.md) | 24/7 operations | Windows scheduled task + NSSM, Docker (brain / MT5-in-Wine), Prometheus + Grafana, Telegram/Discord alerts, log rotation, tailscale/Cloudflare remote, backups. |
| [trading-debug](trading-debug/SKILL.md) | Symptom → fix runbook | Funnel-based diagnosis, retcode table, PowerShell multi-tab log tailing, canary mode, incident postmortem template. First stop when something misbehaves in live. |

## How the skills fit together

```
         Research & signal design                    Risk & execution
    ┌──────────────────────────────┐        ┌──────────────────────────────┐
    │  trading-strategies          │        │  trading-order-execution     │
    │  trading-indicators          │        │  trading-portfolio           │
    │  trading-ml-features         │        │  trading-risk-ops            │
    └──────────────┬───────────────┘        └──────────────┬───────────────┘
                   │                                        │
                   ▼                                        │
    ┌──────────────────────────────┐                        │
    │  trading-optimization        │                        │
    │  trading-backtest            │                        │
    │  (validate before live)      │                        │
    └──────────────┬───────────────┘                        │
                   │ model.pkl, features.json               │
                   ▼                                        │
    ┌─────────────────────────────────────────────┐         │
    │  trading-python-brain                       │         │
    │  (live loop, multi-agent vote, signal)      │         │
    │  ── consults ── trading-news-events ──      │         │
    └───────────┬─────────────────────────────────┘         │
                │  writes                                   │
                ▼                                           │
    ┌─────────────────────────────────────────────┐         │
    │  trading-bridge                             │         │
    │  (JSON schema + atomic write/read)          │         │
    └───────────┬─────────────────────────────────┘         │
                │  reads                                    │
                ▼                                           ▼
    ┌─────────────────────────────────────────────────────────┐
    │  trading-mql5-ea                                        │
    │  (4-filter funnel → OrderSend with broker-aware         │
    │   filling/deviation/STOPS_LEVEL handling)               │
    └───────────┬─────────────────────────────────────────────┘
                │
                ▼
    ┌─────────────────────────────────────────────┐
    │  trading-deploy-monitor                     │   ← 24/7 operations
    │  trading-debug                              │   ← when it misbehaves
    └─────────────────────────────────────────────┘
```

## Using a skill in Cowork

Read the SKILL.md from this folder at the start of any conversation about the corresponding area. The skill tells you:

- When it applies
- The invariants to preserve
- The canonical code snippet to borrow from
- The common bugs
- The extension workflow (adding a new agent / filter / field / feature)

Don't paraphrase — the examples in each skill are tuned to match what actually works in this project.

## Which skill for which question

| You're about to... | Read first |
|---|---|
| Add a new input group to the EA | `trading-mql5-ea` |
| Add a new timeframe to the vote | `trading-python-brain` |
| Change position sizing logic | `trading-risk-ops` |
| Retrain the model | `trading-backtest` + `trading-ml-features` |
| Change the signal JSON contract | `trading-bridge` |
| Port a strategy from freqtrade | `trading-strategies` |
| Add / swap an indicator | `trading-indicators` |
| Run a parameter sweep | `trading-optimization` |
| Block trades around FOMC | `trading-news-events` |
| Fix "requote" / "invalid stops" errors | `trading-order-execution` + `trading-debug` |
| Add a second symbol | `trading-portfolio` |
| Make it a Windows service | `trading-deploy-monitor` |
| EA stopped taking trades | `trading-debug` |

## Editing the skills

Each skill is plain Markdown with YAML frontmatter:

```yaml
---
name: <skill-name>
description: "One paragraph describing when to invoke this skill."
---
```

Keep descriptions precise — Cowork uses them to decide which skill applies to a given request. If you change behavior (new patterns that replace old ones), update the corresponding skill in the same PR as the code change so docs never drift from reality.

## Related files in this project

- `AI_SUPERBB_v14_TrendMaster.mq5` — the EA the skills describe
- `ai_trading_agents/trend_master_brain.py` — the brain
- `ai_trading_agents/multi_agent.py` — the agent bus
- `config/settings.py` — TRENDMASTER_V14 block
- `MTF_AGENTS_STATUS.md` — rolling session status / latest changes
- `tools/dashboard.py` — FastAPI dashboard
- `C:\Users\Ratanshila\*.bat` / `*.ps1` — Windows ops scripts
