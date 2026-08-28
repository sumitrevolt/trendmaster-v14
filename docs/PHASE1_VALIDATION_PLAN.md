# Phase 1 Validation — 30-day disciplined checkpoint

**Account:** $1,000 OctaFX (200x leverage available, NOT utilized at 0.5% risk)
**Config:** Concentrated (top-8, 2 per team) — applied 2026-05-01
**Risk per trade:** 0.5% = $5
**Window:** Day 1 starts on first restart after 2026-05-01.

The single goal of this phase: **prove the live edge matches the backtest
within tolerance.** Not "make money fast." Money will compound on its own
once edge is validated. This phase de-risks Phase 2.

---

## Backtest expectation (what to measure live against)

From walkforward 2026-05-01_0230 on the 8 active symbols (rule-based,
EA-parity, gross — before realistic 50-70% cost haircut):

| Metric | Backtest gross | Net expectation (live) |
|---|---:|---:|
| Avg expR per trade | +0.358R | +0.10 to +0.18R |
| Win rate | 34.7% | 30-40% (wide band, regime-dependent) |
| Trades per day | ~50 (theoretical) | 8-15 (live, gates enforce) |
| Daily P&L expected | — | **$6 - $11** (P50: ~$8) |
| Monthly P&L expected (22 trading days) | — | **$120 - $250** (P50: ~$180) |
| Max drawdown expected | — | **6.5%** ($65) |

These are **expected** numbers. Live can run high or low for weeks; what
matters is the 30-day aggregate vs the band.

---

## Daily monitoring (5 min/day, max)

Run every morning at IST 12:00 (after London open):

```cmd
.venv\Scripts\python.exe tools\phase1_progress.py
```

Outputs:
- Days into Phase 1
- Net P&L vs expected band
- Win rate vs expected band
- Max drawdown observed
- Any RED flags (DD breach, telegram silent, brain restarts)

**Do NOT** open MT5 every hour. The bot's edge is statistical — looking at
intraday P&L is noise. Daily snapshot is enough.

---

## Weekly checkpoints

Each Sunday evening, run:

```cmd
.venv\Scripts\python.exe tools\phase1_progress.py --weekly
```

Verify:
- Week's net P&L is within ±50% of expected ($30-$80 net per week)
- WR is within 25%-45% (wide tolerance for variance)
- Max drawdown stayed under 5%
- All gate vetoes look reasonable (sample 5 from `events.jsonl`)

If any week is outside band but the trend is healthy, do nothing. Variance is
expected. **Three consecutive weeks outside band = investigate before day 30.**

---

## Day-30 unlock decision (PROMOTE / ABORT / EXTEND)

This is where most retail traders fail — they look at one bad week and panic,
or one good week and over-extend. **Pre-commit to the decision tree NOW:**

### PROMOTE to Phase 2 (1% risk) if ALL of:

- [x] 30-day net P&L ≥ **+$80** (low end of expected $120-$250 minus 33% reality buffer)
- [x] Max drawdown observed ≤ **5%** ($50)
- [x] Win rate in **30%-40%** band
- [x] No single-day loss > **3%** (DD breaker should have triggered ≤2 times)
- [x] Telegram alerts arriving consistently (no silent 404 streaks)
- [x] No critical incidents (.resolve() regressions, junction breaks, brain dead > 4 hours)
- [x] Number of trades ≥ **150** (gives statistical significance; ~5/day × 30 days)

### ABORT (revert to rule-only diagnostics, debug edge) if ANY of:

- [ ] 30-day net P&L < **-$50** (worse than expected DD = strategy not working live)
- [ ] Max drawdown > **8%** (well over expected 6.5% = risk model wrong)
- [ ] Win rate < **25%** for full 30 days (way below band = something broken)
- [ ] More than 3 critical incidents (operational instability)

### EXTEND Phase 1 by 30 days if:

