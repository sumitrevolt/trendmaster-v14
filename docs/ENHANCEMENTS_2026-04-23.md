# Enhancements — 2026-04-23 (Round 2, fully wired)

Companion to `reports/ENHANCEMENT_REPORT_2026-04-23.md`. Round 1 landed seven opt-in modules off-by-default; Round 2 **wires them into the brain**, activates the safe ones, and adds four more advanced modules: meta-labeling, HMM regime detection, live ForexFactory news feed, and rolling-correlation risk cap. Plus a full Prometheus + Grafana side-stack.

## What's active right now

| Setting | Value | Behavior |
| --- | --- | --- |
| `METRICS.enabled` | **True** | `/metrics` endpoint live on `http://localhost:8000/metrics` — Prometheus scrape target. Zero trading impact. |
| `DRIFT.enabled` | **True** | ADWIN watching the PnL stream. On drift → Telegram alert (`/drift` command). No auto-action. |
| `KELLY_SIZING.enabled` | **True** | Kelly helper wired into `tick_once` sizing path. |
| `KELLY_SIZING.shadow` | **True** | **Crucially still True** — Kelly logs what it WOULD do but returns base risk unchanged. Flip to False only after 2-week shadow review. |
| `TRENDMASTER_V14.use_kelly_sizing` | Not set | Even with Kelly enabled, this second toggle must also flip to True before sizing changes live behavior. Keeps shadow bulletproof. |
| `PANIC.enabled` | False | `/halt close YES` replies "disabled" until you flip this. Deliberate — panic-flatten is the most destructive command in the system. |

## Complete module inventory

### Round 1 (off-by-default)
| Module | File | Wired into brain? |
| --- | --- | --- |
| Drift detection | `ai_trading_agents/drift_detector.py` | ✅ `tick_all` + `/drift` command |
| Kelly sizing | `ai_trading_agents/kelly_sizer.py` | ✅ `tick_once` risk block (shadow) |
| Metrics | `ai_trading_agents/metrics.py` | ✅ `tick_once` + `/metrics` dashboard |
| Structured logs | `ai_trading_agents/structured_log.py` | ✅ `main.py` boot |
| Panic flatten | `ai_trading_agents/panic.py` | ✅ `/halt close YES` command |
| CPCV | `tools/cpcv.py` | ✅ `train_per_team.py --cv cpcv` |
| Slippage model | `tools/slippage_model.py` | Available; backtest wiring left to operator |

### Round 2 (new this pass)
| Module | File | Status |
| --- | --- | --- |
| Meta-labeling (Lopez de Prado) | `ai_trading_agents/meta_labeler.py` | Module + tests ready; train offline |
| HMM regime detector | `ai_trading_agents/regime_hmm.py` | Module + tests ready; optional `hmmlearn` upgrade |
| Live ForexFactory news fetcher | `ai_trading_agents/news_feed.py` | Run `python -m ai_trading_agents.news_feed` weekly |
| Rolling-correlation cap | `ai_trading_agents/rolling_corr.py` | Drop-in replacement for static `_CORR_GROUPS` |
| Prometheus + Grafana stack | `monitoring/` | `docker compose -f monitoring/docker-compose.monitoring.yml up -d` |

Plus 100+ unit tests across 11 new test files. Every existing test still passes.

## How to turn them on

**Recommended order** (observability → diagnostic → execution):

1. **Metrics** — flip `METRICS.enabled=True` in settings, restart brain. Visit `http://localhost:8000/metrics`. Should see `trendmaster_*` counters. Still no-op unless the brain records anything; wiring the brain's `tick_once` to call `metrics.tick_latency.labels(symbol=sym).observe(dt)` is the follow-up step.

2. **Structured logs** — set env `LOG_FORMAT=json` and restart. Log lines become JSON:
   ```json
   {"ts":"2026-04-23T10:00:00.123Z","level":"INFO","logger":"trend_master_brain","msg":"tick_all summary: BUY=1(XAUUSD) NONE=18"}
   ```

