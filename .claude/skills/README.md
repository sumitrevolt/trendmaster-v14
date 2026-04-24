# AMD Smart Money Forex Bot — Claude Skills

This directory contains 8 skills that Claude Code auto-discovers when
working in this project. Each is a `SKILL.md` (plus optional reference
files) describing a specific area of expertise.

## Inventory

| Skill | Origin | Lines | What it owns |
|---|---|---|---|
| [amd-trading-bot-ops](./amd-trading-bot-ops/SKILL.md) | Custom | 167 | Brain↔EA glue, common workflows, tuning, do-not-do list |
| [mql-developer](./mql-developer/SKILL.md) | [ThomasPraun](https://github.com/ThomasPraun/mql-developer) | 140 + 8 refs | Complete MQL4/MQL5 language reference |
| [backtesting-frameworks](./backtesting-frameworks/SKILL.md) | [wshobson/agents](https://github.com/wshobson/agents) | 657 | Bias avoidance, train/val/test design |
| [risk-metrics-calculation](./risk-metrics-calculation/SKILL.md) | [wshobson/agents](https://github.com/wshobson/agents) | 551 | VaR, CVaR, Sharpe, Sortino, drawdown |
| [walk-forward-optimization](./walk-forward-optimization/SKILL.md) | Custom | 113 | Overfitting defense for brain retrains |
| [regime-detection](./regime-detection/SKILL.md) | Custom | 119 | Trending/ranging/high-vol classification |
| [news-calendar-filter](./news-calendar-filter/SKILL.md) | Custom | 154 | NFP/FOMC/CPI blackout windows |
| [correlation-risk-controls](./correlation-risk-controls/SKILL.md) | Custom | 198 | Currency-bucket exposure caps |

## How they fit together

```
                     amd-trading-bot-ops  ← starts here for any task
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       mql-developer   backtesting   risk-metrics
       (EA changes)    -frameworks   -calculation
                           │
                           ▼
                walk-forward-optimization
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        regime-      news-calendar-  correlation-
        detection      filter        risk-controls
       (when to       (don't trade   (how much in
        trade)         here)         total)
```

## Suggested rollout order

The skills are documentation only — they don't change the bot until you
implement what they describe. Recommended priority:

1. **news-calendar-filter** — biggest tail-risk reduction; ~1hr to ship
2. **walk-forward-optimization** — validates current params before any other change
3. **regime-detection** — biggest live-PnL lever once WFO confirms a stable base
4. **correlation-risk-controls** — only if/when you go multi-symbol

## Adding new skills

Drop a new directory with a `SKILL.md` containing this frontmatter:

```yaml
---
name: skill-name
description: One sentence that helps Claude decide when to use it. Be specific about triggers.
---
```

Claude Code reads the description to route requests. Make it concrete
("use when retraining the brain") not vague ("use for ML stuff").

For richer skills, add reference files in a subdirectory and link to
them from `SKILL.md` — Claude loads the references on demand.
