# Postmortem - pre-commit/junction conflict breaks ai_trading_agents twice during Phase B1 commit

**Date**: 2026-04-26
**Severity**: SEV-3 (no live $ loss; full self-recovery; final state healthy)
**Authors**: Sumit (with Claude assistance)
**Status**: Resolved

## Summary

Pre-commit's `git stash`/restore cycle replaced (then later removed) the
`ai_trading_agents/` NTFS junction during the Phase B1 commit, twice in
a row; the implementing agent detected each break and rebuilt the
junction by hand, the final commit `862077b` landed clean.

## Impact

- **What broke**: The NTFS junction at
  `C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents`
  (target `C:\TrendMaster_aita_canonical\`) was replaced with a real
  empty directory on the first commit attempt and then removed entirely
  on the second.
- **What did NOT break**: No `*.py` brain modules were lost — the
  canonical source at `C:\TrendMaster_aita_canonical\` was untouched
  the whole time. The brain was running on cached imports and never
  crashed. Final commit `862077b` is clean, `pytest` is green, and the
  junction was re-pointed at the canonical folder before session end.
  No live trades were affected (markets closed, Sunday IST).
- **Final state at session close**: `ai_trading_agents/` is a healthy
  junction → `C:\TrendMaster_aita_canonical\`, brain modules importable,
  `pytest` 411 passed.

## Timeline (IST, approximate)

| Time | Event |
|---|---|
| 16:30 | Phase B1 implementation finishes; `cross_asset_join.py` + 220-line test file ready in working tree |
| 16:35 | First `git commit` attempt → pre-commit triggers ruff + ruff-format hooks |
| 16:36 | ruff-format reformats `cross_asset_join.py` (the file lives inside `ai_trading_agents/`, i.e. on the junction target). pre-commit's pre-stage `git stash --keep-index` snapshots the worktree |
| 16:37 | Hooks finish; pre-commit attempts `git stash pop` to restore the worktree. Stash restore **replaces the junction with a real directory** (Windows NTFS + Git on Windows interaction). Agent observes "ai_trading_agents/ now contains 1 file" instead of the full canonical set |
| 16:38 | First recovery: `rd /s /q ai_trading_agents` + `mklink /J ai_trading_agents C:\TrendMaster_aita_canonical`. Junction back, brain importable. |
| 16:42 | Second `git commit` attempt to land the now-formatted files |
| 16:43 | Same pattern: pre-commit's stash/restore cycle, this time the junction is **removed entirely** (no replacement directory created) |
| 16:44 | Second recovery: same `rd /s /q` + `mklink /J` sequence. Junction restored. |
| 16:44 | Third commit attempt succeeds — commit `862077b` lands. Smoke import passes. |

## Root cause

Pre-commit on Windows uses `git stash --keep-index` before running
auto-fix hooks (`ruff --fix`, `ruff-format`, `end-of-file-fixer`,
`trailing-whitespace`) and then `git stash pop` afterwards to restore
any unstaged worktree state. The interaction is:

1. `ruff-format` rewrites a file *inside* `ai_trading_agents/` (the
   junction). The write goes through to `C:\TrendMaster_aita_canonical\`
   transparently — that part is fine.
2. Git stash/unstash on Windows is implemented by Git's own filesystem
   layer, not by NTFS junction-aware code. When `git stash pop` runs
   against a worktree path that is itself a junction, Git's default
   behavior is to materialize the directory at the worktree path —
   which in NTFS terms means **delete the reparse point and recreate
   it as a real directory** (or just delete it). The canonical target
   under `C:\` is untouched, but the junction at the project root is
   destroyed.
3. The next Python import sees an empty `ai_trading_agents/` (or
   nothing at all) and the brain is one restart away from death.

This is the same class of bug as the OneDrive/EDR phantom-deletion
incident from 2026-04-25 — anything other than NTFS-aware code that
walks the worktree can mistake the junction for a directory and
"fix" it.

## Why it didn't catch worse

- The implementing agent had read `CLAUDE.md`'s "Brain package
  maintenance (junction architecture)" section earlier in the session,
  so when `ai_trading_agents/` looked wrong post-commit, the recovery
  command was already in working memory.
- The brain process was holding modules in Python's import cache, so
  no live decision path crashed during the gap.
- Markets were closed (Sunday).
- Future agents may not have all three of those factors aligned.
  Specifically: a fresh-session agent that doesn't read CLAUDE.md
  fully before running `git commit` will not know to look. A weekday
  incident during market hours would have a 5-minute window where the
  brain restart script (post-pre-flight upgrade in
  `2026-04-25_godmode_round2_consolidation.md`) would refuse to start
  but no automatic recovery would run.

## Prevention

Three guard mechanisms shipped in this session's commit:

1. **`tools/restore_junction.cmd`** — single-purpose recovery script.
   Detects whether `ai_trading_agents/` is a healthy junction; if not,
   removes whatever's there and re-creates the junction. Refuses to
   run if `C:\TrendMaster_aita_canonical\` is missing (would otherwise
   create an empty junction and the brain would die on the next import).

2. **`tools/check_junction.py`** + a pre-commit local hook
   (`always_run: true`) — verifies on every commit that the junction
   is intact via `os.path.realpath`. If broken, prints the recovery
   command and exits non-zero. Note: this hook runs *before* pre-commit
   pops its stash to restore unstaged changes, so it cannot prevent
   the current commit's stash/pop from breaking the junction; what it
   *does* prevent is the **next** commit landing on top of an already
   broken worktree (which would compound the damage). Skips silently
   on non-Windows so CI on Linux stays green. This guard fired and
   passed cleanly when the postmortem commit (`81cdbed`) itself was
   created. Verified empirically: pre-commit's post-stash restore on
   that commit *did* remove the junction again, and `restore_junction.cmd`
   self-healed it in one shot.

3. **`start_brain_clean.cmd` upgrade** — pre-flight now calls
   `tools\restore_junction.cmd` before the existing canonical-folder
   import smoke test, so a brain restart after a botched commit
   self-heals instead of failing closed.

## Action items

| # | Action | Owner | Status |
|---|---|---|---|
| 1 | Ship `tools/restore_junction.cmd` | Claude / next session | Done in commit landing this postmortem |
| 2 | Ship `tools/check_junction.py` + pre-commit local hook entry | Claude / next session | Done in commit landing this postmortem |
| 3 | Wire `tools/restore_junction.cmd` into `start_brain_clean.cmd` pre-flight | Claude / next session | Done in commit landing this postmortem |
| 4 | Add "Don't run pre-commit without a junction guard" entry to CLAUDE.md "Don'ts" | Claude / next session | Done in commit landing this postmortem |
| 5 | Investigate whether pre-commit can be configured to skip stash/restore on Windows junction worktrees (`fail_fast` with the new check is a workable stopgap but not a real fix) | Sumit | Open |
| 6 | Watch for repeat occurrence on next 5 commits; if the new check ever fires, file a follow-up postmortem | Sumit | Open |

## Lessons

- **Junction-aware tooling is not a Windows default.** Anything that
  walks the worktree (Git, ruff, OneDrive, antivirus) can stumble on
  a junction unless explicitly junction-aware. The fix is always the
  same shape: a small script that detects breakage and re-creates the
  junction from the canonical target.
- **Self-healing > diagnostic-only checks.** The pre-commit check
  that fires *after* breakage protects future agents from committing
  garbage; the start_brain_clean.cmd pre-flight that *re-creates* the
  junction protects the live trading path. Both layers are cheap.
- **Pre-commit auto-fix hooks are non-trivial on Windows.**
  `ruff-format` doing its job correctly is what triggered the
  stash cycle that broke the junction. Disabling formatting is not
  the answer; guarding the artifact is.

## Related postmortems

- `2026-04-25_phantom_deletion_incident.md` — original junction
  architecture decision; same root issue (non-junction-aware tools
  stomping on the worktree).
- `2026-04-25_godmode_round2_consolidation.md` — added the original
  pre-flight check to `start_brain_clean.cmd`; this session extends
  that pre-flight to also call the new restore script.
- `2026-04-24_zero_trades.md` — the silent-failure shape this
  prevention work helps avoid (broken brain + no loud signal).
