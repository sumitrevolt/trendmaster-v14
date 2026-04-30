# Postmortem index

Reverse-chronological list of incident postmortems. New postmortems should be
appended via the trading-postmortem-new skill, which writes one line here per
incident.

## 2026

- [2026-04-30 - Junction trap silent state drift to C:\logs\ (RESOLVED via `_ROOT` validation fallback in state_store/event_log/process_lock)](2026-04-30_junction_trap_silent_state_drift.md)
- [2026-04-29 - Recurring 109 KB uniform-output model overwriting live (RESOLVED via candidate-path hardening of `train_v14_better.py`)](2026-04-29_uniform_model_recurrence.md)
- [2026-04-29 - 16-hour brain silent termination (RESOLVED; first incident detected end-to-end by watch_pets.py)](2026-04-29_brain_silent_termination.md)
- [2026-04-28 - Orphaned D2 model + dead-market lockout (RESOLVED via `.lgb` file rename + vol_min_quantile loosen)](2026-04-28_orphaned_d2_model_and_dead_market_lockout.md)
- [2026-04-26 - Pre-commit/junction breakage during Phase B1 commit (RESOLVED via restore_junction.cmd + check_junction.py guard)](2026-04-26_pre_commit_junction_breakage.md)
- [2026-04-25 - God-mode round 2 consolidation (latent bug fixes, CI sentinel, archive cleanup)](2026-04-25_godmode_round2_consolidation.md)
- [2026-04-25 - Phantom file-deletion incident (RESOLVED via NTFS junction)](2026-04-25_phantom_deletion_incident.md)
- [2026-04-25 - ai_trading_agents restoration + 13-skill install](2026-04-25_aita_restore_and_skill_install.md)
- [2026-04-24 - Zero trades silent failure](2026-04-24_zero_trades.md)
