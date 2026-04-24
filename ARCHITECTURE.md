# TrendMaster v14 — Architecture

_Last rewrite: 2026-04-23. Supersedes the older "3 teams × 9 agents" doc, which referenced an entry point (`ai_trading_agents/main.py`) and a top-level `src/` tree that no longer exist outside `archive/`._

## Overview

TrendMaster v14 is a two-process trading scaffold running on a single Windows box against an OctaFX-Demo MT5 account. A Python **brain** (`ai_trading_agents/trend_master_brain.py`) pulls OHLC bars from MT5, runs feature engineering plus a LightGBM classifier (with a rule-based fallback), layers a stack of risk and profit gates on top, and atomically writes one JSON signal file per symbol. A compiled MQL5 **Expert Advisor** (`AI_SUPERBB_v14_TrendMaster.mq5`) runs inside the same MT5 terminal, reads those files on every tick, and will only fire an order when its own three-confirmation gate (SuperTrend / Bollinger / MACD) agrees with the Python direction. A Telegram notifier thread inside the brain emits alerts and accepts `/status /pnl /halt /resume /why /symbols /ping /help` commands. All three sides fail independently: the brain is safe if MT5 freezes, the EA is safe if the brain dies, and Telegram failures never crash the loop.

## System topology — 4 teams × 19 symbols

The authoritative list lives in `config/settings.py::TRADING_PAIRS` (lines 29–61) and is mirrored in `ai_trading_agents/risk_manager.py::team_of` (lines 26–39). Team membership is how the risk manager enforces per-team caps and correlation groups.

| Team            | Symbols                                                                                        | Count |
| --------------- | ---------------------------------------------------------------------------------------------- | ----- |
| **METALS**      | `XAUUSD`, `XAGUSD`                                                                             | 2     |
| **FOREX**       | `GBPJPY`, `USDCAD`, `USDCHF`, `EURUSD`, `GBPUSD`, `AUDUSD`, `USDJPY`, `NZDUSD`, `EURJPY`, `EURGBP`, `AUDJPY`, `CADJPY` | 12    |
| **CRYPTO**      | `BTCUSD`, `ETHUSD`                                                                             | 2     |
| **COMMODITIES** | `XTIUSD` (WTI), `XBRUSD` (Brent), `XNGUSD` (nat-gas)                                           | 3     |

Commodities use the broker's native `XTIUSD` / `XBRUSD` / `XNGUSD` names — the legacy `USOIL`/`UKOIL` symbols aren't listed on OctaFX-Demo (`config/settings.py` lines 52–60). `CORN` and `WHEAT` were removed for the same reason.

## Process model — who owns what

Three long-lived components run concurrently.

**The brain** is a single Python process launched under a supervisor. It owns feature engineering, the ML model, the multi-agent vote, the filter stack, the risk checks, state persistence, and signal-file emission. It acquires a cross-platform single-instance lock (`ai_trading_agents/process_lock.py`, `SingleInstanceLock("brain")`) before doing anything so a second accidental start refuses cleanly rather than corrupting the signal file with torn writes. When the lock is stale (holder PID no longer alive) it is force-released.

**The supervisor** (launched via `start_brain_supervised.cmd` / `scripts/supervisor.py`) is a thin watchdog that respawns the brain with exponential backoff if it crashes, and pushes a Telegram alert when it does. Restart count is persisted in `brain_state.json::restart_count` and visible in `/status`.

**The MQL5 Expert Advisor** is attached to one chart per symbol in the MT5 terminal. It is responsible for order sizing (using its own `InpRiskPct`, independent of Python's `RISK.risk_percent` — see the block comment in `config/settings.py` lines 208–221), stop / target management, partial closes, chandelier trailing, and broker-level daily loss kill-switch. EA inputs of note: `InpMagic=20260420`, `InpAISignalFile=trendmaster_signals.json`, `InpAIStaleSecs` (default 60) controls how long a brain signal is considered fresh, `InpAIRequired` controls whether the brain is a hard gate or advisory. When `InpAIRequired=true`, three EA confirmations AND a matching non-NONE Python direction are both required.

**The Telegram notifier** is a daemon thread spun up inside the brain's `run_forever`. Sends: startup, MT5-offline, drawdown lockout, daily-PnL summary at UTC midnight, per-symbol direction-change pushes (deduped so a sustained BUY doesn't spam). The command listener (`ai_trading_agents/telegram_commands.py`) long-polls Telegram and dispatches to handlers registered inside the brain (`_handle_halt`, `_handle_resume`, `_build_status_message`, `_build_pnl_message`, `_build_why_message`, etc.).

