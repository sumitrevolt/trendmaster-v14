# TrendMaster v14 — Best-in-World Roadmap

**Created**: 2026-04-29  
**Author**: OpenClaw + Claude collaboration session  
**Goal**: Take TrendMaster from "already excellent" to "genuinely best-in-class retail MT5 system"

---

## Honest baseline assessment (what's already best-in-class)

The current system is, frankly, already in the top 5% of retail MT5 setups
worth comparing against. These are the bits that don't need fixing:

- **Two-process fail-independent design** — Python brain ↔ MQL5 EA via atomic
  signal file. Either side crashes, the other keeps doing its job.
- **7-gate filter stack** with audit-fix discipline, cooldown, drawdown lock,
  news blackout, vol-regime, profit-lock, session-window.
- **Per-team risk caps** (METALS / FOREX / CRYPTO / COMMODITIES) with
  correlation grouping.
- **Atomic signal writes** with retry-on-WinError-5 and stale-file age check
  on the EA side.
- **Single-instance lock** with stale-PID cleanup.
- **MT5 reconnect** with exponential backoff.
- **Telegram out-of-band channel** with `/status /pnl /halt /resume /why /symbols /ping /help`.
- **Supervisor** with restart-count alerting.
- **Knowledge graph** (`code-review-graph` MCP) wired into post-tool-use hook
  — Claude/agents can ask "who calls this", "impact radius", "find large
  functions" without re-grepping the repo.
- **Drift detector** running in alerts-only mode.
- **Prometheus-style metrics** exposed on the dashboard.
- **Phase B3 smartmoney features** (COT + EIA) wired and trained.
- **NTFS-junction trick** + canonical source-of-truth at
  `C:\TrendMaster_aita_canonical\` to escape OneDrive/EDR file-deletion bugs.
- **47-day silent-failure incident** properly post-mortemed and fixed.

---

## What was shipped this session (2026-04-29)

### A. OpenClaw — Claude Code-class developer experience

| Change | Why | File |
|---|---|---|
| Multi-model failover chain | github-copilot/claude-3.5-sonnet stale cache was tripping cooldown | `openclaw.json` `agents.defaults.model.failover` |
| Stale session model cache cleared | Old `claude-3.5-sonnet` was stuck in `agent:main:main` | `agents/main/sessions/sessions.json` |
| 5 MCP servers wired | Was just `code-review-graph`. Now also: sequential-thinking, fetch, filesystem, memory | `openclaw.json.mcp.servers` |
| `reviewer` and `researcher` agents added | `main` (opus-4.6) writes, `reviewer` (sonnet-4.6) checks, `researcher` (gemini-2.5-pro) explores | `openclaw.json.agents.list` |
| pre/post-run hooks | Brain liveness check before any `trader`-scope agent run; git-status snapshot post-run | `openclaw.json.hooks.preRun/postRun` |
| Bonjour/mDNS disabled | Was stuck in announce loop on Windows | `openclaw.json.gateway.bonjour.mode = "off"` |
| Restart script | Single-command safe restart with port-kill + config validation | `restart_gateway.cmd` |

**To activate**: run `C:\Users\Ratanshila\.openclaw\restart_gateway.cmd` (or just
`gateway.cmd` if you've already killed the old process).

### B. Trading bot — shared Python ↔ MQL5 config bridge

This was listed as "Planned, not live" in `ARCHITECTURE.md`. Now it ships.

| File | Purpose |
|---|---|
| `config/trading_config.yaml` | Single source of truth (risk %, magic, AI gate, EA indicators, profit-optimizer thresholds) |
| `config/shared_config_loader.py` | Python loader. `env > yaml > hardcoded` precedence. Backward compatible — safe to import even without pyyaml. |
| `tools/sync_config_to_mqh.py` | Generates `MQL5/Include/TrendMasterShared.mqh` from YAML. Run once after each YAML edit, then recompile EA. |

**Migration path** (non-breaking):

```python
# In config/settings.py — replace hard-coded values with shared loader
from config.shared_config_loader import env_or_shared

RISK = {
    "risk_percent": env_or_shared("RISK_PERCENT", "risk.risk_percent", 0.5),
    "max_daily_drawdown_percent": env_or_shared(
        "MAX_DAILY_DRAWDOWN", "risk.max_daily_drawdown_percent", 3.0
    ),
    # ...
}
```

In `AI_SUPERBB_v14_TrendMaster.mq5`, change input defaults:

```mql5
#include <TrendMasterShared.mqh>
input double InpRiskPct = TM_RISK_PERCENT;   // was hard-coded 1.0
input long   InpMagic   = TM_MAGIC;          // was hard-coded 20260420
```

### C. Trading bot — Phase B3 ML safe re-enable

`tools/enable_phase_b3_ml.py` — reversible script that swaps the active
LightGBM model from the weak v1 (107 KB) to the disabled B3 (20 MB).

```bash
python tools/enable_phase_b3_ml.py --verify    # check current state
python tools/enable_phase_b3_ml.py --dry-run   # preview swap
python tools/enable_phase_b3_ml.py             # do the swap (with smoke test)
python tools/enable_phase_b3_ml.py --rollback  # undo
```

After swap, the operator must lower `min_ml_confidence` from 0.70 → 0.62
(in `config/trading_config.yaml` AND `config/settings.py::TRENDMASTER_V14`)
because B3's calibrated max-prob is 0.589.

---

## What's next — prioritised by leverage

### P0 — Run before next live trading day

1. **Restart OpenClaw** (gateway will pick up new config + clear stale cache).
   ```cmd
   C:\Users\Ratanshila\.openclaw\restart_gateway.cmd
   ```

2. **Pip-install pyyaml in the brain venv** (so `shared_config_loader` works):
   ```cmd
   "C:\Users\Ratanshila\Documents\autmated trading\.venv\Scripts\pip.exe" install pyyaml
   ```

3. **Generate the MQH header**:
   ```cmd
   cd /d "C:\Users\Ratanshila\Documents\autmated trading"
   .venv\Scripts\python.exe tools\sync_config_to_mqh.py
   ```

4. **Verify Phase B3 file state** before any swap:
   ```cmd
   .venv\Scripts\python.exe tools\enable_phase_b3_ml.py --verify
   ```

### P1 — High-impact, ≤ 2 hour work each

5. **Lower `min_ml_confidence` 0.70 → 0.62** and run B3 swap. Watch first
   30 minutes of `logs/trend_master_brain.log`. Roll back if /why veto rate
   drops below 30% (means model is too permissive).

6. **Migrate settings.py → shared_config_loader**. One PR per RISK / brain /
   profit_optimizer block. Keep the hard-coded defaults as fallbacks.

7. **Recompile EA with the generated MQH**. Open
   `AI_SUPERBB_v14_TrendMaster.mq5` in MetaEditor, add
   `#include <TrendMasterShared.mqh>`, change input defaults to the
   `TM_*` constants, F7 to compile, redeploy.