- Net P&L between -$50 and +$80 (drifting, not failing)
- Or fewer than 150 trades (need more samples)
- Or 1-2 critical incidents got resolved (one-off, not pattern)

**No "I think it'll work next month" extensions.** Either data passes or
it doesn't. If it doesn't pass on day 60, it's not the strategy that's wrong
— it's the assumption that walkforward translates to live (slippage, regime
change, broker fills). Investigate.

---

## What CANNOT trigger config change during Phase 1

These are temptations to resist:

| Temptation | Why no |
|---|---|
| Bump risk_pct to 1% mid-phase | Resets the validation clock; you're trading with no proven edge |
| Re-add a "good week" symbol back | Sample-size gaming. Whole point of Phase 1 is the SET we agreed to. |
| Disable session_window gate "to catch more trades" | Asian-session trades are EV-negative. Will tank the 30-day edge. |
| Lower MIN_CONF below 0.50 | Trades on noise. Memory invariant: don't lower below 0.50. |
| "Just one manual override" trade | Once you start, you'll do it again. Bot's discipline only works if you preserve it. |

If any of these feel necessary mid-phase, that's a signal to **investigate**,
not to change config. Open a postmortem first, decide later.

---

## Day-0 baseline (capture once before restart)

Before you run `start_brain_clean.cmd` to activate the Concentrated config,
record:

```
date_utc:           2026-05-01T??:??:??Z
account_balance_usd: $1000  (or current)
account_equity_usd:  $???   (current MT5 equity if different)
open_positions:      ??     (close any orphans before phase starts)
config_version:      Concentrated v1 (top-8, 0.5% risk, EU Labour Day blackout)
walkforward_ref:     reports/walkforward/2026-05-01_0230.json
expected_p50_30d:    +$180
```

`tools/phase1_progress.py` writes this baseline on first run and never
overwrites — it's the immutable Day-0 anchor for all later comparisons.

---

## What happens at Day 30

If PROMOTE: edit `RISK_PERCENT=0.5` to `RISK_PERCENT=1.0` in `config/.env`,
restart brain, start Phase 2 with the same 8 symbols. Phase 2 doc will be
written then.

If ABORT: open `docs/POSTMORTEMS/2026-XX-XX_phase1_abort.md`, investigate
the 3 most likely failure modes (cost haircut wrong, regime change, broker
fills bad), then iterate. Possibly add capital and re-run Phase 1 instead
of escalating risk.

If EXTEND: continue Phase 1, write a brief "extension note" in
`docs/team/trader/extension_note_<date>.md` saying why and what's the
specific signal that would resolve.

---

## Compounding math (motivation)

If Phase 1 hits P50 ($180/mo), Phase 2 hits P50 ($350/mo with compounding),
Phase 3 hits P50 ($600/mo)... here's the realistic glide path:

| Month | Phase | Account starting | Realistic P&L | Account ending |
|---:|---|---:|---:|---:|
| 1-3 | Phase 1 (0.5%, top-8) | $1,000 | ~$540 | $1,540 |
| 4-6 | Phase 2 (1%, top-8) | $1,540 | ~$1,000 | $2,540 |
| 7-9 | Phase 3 (Aggressive 1%) + add $3K capital | $5,540 | ~$2,500 | $8,040 |
| 10-12 | Phase 3 continued | $8,040 | ~$3,500 | $11,540 |
| 13-18 | Phase 3 + add $10K capital | $21,540 | ~$10,000 | $31,540 |
| 19-24 | Ultra (1.5%) + add $20K capital | $51,540 | ~$25,000 | **$76,540** |

**By month 24, daily P&L target $300/day is hit on $76,000 capital.**

This requires: (a) live edge matches backtest, (b) you actually add capital
when checkpoints pass, (c) no over-leverage during winning streaks. Each is
a discipline test, not a math problem.

This is the **compounding billionaire path.** Slow first 6 months. Real
acceleration starts month 9. Year 2 is where capital growth + edge growth
+ compounding all click together.