## The tick loop

Per-cycle inference is defined by `tick_once(symbol)` (`trend_master_brain.py:641`) and driven in multi-symbol mode by `tick_all()` (line 1186). Cadence is `TRENDMASTER_V14.inference_interval_ms = 3000` — 3 s is ample for H1/H4 bars, and we emit one condensed `tick_all summary` log line every 30 s covering all 19 symbols.

The full pipeline, in order:

1. **`pull_bars(TF, 500)`** — `_mt5_copy_rates_safe` wraps MT5 data pulls with a single re-init-and-retry on transient failure. Returns `None` on persistent failure and that symbol is skipped for the cycle.
2. **`build_features(df)`** — EMA / RSI / ATR / ADX plus rolling windows from `FEATURE_WINDOWS=[5,10,20,50]`.
3. **`infer_ml(x)`** — LightGBM (if installed) else a rule-based fallback. Returns `(direction, confidence)`.
4. **Kill-switch** — if `persistent["trading_paused"]` OR `persistent["halted"]` is True, force direction to `NONE`. Both keys are checked because `/halt` now writes the canonical `halted` key while `tick_once` historically read `trading_paused`; the audit fix of 2026-04-22 made both keys honour each other so a halt persists across restarts.
5. **`mtf_agree(direction, symbol)`** — pulls the mid and slow timeframes (`config.settings.timeframes_for(symbol)` — per-symbol overrides for XAU/metals → H1/H4/D1, JPY pairs → M15/M30/H1, default → M30/H1/H4) and requires all three to agree.
6. **Confidence gate** — `conf >= MIN_CONF` (default 0.62).
7. **`profit_filters.evaluate_all(...)`** — the seven-gate stack (see next section). On veto, direction drops to `NONE`, the reason is stashed in `self.state.last_veto_per_symbol[sym]` for `/why`, and if the veto came from the daily-DD gate specifically, `persistent["drawdown_lockout_until"]` is stamped to end-of-UTC-day with an operator Telegram alert.
8. **`agent_vote(symbol)`** — the multi-agent layer (`ai_trading_agents/multi_agent.py::vote_all`). Three agents (trend / momentum / timing), unanimous vote required (`agent_min_votes=3`). Final direction = intersection of ML sign and agent-bus sign; any disagreement ⇒ `NONE`.
9. **`risk_manager.check_risk(...)`** — newly wired on 2026-04-22 (three `[audit-fix 2026-04-22]` markers in `trend_master_brain.py` lines 63–71, 122, and 796–882). Runs only if direction is still BUY/SELL. Pulls live equity and open positions from MT5, sizes the lot using `risk_manager.size_position` with ATR-derived SL distance (`default_sl_atr_multiple=2.0`) and broker `trade_tick_value / trade_tick_size`, then calls `check_risk` which enforces: daily loss stop, daily profit lock, cooldown flag, loss-streak cap, `max_open_total`, `max_open_per_team`, correlation groups, min lot. On block, the reason is appended to the `/why` veto chain and direction becomes `NONE`.
10. **`write_signal(direction, conf, agent_dir, agent_votes, symbol)`** — atomic write to the per-symbol JSON (primary symbol XAUUSD keeps the legacy `trendmaster_signals.json` filename for backward-compat).
11. **Persist** — `StateStore.update_signal` every `PERSIST_EVERY_N_TICKS=10`, plus forced persist on direction change so a restart never re-fires the same direction.
12. **Telegram push** — only on per-symbol direction change, wrapped in try/except.

## Filter stack — seven gates

Defined in `ai_trading_agents/profit_filters.py`, composed by `evaluate_all()` (line 384). Configuration lives in `config/settings.py::PROFIT_OPTIMIZER` (lines 604–653). A trade is allowed only if every enabled gate returns `allow=True`.