8. **Validate metalabel** — currently `metalabel_enabled: false`. Train per
   `tools/train_v14_c1_metalabel.py`, check OOF AUC ≥ 0.55, flip the flag.

### P2 — Real edge gains

9. **Per-team meta-label heads** (Phase C2) — train using
   `tools/train_v14_c2_metalabel_perteam.py` for METALS / FOREX / CRYPTO /
   COMMODITIES. Keep global head as fallback.

10. **EIA API key** — set `EIA_API_KEY` in `config/.env` to unlock the
    `ng_storage_delta_z` smartmoney feature (currently NaN-dropped, only
    32 of 33 features active).

11. **Walk-forward optimizer** — wrap existing `tools/backtest_v15_fast.py`
    in a CPCV harness (the `cpcv.py` module is already there, just not
    plumbed through). Optimize `min_ml_confidence`, `vol_min_quantile`,
    `agent_min_votes` per team.

12. **Re-enable spread_guard with smarter logic** — current default disabled.
    Replace "spread > X*ATR veto" with rolling-percentile guard
    (current spread > 95th-pct of last 1000 ticks) so it only kicks in on
    genuine wide-spread regimes, not normal bursts.

### P3 — Best-in-class differentiators

13. **Live performance dashboard** — `tools/dashboard.py` exists. Extend with
    Sharpe (rolling 50 trades), Sortino, max-DD, Calmar, expected R per
    team. Render on `/metrics` Prometheus endpoint already exposed.

14. **Position-correlation hedge gate** — currently `_CORR_GROUPS` blocks
    same-direction stacking. Add an inverse-correlation HEDGE bonus —
    if you're long XAUUSD and would otherwise short USDJPY, allow the
    USDJPY because the dollar-positive view hedges the metal-positive view.

15. **Online learning** — `online_learner.py` is in the codebase, off by
    default. Wire it in for the meta-label classifier (binary act/skip),
    keeping the LightGBM directional model frozen. River + ADWIN already
    feasible.

16. **A/B harness for parameter changes** — `ab_test.py` exists. Use it to
    A/B `default_sl_atr_multiple = 1.0 vs 1.25`, etc., on parallel demo
    accounts before any live param change.

17. **Regime-aware position sizing** — `regime_hmm.py` is there. Plug into
    Kelly sizer so HIGH_VOL regime drops Kelly fraction to 0.25× and
    LOW_VOL boosts to 1.0× of `kelly_max_fraction`.

---

## Validation gates — never ship blind

Every P1+ change goes through this gate:

1. **Unit / integration tests pass** — `pytest -q tests/`
2. **CPCV walk-forward** — OOF accuracy ≥ baseline, OOF expected-R ≥ baseline
3. **EA parity check** — `tools/ea_parity_nightly.py` shows ≥ 95% match between
   Python and MQL5 sides on the last 7-day bar window
4. **Demo account 24h soak** — copy live config to demo MT5, watch
   `restart_count`, veto rate, daily PnL
5. **Promote** — only after all four green

`tools/config_promotion_gate.py` already exists for step 5. Use it.

---

## What we explicitly did NOT change

- `archive/legacy_python/` — disaster-recovery seed, untouched
- `ai_trading_agents/` junction → `C:\TrendMaster_aita_canonical\` — untouched
- Live brain memory (`brain_memory.json`) — untouched
- Live brain state (`brain_state.json`) — untouched
- The MQ5 EA `.ex5` compiled binary — untouched (recompile only after MQH change)
- Telegram bot tokens — untouched (Jarvis bot reservation respected)
- Any commit history

---

## Files added this session

```
config/trading_config.yaml                         # NEW canonical config
config/shared_config_loader.py                     # NEW Python loader
tools/sync_config_to_mqh.py                        # NEW MQH generator
tools/enable_phase_b3_ml.py                        # NEW safe model swap
docs/BEST_IN_WORLD_ROADMAP.md                      # NEW (this file)
```

```
C:\Users\Ratanshila\.openclaw\openclaw.json        # REWRITTEN with multi-failover
C:\Users\Ratanshila\.openclaw\restart_gateway.cmd  # NEW restart script
C:\Users\Ratanshila\.openclaw\agents\main\sessions\sessions.json  # PATCHED stale model
```

All previous versions are timestamped backups in the same folders.
