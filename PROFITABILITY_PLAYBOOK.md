# Profitability Playbook — TrendMaster v14

_Last rewrite: 2026-04-23. Replaces the older "dispatcher integration" doc — that integration path is not what runs in production. The brain calls `profit_filters.evaluate_all` directly inside `tick_once`, and as of 2026-04-22 also calls `risk_manager.check_risk` before writing any non-NONE direction._

This is the operator's reference for what gates a trade actually passes through, how to tune each knob, and where to look when the stack misbehaves. This is a paper-trading scaffold on a $300 OctaFX-Demo account — not a money printer. Everything here is about making a marginal edge survive real-world frictions: spreads, dead markets, news spikes, tilt after losses.

## The actual live signal path

Every 3 seconds, `tick_all()` in `ai_trading_agents/trend_master_brain.py` iterates all 19 symbols in `config.settings.TRADING_PAIRS` and calls `tick_once(symbol)` for each. `tick_once` (line 641) is the single source of truth for what reaches the EA. The pipeline — in order — is:

```
pull_bars → build_features → infer_ml →
  kill_switch(halted/trading_paused) →
    mtf_agree(fast+mid+slow) →
      conf >= MIN_CONF (0.62) →
        profit_filters.evaluate_all (7 gates) →
          multi_agent.vote_all (3/3 unanimous) →
            risk_manager.check_risk  [audit-fix 2026-04-22] →
              write_signal (atomic JSON)
```

Any stage that returns `NONE`/`block` short-circuits the rest and a `NONE` signal is written. The EA then simply won't fire regardless of its own three confirmations. The brain stashes the most recent veto reason per symbol on `state.last_veto_per_symbol`, which is what `/why XAUUSD` returns.

`profit_filters.evaluate_all` and `risk_manager.check_risk` overlap on purpose — daily loss, profit lock, and loss-streak all appear in both layers. Belt-and-braces. If settings drift between the two layers, the tighter of the two wins.

## The seven profit filters

Configured in `config/settings.py::PROFIT_OPTIMIZER` (lines 604–653) and implemented in `ai_trading_agents/profit_filters.py`.

### 1. `spread_guard` — DISABLED

Would block any trade where broker spread exceeds `max_spread_atr_ratio=0.25` (25%) of current ATR. **Currently disabled by operator policy (2026-04-22).** The reasoning: broker-side spread is noisy and can transiently spike, and the `vol_regime` dead-market check already catches the "is there any real tradable move here" question. Do not re-enable this without discussing — MEMORY notes this is a deliberate operator decision.

Implementation: `profit_filters.py:52`. Knob: `PROFIT_OPTIMIZER.spread_guard` (True/False toggle) and `PROFIT_OPTIMIZER.max_spread_atr_ratio`.

### 2. `vol_regime` — enabled