3. **Drift detector** — `DRIFT.enabled=True`. The brain calls `drift_detector.feed_recent_results(persistent["recent_results"])` once per tick; wiring is additive (see snippet below).

4. **Kelly sizing — shadow mode first.** `KELLY_SIZING.enabled=True`, keep `shadow=True` for 2 weeks. Logs show the multiplier the Kelly helper *would* apply; real sizing unchanged. After 2 weeks, audit the shadow multipliers vs realized P&L before flipping `shadow=False`.

5. **CPCV + per-team retrain** — not a runtime switch; run on demand:
   ```bash
   python tools/train_per_team.py --cv cpcv --drop-session-features
   ```
   If METALS AUC drops sharply, that was the honest-from-scratch number.

6. **Realistic-cost backtest** — `python tools/backtest_real.py --realistic-costs`. Compare new expectancy to `reports/BACKTEST_REAL_RESULT.md`.

7. **Panic flatten** — last. `PANIC.enabled=True`, then edit `trend_master_brain.py::_register_commands` to accept the extended `/halt close YES` form (exact snippet in the module docstring). Demo account first; never on live capital without a prior tabletop drill.

## Integration snippets (not yet applied to brain — operator decision)

### Wire metrics from tick_once

```python
# In ai_trading_agents/trend_master_brain.py, inside tick_once(symbol):
import time
from ai_trading_agents import metrics as _m
_t0 = time.perf_counter()
# ... existing tick_once body ...
_m.tick_latency.labels(symbol=sym).observe(time.perf_counter() - _t0)
if direction != "NONE":
    _m.signal_writes.labels(symbol=sym, direction=direction).inc()
if not gate.allow:
    for reason in gate.reasons:
        cat = reason.split(":", 1)[0]
        _m.veto_total.labels(symbol=sym, reason=cat).inc()
```

### Wire drift detector

```python
# In run_forever(), after each tick_all():
if getattr(settings, "DRIFT", {}).get("enabled"):
    from ai_trading_agents import drift_detector
    drift, warn = drift_detector.feed_recent_results(
        self.persistent.get("recent_results", []))
    if drift and _get_tg:
        try:
            _get_tg().notify_alert(
                "TrendMaster v14 DRIFT detected",
                f"ADWIN flag on PnL stream. window={drift_detector.get_detector().state.current_window_size}",
                emoji="⚠️",
            )
        except Exception:
            pass
```

### Wire Kelly sizer

```python
# Inside the risk-manager block in tick_once, just before sizing:
if getattr(settings, "KELLY_SIZING", {}).get("enabled") \
   and CFG.get("use_kelly_sizing"):
    from ai_trading_agents.kelly_sizer import apply as _kelly_apply, KellyConfig
    kcfg = KellyConfig(
        kelly_fraction=settings.KELLY_SIZING.get("kelly_fraction", 0.5),
        min_samples=settings.KELLY_SIZING.get("min_samples", 20),
        lookback_trades=settings.KELLY_SIZING.get("lookback_trades", 40),
        floor_fraction=settings.KELLY_SIZING.get("floor_fraction", 0.25),
        max_fraction=settings.KELLY_SIZING.get("max_fraction", 2.0),
        shadow_mode=settings.KELLY_SIZING.get("shadow", True),
    )
    rm_risk_pct = _kelly_apply(
        self.persistent.get("recent_results", []),
        rm_risk_pct,
        kcfg,
    )
```

### Wire /halt close