| Gate              | Function                       | Status          | What it blocks |
| ----------------- | ------------------------------ | --------------- | -------------- |
| `spread_guard`    | `spread_guard` (L52)           | **DISABLED**    | Broker spread > 25% of ATR. Per operator policy 2026-04-22 — broker-spread alone shouldn't gate entries; the `vol_regime` dead-market check is the real liquidity filter. Do not re-enable without asking. |
| `vol_regime`      | `volatility_regime` (L84)      | enabled         | ATR in bottom 20% quantile (dead market) or top 5% (spike regime). |
| `profit_lock`     | `daily_profit_lock` (L121)     | enabled         | Stop trading once intraday PnL >= `daily_profit_target_pct` (default +2%). |
| `loss_cooldown`   | `loss_streak_cooldown` (L145)  | enabled         | After N consecutive losses (default 3) or while a cooldown window is active. |
| `session_window`  | `session_window` (L350)        | enabled         | Hours outside London/NY (default 07:00–20:59 UTC). |
| `news_blackout`   | `news_blackout` (L317)         | enabled         | ±30 min of any `impact=high` event in `config/news_calendar.json`. Fails open if calendar empty. |
| `daily_loss_limit`| `daily_loss_limit` (L202)      | enabled         | `max_loss_pct=3%` vs SoD equity OR `intraday_dd_pct=2%` from intraday peak. First to fire locks the UTC day via `drawdown_lockout_until`. |

Gates also return a `score_adjust` that nudges confidence up or down — `evaluate_all` sums them and the brain clamps final `conf` to `[0, 1]` before comparing to `MIN_CONF`.

## Risk layer

`ai_trading_agents/risk_manager.py` is pure Python, MT5-free at module level, unit-testable. It's now wired into `tick_once` and is the last gate before `write_signal`.

**Per-trade sizing** (`size_position`, L96): `risk_amt = equity * risk_pct/100`, `raw_lots = risk_amt / (sl_distance_price * pip_value_per_lot)`, stepped down to `lot_step=0.01` and clamped to `[min_lot, max_lot]`. Pip value is pulled from `mt5.symbol_info().trade_tick_value / trade_tick_size`; falls back to $10/lot if unavailable.

**Hard caps** (from `config/settings.py::RISK`): `risk_percent=0.5%`, `max_daily_drawdown_percent=3.0%`, `max_open_trades=2`, `max_consecutive_losses=2`, `min_lot_size=0.01`, `max_lot_size=0.03`. The `_build_risk_config` helper (L127) maps settings keys onto the `RiskConfig` dataclass and derives `max_open_per_team = max(1, total//2 + 1)` since settings has no explicit per-team knob.

**Correlation groups** (`_CORR_GROUPS`, L43): USD majors, USD-JPY/CHF/CAD, JPY crosses, metals, oils, crypto. Same-direction stacking inside any group is capped at `max_corr_same_dir=2`.

**Profit lock + daily loss stop** are enforced both in `risk_manager.check_risk` AND in `profit_filters.evaluate_all` using the same SoD equity source — belt-and-braces. The profit_filters copy owns the drawdown-lockout-until stamp.

**Daily-profit target** — note that `RISK` in `settings.py` doesn't set `daily_profit_target_pct` explicitly, so the `RiskConfig` default of 2.0% applies. `PROFIT_OPTIMIZER.daily_profit_target_pct=2.0` is the same number — they agree by accident, not by reference. Worth watching.

## State persistence

Two JSON files in the repo root.

`brain_state.json` is the durable brain state written by `ai_trading_agents/state_store.py::StateStore`. Schema includes: `halted` (canonical kill-switch), `trading_paused` (legacy alias — written in parallel), `start_of_day_equity`, `start_of_day_date`, `daily_drawdown_peak_eq`, `drawdown_lockout_until`, `cooldown_until_ts`, `recent_results` (rolling list used by loss-streak cooldown), `last_signal_per_symbol`, `last_veto_per_symbol`, `restart_count`, `daily_summary_sent_date`. Writes are atomic (temp file + `os.fsync` + `os.replace`), and `StateStore.update_signal` is the dedicated path for the hot hotspot.

`brain_memory.json` is the 500-trade rolling history consumed by `ai_trading_agents/ml_models/` for per-team LightGBM retraining. Managed by `ai_trading_agents/trade_tracker.py::TradeTracker`. Each entry is a dict with `pnl`, `r_mult`, entry/exit price, direction, symbol, and metadata — `trade_tracker.pnl_of()` is the shape-normalizer consumed by both filters and the risk manager.

**SoD equity source** (post-audit) prefers the persisted `start_of_day_equity` first and only falls back to live `account_info().equity` when no snapshot exists, persisting the fallback immediately. Previous code read `account_info().balance`, which drifted against realized PnL and broke the daily-DD gate (`trend_master_brain.py` lines 691–709).

## Ops

**Process lock** — `msvcrt.locking` on Windows, `fcntl.flock` on POSIX, same interface. Lock file is in `%LOCALAPPDATA%/TrendMaster` (Windows) or `/tmp` (POSIX) with the holder PID. Stale-PID cleanup is automatic.