The real liquidity check. Looks at the last ~500 ATR(14) readings and blocks the trade if current ATR is below the 20th percentile (dead market — RR can't develop) or above the 95th percentile (spike regime — stops get blown out by noise). Knobs: `vol_min_quantile=0.20`, `vol_max_quantile=0.95`. Inside the sweet-spot band (45th–85th percentile) it hands a +0.05 nudge to confidence. Tuning: if you're vetoing 90% of EURGBP ticks, lower `vol_min_quantile` to 0.15 — but that'll mean more trades in genuinely dead sessions. Side-effect: logs spam when the market is persistently dead is rate-limited to one line per (symbol, reason) per 60 s by `_log_dedup`. Implementation: `profit_filters.py:84`.

### 3. `profit_lock` — enabled

Hard stop for the rest of the UTC day once intraday PnL hits `daily_profit_target_pct=2.0%`. The reasoning is empirical: most retail blowups happen after a green session when the trader keeps clicking. We just stop. Knob: `PROFIT_OPTIMIZER.daily_profit_target_pct`. Note: `RiskConfig` in `risk_manager.py` carries the same 2.0% default, so the two layers agree — but they're not reading the same number, they're both defaulting to it. If you raise one, raise the other. Implementation: `profit_filters.py:121`.

### 4. `loss_cooldown` — enabled

Counts trailing losses in `persistent["recent_results"]` via `trade_tracker.pnl_of` (handles both legacy float entries and new dict-shaped entries). Blocks once the streak hits `max_consec_losses=3`, or any time `persistent["cooldown_until_ts"]` is in the future (set elsewhere). One-away-from-cap gives a -0.05 confidence nudge — early tilt warning. Knobs: `max_consec_losses` (also mirrored in `RISK.max_consecutive_losses=2` — note the mismatch, the risk layer will fire first at 2 before profit_filters fires at 3), `cooldown_hours=4`. Implementation: `profit_filters.py:145`.

### 5. `session_window` — enabled

Blocks every hour outside `best_hours_utc = range(7, 21)` (07:00–20:59 UTC). London-NY overlap (12–16 UTC) gets a +0.03 confidence nudge. Important: this is a brain-wide filter and ignores per-symbol `PAIR_SESSION_FILTERS` in settings (those exist for other modules). Crypto runs 24/7 but the brain filter is global, so BTCUSD and ETHUSD only trade 07–21 UTC. Knob: `PROFIT_OPTIMIZER.best_hours_utc`. Implementation: `profit_filters.py:350`.

### 6. `news_blackout` — enabled

Reads `config/news_calendar.json` (cached 10 min) and blocks trades within ±`news_window_minutes=30` of any event whose `impact` matches `news_impact_levels=("high",)`. Fails open when the calendar is empty or missing — this is on purpose so a missing file doesn't halt the whole system, but it means an operator has to actually keep the file fresh. The calendar was repopulated 2026-04-22 with ~58 high-impact events covering 2026-Q2 through Q3 (FOMC, NFP, CPI, ECB, BOE, BOJ, Eurozone CPI flash). Refresh weekly from forexfactory.com or investing.com — the `_note` header in the JSON has the exact instructions. Implementation: `profit_filters.py:317`.

### 7. `daily_loss_limit` — enabled (the prop-firm trail)

Two thresholds, blocks on whichever trips first:
- `daily_max_loss_pct=3.0%` — hard stop at -3% vs start-of-day equity.
- `intraday_dd_pct=2.0%` — trails the intraday equity peak; locks once you've given back 2% from the high.

The intraday-peak trail catches the common "+1.5% in the morning, -1% by NY close" failure mode that a bare -3% stop would miss. Once tripped, `persistent["drawdown_lockout_until"]` is stamped to end-of-UTC-day (so an equity bounce doesn't unlock you) and a Telegram alert fires. Auto-resumes on the next UTC-midnight SoD roll. Implementation: `profit_filters.py:202`.

## Risk-layer tuning (`config/settings.py::RISK`, lines 222–254)

| Key | Current | Effect |
| --- | ------- | ------ |
| `risk_percent` | 0.5 | Per-trade % of equity put at risk. ~$1.50 max loss on a $300 account. **Kept in sync manually with MQL5 `InpRiskPct`** — see the block comment in settings lines 208–221. If you change one, change the other. |
| `max_daily_drawdown_percent` | 3.0 | Hard daily cap. Feeds `RiskConfig.max_daily_loss_pct`. Matches `PROFIT_OPTIMIZER.daily_max_loss_pct` by convention, not by reference. |
| `max_open_trades` | 2 | Portfolio cap. `max_open_per_team` is derived as `max(1, total//2 + 1) = 2`. |
| `max_consecutive_losses` | 2 | **Tighter than `PROFIT_OPTIMIZER.max_consec_losses=3`** — the risk layer trips first. If you want the profit-filter message to win, align these. |
| `min_lot_size` / `max_lot_size` | 0.01 / 0.03 | Hard clamps on `size_position` output. |
| `default_sl_atr_multiple` | 2.0 | Used by the brain when sizing lots via `size_position` (SL distance = ATR × 2.0). The EA uses its own `InpSL_AtrMult=1.5` — a known divergence, not a bug. |

Correlation-group caps and per-team caps are in `risk_manager.py` (`_CORR_GROUPS` at line 43, `TEAM_*` sets at lines 26–31). If a broker change renames a pair, update both `risk_manager.py::TEAM_*` and `config/settings.py::TRADING_PAIRS`.

## Reading Telegram output

- **`/status`** — model type (`lgbm` or `rule`), last signal across any symbol, live-vs-halted flag, restart count, mode (MULTI/SINGLE), MT5 account equity and balance.
- **`/pnl`** — today's PnL vs persisted SoD equity. If this looks wrong, check `persistent["start_of_day_equity"]` and `start_of_day_date` in `brain_state.json` — an incorrect SoD is the usual cause.
- **`/symbols`** — per-symbol last direction, confidence, and veto reason (if any). Good for "why isn't EURGBP firing?" at a glance.
- **`/why XAUUSD`** — last veto string for that symbol, including both profit-filter reasons and `risk_manager:` reasons (the post-audit risk gate appends to the same chain).
- **`/halt`** — sets both `halted=True` and `trading_paused=True` in `brain_state.json`, persists immediately. Emits a confirm alert. Existing open trades are untouched (EA still manages their TP/SL/BE).
- **`/resume`** — idempotent undo. Emits an alert.
- **`/ping`**, **`/help`** — cheap liveness and command list.

Telegram credentials live in `config/.env` and `ai_trading_agents/.env`. Missing creds or missing `requests` ⇒ the notifier silently no-ops; the brain runs identically without Telegram.

## Troubleshooting playbook

**"System isn't trading" — check the gates in this order:**

1. **`/status`** — is the brain halted? A `/halt` issued before a crash now survives the restart (post-audit), so you may have halted yourself days ago. `/resume` to clear.
2. **`/symbols`** — if every symbol shows a veto, check the shared-reason ones first. Common culprits in order of frequency:
   - `session: hour X UTC outside best window 7-20` — wait for London open, or tune `best_hours_utc`.
   - `news: ... in ±30m` — high-impact event nearby; expected.
   - `daily_dd: ...` — DD lockout is tripped; won't clear until UTC midnight. Check `/pnl`.
   - `regime: dead market: ATR < q20` — genuinely dead market. If it's every symbol, it's probably Sunday or a holiday; otherwise tune `vol_min_quantile` down.
   - `risk_manager: loss streak 2 >= cap 2` — loss cooldown tripped. Will clear when `cooldown_until_ts` expires (default 4 h).
   - `risk_manager: max open total 2 reached` — portfolio cap; positions need to close before any new entry.
3. **`brain_state.json`** — look at `halted`, `drawdown_lockout_until`, `cooldown_until_ts`, `start_of_day_equity`, `last_veto_per_symbol`. These four keys explain 90% of "why isn't it trading".
4. **Brain log** — `ticks_all summary: BUY=0 SELL=0 NONE=19 ERR=0` means filters are working, not that they're broken. `ERR=N` means `pull_bars` is failing — check MT5 connectivity.

**"Daily loss lock fired too early":** the SoD equity source changed post-audit to prefer `persistent["start_of_day_equity"]` and fall back to live `account_info().equity` only if no snapshot exists (previously read `account_info().balance`, which drifted against realized PnL — `trend_master_brain.py` lines 691–709). If `/pnl` shows a losing figure that doesn't match your account, check `start_of_day_equity` in `brain_state.json` — it may be stale from before a manual deposit. Fix: stop the brain, edit the value to match today's true opening equity, restart.

**"Halt didn't persist across restart":** pre-audit behaviour. The current build writes BOTH `halted` and `trading_paused` keys on `/halt`, and `tick_once` reads both — a halt issued before a crash IS still in effect after the supervisor restarts the brain (`trend_master_brain.py` lines 389–403 and 659–662). If you see this still happening, your build is older than 2026-04-22.

**"Signal file writes failing with WinError 5":** EA or dashboard is reading at the swap moment. Normal; `write_signal` retries 4 times with 50/100/200ms backoff. Only log once per failure. If you see persistent failures, close any dashboard that opens the JSON for read.

**"Telegram commands don't respond":** the command listener is a daemon thread. Missing creds ⇒ silent no-op. Confirm `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in both `config/.env` and `ai_trading_agents/.env`. Test with `/ping`.

## News calendar maintenance

`config/news_calendar.json` is a hand-curated list of `{ts_utc, event, impact}` objects. The file was populated 2026-04-22 with ~58 high-impact events covering 2026-Q2 and Q3 skeleton (FOMC ~6-week cadence, NFP first Friday, US CPI mid-month, ECB/BOE/BOJ, Eurozone/UK CPI). **Refresh weekly** from forexfactory.com or investing.com's economic calendar — exact release times drift and meetings get rescheduled. The header `_note` entry in the JSON (first element) documents the schema and refresh procedure. The cache TTL is 10 minutes, so edits take effect on the next tick.

Only `impact=high` events currently block (`news_impact_levels=("high",)`). To include medium-impact, widen to `("high", "medium")` in `PROFIT_OPTIMIZER`. Fail-open behaviour: an empty or missing file means "no news blackout", not "block everything" — this is deliberate but worth noting if you delete the file by accident.

## What the `reports/` directory contains

- `reports/AUDIT_*.md` — the prioritized audit pass from 2026-04-22 (strategy, risk, execution, opportunities). Source for the HIGH-severity fixes landed that day (risk_manager wiring, SoD equity source, halt persistence, news-calendar population).
- `reports/RISK_MODEL.md` — formal description of the risk layer, correlation groups, and the relationship between `RISK.risk_percent` and `InpRiskPct`.
- `reports/EA_PARITY.md` — notes on `ea_confirmations.py` and how a Python backtest lines up with live EA decisions.
- `reports/daily/YYYY-MM-DD.md` — daily PnL summaries emitted by the brain at UTC midnight via `_build_pnl_message`. Look here for the historical equity curve.
- `reports/tick_summaries/` — rolling 30 s `tick_all` snapshots if enabled. Useful for post-mortem but not required.

## Final note on expectations

This is a capital-preservation scaffold first, profit-seeking second. On a $300 account with 0.5% risk, a lockup of 3% is $9. Every gate in this stack is there to make sure we lose $9 slowly and rarely rather than $300 fast and once. Don't treat any of the percentages above as "aggressive" until you've backtested against `brain_memory.json` (task #12, in progress).
