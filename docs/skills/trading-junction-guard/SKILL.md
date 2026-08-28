---
name: trading-junction-guard
description: Verify that ai_trading_agents/ is still a valid NTFS junction → C:\TrendMaster_aita_canonical\ AND that the canonical folder has all 39 expected brain modules. Defends against the 2026-04-25 phantom-deletion class of incidents recurring. Use when the user asks "junction healthy", "junction guard", "is the package intact", "verify brain modules", or as a 15-minute scheduled task.
---

# Trading Junction Guard

The 2026-04-25 phantom-deletion incident wiped `ai_trading_agents/*.py` and was only fully resolved by switching to a junction architecture. If the junction itself is ever removed, recreated incorrectly, or if files vanish from the canonical folder, this skill catches it within 15 minutes.

## When to invoke

- Scheduled task: every 15 minutes (`schtasks /sc MINUTE /mo 15`).
- After any restart of the brain.
- After any operating-system update (Windows updates have wiped junctions in the past).
- Operator manual: "verify junction integrity".

## What it checks

| Check | Detail |
|---|---|
| 1. `ai_trading_agents/` exists | Directory present at expected path |
| 2. It IS a junction | `fsutil reparsepoint query` returns Mount Point reparse type |
| 3. Junction target is correct | Resolves to `C:\TrendMaster_aita_canonical\` |
| 4. Canonical folder exists | `C:\TrendMaster_aita_canonical\` is a real directory |
| 5. Canonical folder has expected files | Cross-check against `references/expected_modules.txt` (37 canonical modules + brain + __init__) |
| 6. No NUL-byte corruption | Sample 5 random modules; reject if any contains `\x00` |
| 7. Brain top-level imports | `python -c "import ai_trading_agents.trend_master_brain"` succeeds |

If ALL 7 pass, junction is HEALTHY. Any failure → page Telegram with the specific check that failed.

## Output

```
Junction Guard — 2026-04-25 16:50 UTC
======================================
Check 1 — ai_trading_agents/ exists:           OK
Check 2 — Is junction (reparse point):         OK (Mount Point)
Check 3 — Junction target correct:             OK (C:\TrendMaster_aita_canonical)
Check 4 — Canonical folder exists:             OK
Check 5 — Module count vs expected:            OK (39/39)
Check 6 — Random NUL-byte sample (5 modules):  OK
Check 7 — Brain top-level import:              OK

VERDICT: HEALTHY

(no Telegram alert sent)
```

For a regression:

```
Junction Guard — 2026-04-25 16:50 UTC
======================================
Check 1 — ai_trading_agents/ exists:           OK
Check 2 — Is junction (reparse point):         FAIL — directory is no longer a junction
                                               (regular directory created by something)
Check 3 — Junction target correct:             SKIP (not a junction)
...

VERDICT: REGRESSED

Telegram alert sent:
"[TrendMaster ALERT] Junction guard failed at 16:50 UTC.
 ai_trading_agents/ is no longer a junction (regular dir).
 Brain restart will likely fail. Restore via:
   rd /s /q ai_trading_agents
   mklink /J ai_trading_agents C:\TrendMaster_aita_canonical
 See CLAUDE.md 'Brain package maintenance' section."
```

## How to call

```cmd
cd C:\Users\Ratanshila\Documents\autmated trading
.venv\Scripts\python.exe ${CLAUDE_PLUGIN_ROOT}\skills\trading-junction-guard\guard.py
```

Pass `--quiet-on-healthy` to suppress output if all checks pass (good for schtask). Pass `--no-telegram` to disable paging (test mode).

## Schtask installation

```cmd
schtasks /create /sc MINUTE /mo 15 /rl LIMITED /f /tn "TrendMaster Junction Guard" ^
    /tr "cmd /c cd /d \"C:\Users\Ratanshila\Documents\autmated trading\" && .venv\Scripts\python.exe docs\skills\trading-junction-guard\guard.py --quiet-on-healthy >> logs\junction_guard.log 2>&1"
```

## Critical guardrails

- **Read-only.** The skill verifies; it never auto-rebuilds the junction. CLAUDE.md has the rebuild commands; operator runs them.
- **De-dupe Telegram pages.** Don't re-page within 60 minutes of last page.
- **Don't fail on transient I/O errors.** If a module can't be opened (Python had it locked for compile), retry once before flagging.
- **Skip check 7 if a brain is currently in startup window** (the import itself can fail mid-startup harmlessly). Track `logs/brain.pid` mtime; if < 60s old, skip.

## Helper script

`guard.py` next to this SKILL.md. Expected modules list in `references/expected_modules.txt`.