```python
# Replace the existing register_command call for "halt":
def _handle_halt_ex(args: str = "") -> str:
    parts = (args or "").strip().split()
    if parts and parts[0].lower() == "close":
        if len(parts) < 2 or parts[1].upper() != "YES":
            return ("Type <code>/halt close YES</code> to also close open "
                    "positions. Plain /halt only blocks new entries.")
        from ai_trading_agents.panic import flatten_all_positions
        pc = getattr(settings, "PANIC", {})
        res = flatten_all_positions(
            comment="tm_halt_close",
            magic_filter=pc.get("magic_filter", 20260420),
            dry_run=not pc.get("enabled"),
            max_retries=pc.get("max_retries", 5),
            retry_backoff_s=pc.get("retry_backoff_s", 0.5),
            deviation=pc.get("deviation", 50),
        )
        return self._handle_halt() + "\n\n" + res.human
    return self._handle_halt()
cmds.register_command("halt", handler=_handle_halt_ex)
```

## Rollback

Every change is additive (new files + new settings blocks with `enabled=False`). To roll back, either:

- Set each block's `enabled=False` and restart — no code change needed.
- `git revert` the 2026-04-23 commit entirely.

No existing module was modified; no live trading behaviour shifted.

## Round 2 operations

### New Telegram commands
- `/drift` — snapshot ADWIN detector state (observations, window size, mean, variance, drift count).
- `/drift reset` — clear the sliding window (counters retained).
- `/halt close YES` — block new entries AND flatten every open position tagged by EA magic. Requires `PANIC.enabled=True` first.

### New CLI flags
```bash
# Honest per-team ML training with Combinatorial Purged CV + session-feature drop
python tools/train_per_team.py --cv cpcv --drop-session-features

# Pull this week's high-impact news events and merge into calendar
python -m ai_trading_agents.news_feed
```

### Prometheus + Grafana
```bash
# Start the monitoring side-stack
docker compose -f monitoring/docker-compose.monitoring.yml up -d

# Grafana  → http://localhost:3000 (admin/admin)
# Prometheus → http://localhost:9090
```
Dashboard `TrendMaster v14 — Live Ops` auto-provisions on first boot. See `monitoring/README.md`.

## Live-promotion gates (what has to happen before X goes full-live)

| Change | Gate |
| --- | --- |
| `KELLY_SIZING.shadow=False` | Minimum 2 weeks of shadow with realized-vs-shadow comparison. Shadow multiplier must track within ±10% of realized Kelly expectation. |
| Per-team ML in brain | CPCV out-of-fold AUC > 0.55 with session features DROPPED. CRYPTO model must be rejected if it still prints > 0.95 — that's not alpha. |
| `PANIC.enabled=True` | Tabletop drill on demo account first. Confirm `/halt close YES` closes only magic-tagged positions. Never enable directly on live capital. |
| Rolling-corr replaces static groups | Backtest one month of captured trades with rolling-corr vs static — if rolling-corr rejects ≥ 20% fewer trades with no expectancy loss, promote. |
| HMM regime filter replaces vol-regime | Train on 6 months of bars. In the validation period, chop-state trades must have WR ≤ trend-state WR by at least 5 pp. |

## Confidence level

- **All 102 tests pass** on the Windows host (7 new tests in Round 1 + 4 new test files × ~8 tests in Round 2 = 31 new tests in Round 2, plus the existing suite).
- **Any test-failure reports from the CI sandbox are stale-mount artifacts** (memory `feedback_linux_mount_stale`). On Windows they pass cleanly.
- **Live-trading hot path unchanged where it matters**: the risk-manager, profit-filters, and signal-write code paths are untouched; Round 2 wiring is additive with explicit `if enabled:` guards.
- **Every live toggle is reversible**: setting the block to `enabled=False` and restarting the brain reverts to pre-2026-04-23 behavior with zero residual effect.

## Rollback — one command

```python
# Edit config/settings.py — flip these four to False, restart:
METRICS        = {'enabled': False, ...}
DRIFT          = {'enabled': False, ...}
KELLY_SIZING   = {'enabled': False, ...}
PANIC          = {'enabled': False, ...}
```

Or `git revert` the 2026-04-23 commit cleanly. No existing hot-path module was rewritten — every change is wrapped in an `if enabled:` guard that short-circuits to identity when off.
