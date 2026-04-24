---
name: trading-why-inspector
description: "Inspect why the TrendMaster brain accepted or vetoed a symbol's signal, across symbols and over recent history. Shows agent votes, confidence, regime, spread, and the last veto reason per symbol. Use when Telegram /why isn't detailed enough, when debugging gate behavior across many symbols at once, or diagnosing why the book is quiet."
---

# trading-why-inspector

The Telegram `/why SYMBOL` command shows the current signal for one symbol. This skill extends that for deeper debugging: across symbols, across recent history, and aggregated by gate name. If `/why` tells you what; this skill tells you *why so many why's look the same*.

## When to use

- Signals firing less than expected — diagnose which gate is dominating vetoes
- One symbol is silent while others trade — find out what's specific to it
- After tuning a gate threshold, confirm the intended effect before leaving it overnight
- Before asking "why is nothing trading?" in Telegram — answer it yourself first

## Single symbol (replicates `/why`)

```python
import json
from pathlib import Path

sig_path = Path("signals") / "XAUUSD.json"
sig = json.loads(sig_path.read_text())
print({
    "direction":    sig.get("direction"),
    "confidence":   sig.get("conf"),
    "agent_votes":  sig.get("agent_votes"),
    "regime":       sig.get("regime"),
    "written_at":   sig.get("ts"),
})
```

## Veto log (all symbols)

Last veto per symbol is stored in `state["last_veto_per_symbol"]`:

```python
from pathlib import Path
from ai_trading_agents.state_store import StateStore

state = StateStore(Path("logs/brain_state.json")).load()
for sym, veto in (state.get("last_veto_per_symbol") or {}).items():
    gate   = veto.get("gate", "unknown")
    reason = veto.get("reason", "")
    ts     = veto.get("ts", "")
    print(f"{sym:10}  [{gate:<20}]  {reason}  ({ts})")
```

## Aggregate: which gate is vetoing most?

```python
from collections import Counter
from pathlib import Path
from ai_trading_agents.state_store import StateStore

state = StateStore(Path("logs/brain_state.json")).load()
counter = Counter()
for v in (state.get("last_veto_per_symbol") or {}).values():
    counter[v.get("gate", "unknown")] += 1
for gate, n in counter.most_common(10):
    print(f"{n:3}  {gate}")
```

If one gate is > 70% of vetoes, that gate is doing almost all the filtering work — likely miscalibrated.

## Common gate names (reference)

- `profit_optimizer` — vol regime, confidence floor (spread guard is **disabled** by project policy)
- `risk_manager` — `max_open`, `max_open_per_team`, daily drawdown breaker
- `news_filter` — high-impact event window from `data/news_calendar.json`
- `meta_labeler` — secondary filter on HMM regime agreement
- `ea_quorum` — fewer than `require_all_3` EA confirmations
- `max_dd_breaker` — panic halt if rolling drawdown exceeds cap
- `reentry_tracker` — reentry permit not available / cooldown active

## Runtime overrides (from memory)

Gates `require_all_3` and `max_spread_atr_pct` can be live-overridden via the EA signal JSON — no chart re-attach required. Handy for testing a looser gate for an hour without a restart.

## Reminders

- **Spread guard is disabled** by operator policy. Do not re-enable without asking — `PROFIT_OPTIMIZER.spread_guard=False`, `vol_regime=True` is the correct state.
- Vetoes are last-writer-wins per symbol; a symbol that just traded will have its last successful signal, not a veto. Filter for vetos with `veto.get("status") == "veto"` if the signal JSON exposes that.

## Pairs well with

- `trading-daily-pnl` — see if vetoes correlate with a drawdown day
- `trading-ea-parity` — if the brain says "accept" and the EA still rejected, parity will surface it