**MT5 reconnect** — `_mt5_initialize_with_retry` does 5 attempts with exponential backoff capped at 60s. `_mt5_copy_rates_safe` does one re-init-and-retry on transient data-pull failures. If initialize() still fails after 5 attempts on boot, the brain exits with a Telegram `MT5 OFFLINE` alert and lets the supervisor handle restart.

**Telegram commands**: `/status` (model, last signal, paused flag, restart count), `/pnl` (today vs SoD equity), `/symbols` (per-symbol last direction + veto), `/why SYMBOL` (last veto reason), `/halt` (sets both `halted` and `trading_paused`, persists, emits alert), `/resume` (idempotent undo), `/ping`, `/help`. `/halt` durability: after the 2026-04-22 audit fix, a halt issued right before a crash is still in effect after the supervisor restarts the process.

**Supervisor alerts** — an alert-on-restart hook fires when `restart_count` increments beyond a threshold within a rolling window, surfaced in the same Telegram channel.

**EA parity backtest** — `ea_confirmations.py` reproduces the EA's C1/C2/C3 check in pandas bar-for-bar, so a Python backtest sees the same accept/reject as live.

## Signal file — atomic protocol

One JSON file per symbol. Primary (`XAUUSD`) uses the legacy name `trendmaster_signals.json` for EA backward-compat; every other symbol uses `trendmaster_signals_{SYMBOL}.json`. Schema:

```json
{"direction":"BUY","confidence":0.71,"ts":1712345678,"symbol":"XAUUSD","brain":"TrendMaster_v14","model":"lgbm","agents":{"dir":"BUY","votes":[...]}}
```

Write protocol (`write_signal`, L566): open `path + ".tmp"`, `json.dump` with compact separators, `flush`, `fsync`, then `os.replace(tmp, path)` — atomic on both NTFS and ext4. On `WinError 5` (EA or dashboard reading during the swap), retry up to 4 times with 50/100/200ms backoff. If all retries fail, log once and drop the tick rather than emit a torn write. EA enforces `InpAIStaleSecs=60` on the `ts` field, so a brain that hangs mid-write doesn't give stale direction forever.

## Data-flow diagram

```
                   ┌──────────────────────┐
                   │  MT5 Terminal (live) │
                   └──────────┬───────────┘
                              │ copy_rates_from_pos / account_info / positions_get
                              ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │  trend_master_brain.py  (Python, single-instance, supervised)    │
 │                                                                   │
 │   tick_all()                                                      │
 │     └─ for sym in ALL_SYMBOLS (19):                               │
 │          tick_once(sym):                                          │
 │            pull_bars → build_features → infer_ml                  │
 │            → kill_switch (halted / trading_paused)                │
 │            → mtf_agree (fast+mid+slow)                            │
 │            → conf >= MIN_CONF                                     │
 │            → profit_filters.evaluate_all (7 gates, 1 disabled)    │
 │            → multi_agent.vote_all (3/3 unanimous)                 │
 │            → risk_manager.check_risk [audit-fix 2026-04-22]       │
 │            → write_signal (atomic temp+fsync+replace)             │
 │            → StateStore.save (every 10 ticks + on change)         │
 │            → Telegram push (on direction change)                  │
 └────────────┬──────────────────────────────────────┬──────────────┘
              │ atomic JSON                           │ Telegram HTTPS
              ▼                                       ▼
 ┌─────────────────────────────────┐   ┌──────────────────────────┐
 │ trendmaster_signals_{SYM}.json  │   │ Telegram (notify + cmds) │
 └────────────┬────────────────────┘   │ /status /pnl /halt /why  │
              │ read each tick          └──────────────────────────┘
              ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │  AI_SUPERBB_v14_TrendMaster.mq5  (MQL5 EA, one per chart)        │
 │                                                                   │
 │   OnTick():                                                       │
 │     C1 TREND (EMA + SuperTrend + ADX)                             │
 │     C2 VOLA  (Bollinger mid + width)                              │
 │     C3 MOMO  (MACD histogram)                                     │
 │     + brain direction matches (InpAIRequired)                     │
 │     → TrySendOrder (InpRiskPct, InpMagic=20260420)                │
 │     → partial TPs, BE, chandelier trail                           │
 └──────────────────────────────────────────────────────────────────┘
```

## Planned, not live

- Per-team LightGBM retraining pipeline (task #13).
- Real-data backtest harness against `brain_memory.json` (task #12).
- Shared config file read by both Python and MQL5 (today `RISK.risk_percent` and `InpRiskPct` are kept in sync manually — see `config/settings.py` lines 208–221).
