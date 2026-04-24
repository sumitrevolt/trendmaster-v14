# TrendMaster v14 — Developer Guide

Short, opinionated guide for the changes you'll actually make. For the
user-facing install/start flow, see `README.md` and `INSTALL_v14.md`.

## Repo layout

    ai_trading_agents/     Python brain, agents, risk, dispatcher
    config/                settings.py + .env (credentials, pair list, flags)
    tools/                 CLI utilities (backtest, train, pull history, supervisor, dashboard)
    tests/                 pytest suite (no MT5 / no lightgbm required)
    data/                  OHLCV history CSVs + label files
    models/                Versioned LightGBM artifacts (registry)
    logs/                  brain / dashboard / supervisor runtime output
    AI_SUPERBB_v14_*.mq5   MetaTrader 5 Expert Advisor (execution layer)

## Running things

    python main.py scan                       # one-shot signal scan, all pairs
    python main.py run                        # live brain loop (MT5 required)
    python main.py dashboard                  # http://localhost:8000
    python main.py supervise                  # brain + dashboard with auto-restart
    python main.py backtest XAUUSD            # walk-forward on data/xauusd_m5_history.csv
    python main.py train XAUUSD               # binary "take this setup?" trainer
    python main.py pull-history --bars 50000  # fan out M5 history for every pair
    python main.py health                     # exit 0 if signal fresh + dashboard up
    pytest                                    # full unit + integration suite

## Adding a new trading pair

1. Add the symbol string to `TRADING_PAIRS` in `config/settings.py`.
2. Classify it in `ai_trading_agents/risk_manager.py` by adding it to
   one of `TEAM_METALS / TEAM_FOREX / TEAM_CRYPTO / TEAM_COMMODITIES`.
   If it correlates with an existing bucket, add it to the right set in
   `_CORR_GROUPS` to stop stacking same-direction trades.
3. Pull history: `python main.py pull-history --symbols NEWSYM`.
4. Backtest: `python main.py backtest NEWSYM`. Only ship it live if the
   report prints `Viable: True`.
5. Watch one live scan: `python main.py scan --symbols NEWSYM`.

## Adding a new agent

Agents are 20-line pure functions. Pattern:

    def my_agent(df: pd.DataFrame) -> AgentVote:
        if len(df) < 50:
            return AgentVote("my_agent", 0, "insufficient bars")
        # ... compute indicators ...
        if bull_condition:  return AgentVote("my_agent", +1, reason)
        if bear_condition:  return AgentVote("my_agent", -1, reason)
        return AgentVote("my_agent", 0, "no trigger")

Then wire it into `vote_all()` in `ai_trading_agents/multi_agent.py` and
add a test in `tests/test_multi_agent.py`.

## Adding a new gate to the risk manager

Open `ai_trading_agents/risk_manager.py::check_risk` and insert the new
check in priority order (cheapest / most-likely-to-fail first). Return a
`RiskDecision(False, "reason string")`. Write the test in
`tests/test_risk_manager.py` — follow the existing
"test_daily_loss_stop_blocks_trade" pattern.

## Running ML retraining end-to-end

    # 1. Let the system run 50-100 trades to populate logs/trades.csv
    # 2. Label them
    python -m tools.label_trades

    # 3. Retrain
    python main.py train XAUUSD
    # → new version lands in models/XAUUSD/YYYYMMDDTHHMMSS.lgb
    # → latest.lgb pointer is updated automatically

    # 4. A/B: compare vs rule-based via backtest
    python main.py backtest XAUUSD

    # 5. Roll back if you don't like the new one
    python -c "from tools.model_registry import rollback_to; \
               rollback_to('XAUUSD', '<older_version>')"

## Dashboard / health

Dashboard exposes two endpoints:

    GET /                Full-page live monitor (polls /api/state every 1 s)
    GET /api/state       JSON snapshot: signal, MT5 state, brain + EA logs
    GET /healthz         200 if the signal file is fresh (<60 s old), 503 otherwise

`tools/supervisor.py` uses `/healthz` as the readiness probe for
auto-restart. `python main.py health` is a thin wrapper.

## EA development

The MQL5 source is `AI_SUPERBB_v14_TrendMaster.mq5`. Recompile with
`python tools/compile_ea.py` (which shells out to `metaeditor64.exe`
and parses the UTF-16 compile log). The .ex5 lands in `Experts\` under
your MT5 data folder.

## Testing matrix

* MT5-free tests run in CI (`pytest` — see `.github/workflows/ci.yml`).
* `@pytest.mark.mt5` marks live-MT5 tests (none currently — add there
  if you write integration tests that need a real terminal).
* `@pytest.mark.slow` marks full backtests on the 50K-bar history.

Keep unit tests fast (<1 s each). Anything that needs MetaTrader5 or a
trained LightGBM model goes behind a `pytest.importorskip`.
