## Summary

<!-- One-paragraph description of what this PR changes and why. Link
     any relevant memory entry, issue, or incident. -->

## Risk tier

- [ ] **Low** — docs, tests, tooling, CI. No runtime impact.
- [ ] **Medium** — isolated module change, covered by tests.
- [ ] **High** — touches `trend_master_brain`, `risk_manager`,
      `panic`, `ea_confirmations`, `check_risk`, or any money-path logic.

## Pre-merge checklist

- [ ] `pre-commit run --all-files` clean locally.
- [ ] `pytest -q tests/` passes (or, if skipped, explained why).
- [ ] If this touches trading logic: ran
      `python tools/code_health_audit.py` and checked the affected
      functions haven't regressed in coverage/complexity.
- [ ] If this touches flow-relevant code (orders/fills/state):
      ran `rebuild_graph.cmd` and inspected `get_affected_flows`
      in the DB.
- [ ] No new top-level `import MetaTrader5` — must stay late-bound
      (`tests/test_imports.py` enforces this).
- [ ] No secrets in diff (`detect-private-key` hook runs on commit;
      spot-check anyway).
- [ ] CI on this branch is green.

## Rollback plan

<!-- How do we revert this safely if it misbehaves in production?
     E.g. "revert commit, EA continues trading on last config",
     or "run rebuild_graph.cmd to reset graph state". -->

## Operator notes

<!-- Anything the on-call operator needs to know — new Telegram
     command, new env var, new scheduled task, changed behaviour on
     broker disconnect, etc. -->
