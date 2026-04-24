# Project-local Claude Code subagents

Subagents Claude Code can delegate to. Activated automatically when
their `description` field matches the task, or explicitly via
`> Use the <name> subagent to …` in Claude Code.

## Installed subagents

All three are `model: opus` (deep reasoning) — picked because
high-stakes trading-logic decisions merit the extra cost.

| Subagent | When to invoke | Source |
|----------|----------------|--------|
| `quant-analyst` | New trading strategies, statistical arbitrage, derivatives pricing, backtesting with historical validation, alpha attribution | VoltAgent awesome-claude-code-subagents |
| `risk-manager` | VaR/CVaR work, stress testing, control-framework design, regulatory-compliance checks, exposure calculation. Maps to `ai_trading_agents/risk_manager.py` | VoltAgent awesome-claude-code-subagents |
| `fintech-engineer` | Payment/broker integration, financial-logic correctness, transaction auditing, anti-fraud | VoltAgent awesome-claude-code-subagents |



## Why these three specifically

Cherry-picked from a 131-subagent collection. Most of that repo is
web/mobile/DevOps-focused — irrelevant here. These three fill real
gaps in the already-installed `claude-trading-skills` marketplace
(which focuses more on MQL5/chart/indicator craft than quantitative
theory and risk frameworks).

## Not installed (on purpose)

- `reinforcement-learning-engineer` — memory flags RL as "deliberate
  gap / future R&D"; no active work, subagent would rot.
- Generic `code-reviewer`, `debugger`, `python-pro` — already covered
  by the installed `engineering:*` plugin skills.
- Everything in categories 01 (core dev), 02 (language specialists),
  03 (infra), 06 (DX), 08 (business), 09 (meta) — no TrendMaster-fit.

## Adding more later

```powershell
$base = "https://raw.githubusercontent.com/VoltAgent/awesome-claude-code-subagents/main/categories"
Invoke-WebRequest "$base/<category>/<name>.md" -OutFile .claude\agents\<name>.md
```

Catalog: https://github.com/VoltAgent/awesome-claude-code-subagents

## Companion Python libs

Installed on the host alongside these subagents, ready for any
backtest/metrics code that wants them. Not yet imported anywhere —
when code starts using them, add to `requirements.txt` and to
`.github/workflows/ci.yml`'s install step:

- `empyrical` 0.5.5 — Sharpe/Sortino/MaxDD/alpha/beta metrics (Zipline's lib)
- `quantstats` 0.0.81 — full performance reports with HTML output
