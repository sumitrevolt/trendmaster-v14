---
name: trading-portfolio
description: Portfolio-level risk controls for multi-symbol trading — correlation caps, hedging pairs, concurrent-trade limits, margin utilization budgets, and aggregate risk sizing so individual-trade rules do not blow up at the portfolio level.
---

# Portfolio & Correlation Management

A single-symbol EA is a lone trade. A portfolio is a fleet. Per-trade risk controls (1% risk, stop-loss, ATR sizing) are necessary but **not sufficient** once you run multiple instances. Three correlated longs = one 3x-sized long. Margin used per symbol adds up. Max-daily-loss at the account level is the only backstop that actually matters.

This skill covers the glue that turns N single-symbol EAs into a coherent portfolio.

---

## When to use this skill

- Running the EA on more than one symbol (XAUUSD + EURUSD + NAS100, etc.)
- Running multiple strategies on the same symbol (trend + mean-reversion magics)
- Adding a new symbol and you need to know the correlation impact
- Seeing "not enough money" / retcode 10019 during news events
- Equity curve is spikier than the single-symbol backtests predict

---

## Core principle: risk aggregates, not diversifies (unless you prove it)

Two assumptions that kill accounts:

1. **"Different symbols = independent risk."** Wrong during risk-off events — XAUUSD, USDJPY, EURUSD, SPX500 all move together on FOMC days.
2. **"1% per trade means 1% portfolio risk."** Wrong. Five open 1%-risk trades in the same cluster = 5% risk if they all stop out simultaneously (and they will).

Solution: treat the **cluster** as the unit of risk, not the symbol.

---

## Correlation matrix: compute it, don't guess

```python
# analytics/correlation.py
import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
           "NAS100", "SPX500", "UKOIL", "BTCUSD"]

def fetch_returns(symbol: str, timeframe=mt5.TIMEFRAME_H1, bars=1000) -> pd.Series:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        return pd.Series(dtype=float, name=symbol)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")
    return np.log(df["close"] / df["close"].shift(1)).rename(symbol)

def correlation_matrix(symbols=SYMBOLS, timeframe=mt5.TIMEFRAME_H1, bars=1000) -> pd.DataFrame:
    rets = pd.concat([fetch_returns(s, timeframe, bars) for s in symbols], axis=1).dropna()
    return rets.corr()

def cluster(corr: pd.DataFrame, threshold: float = 0.6) -> dict[str, int]:
    """Greedy clustering: two symbols share a cluster if |rho| >= threshold."""
    groups: dict[str, int] = {}
    next_id = 0
    for sym in corr.columns:
        if sym in groups:
            continue
        groups[sym] = next_id
        for other in corr.columns:
            if other in groups:
                continue
            if abs(corr.loc[sym, other]) >= threshold:
                groups[other] = next_id
        next_id += 1
    return groups
```

**Refresh cadence**: recompute weekly, or after any regime break (e.g., central bank pivot). Correlations are not stationary.

**Rule of thumb for XAUUSD clusters (H1, rolling 1000 bars)** — roughly:

- Cluster A (risk-off / USD-weak): XAUUSD, EURUSD (negatively), DXY (inverse)
- Cluster B (risk-on): SPX500, NAS100, BTCUSD (loose)
- Cluster C (oil/commodities): UKOIL, USDCAD (inverse)

Your live numbers will differ — **use the code, not the rule of thumb**.

---

## Position caps: per-cluster, not per-symbol

```python
# risk/portfolio_caps.py
from dataclasses import dataclass

@dataclass
class PortfolioLimits:
    max_open_trades: int = 6
    max_trades_per_symbol: int = 2
    max_trades_per_cluster: int = 2
    max_trades_per_direction_per_cluster: int = 2  # block "3 longs in risk-off cluster"
    max_portfolio_risk_pct: float = 3.0            # sum of open-trade risk ≤ 3% equity
    max_margin_util_pct: float = 30.0              # margin used / equity

def can_open_new(desired: dict, open_positions: list, clusters: dict,
                 equity: float, margin_used: float, limits: PortfolioLimits) -> tuple[bool, str]:
    """desired = {'symbol': 'XAUUSD', 'dir': +1, 'risk_pct': 1.0, 'margin_est': 50.0}"""
    if len(open_positions) >= limits.max_open_trades:
        return False, "max_open_trades"

    sym_count = sum(1 for p in open_positions if p["symbol"] == desired["symbol"])
    if sym_count >= limits.max_trades_per_symbol:
        return False, "max_trades_per_symbol"

    c = clusters.get(desired["symbol"])
    if c is not None:
        cluster_trades = [p for p in open_positions if clusters.get(p["symbol"]) == c]
        if len(cluster_trades) >= limits.max_trades_per_cluster:
            return False, "max_trades_per_cluster"
        same_dir = [p for p in cluster_trades if p["dir"] == desired["dir"]]
        if len(same_dir) >= limits.max_trades_per_direction_per_cluster:
            return False, "cluster_direction_cap"

    # Aggregate risk (stops assumed honored)
    total_risk = sum(p["risk_pct"] for p in open_positions) + desired["risk_pct"]
    if total_risk > limits.max_portfolio_risk_pct:
        return False, f"portfolio_risk {total_risk:.2f} > {limits.max_portfolio_risk_pct}"

    # Margin headroom
    util_after = (margin_used + desired["margin_est"]) / max(equity, 1e-9) * 100
    if util_after > limits.max_margin_util_pct:
        return False, f"margin_util {util_after:.1f}% > {limits.max_margin_util_pct}%"

    return True, "ok"
```

Call this **before** routing a signal to the bridge. If `can_open_new` returns False, log the reason and skip — do not queue.

---

## Natural hedges: lower risk, not diversification

These pairs co-move *negatively* most of the time:

| Pair A | Pair B | Typical ρ | Note |
|--------|--------|-----------|------|
| EURUSD long | USDCHF long | −0.85 | Both USD side cancels — check DXY instead |
| GBPUSD long | EURGBP long | −0.70 | Cross-rate trap |
| XAUUSD long | DXY long | −0.55 | Gold ↑ when dollar ↓ |
| SPX500 long | VIX long | −0.80 | Classic fear hedge |

**Rule**: if you already have `EURUSD long`, opening `USDCHF long` should count as *reducing* the EURUSD position, not adding. Track cluster + direction — if signed direction cancels in the cluster, allow it; if it stacks, block.

```python
def signed_cluster_exposure(open_positions, clusters, signs: dict[str, int]) -> dict[int, float]:
    """signs: {'EURUSD': +1, 'USDCHF': -1, ...}  # whether 'long' means USD-weak"""
    exp: dict[int, float] = {}
    for p in open_positions:
        c = clusters.get(p["symbol"])
        if c is None:
            continue
        s = signs.get(p["symbol"], 1) * p["dir"]
        exp[c] = exp.get(c, 0.0) + s * p["lot_risk_eq"]
    return exp
```

---

## Aggregate risk budget

Rule: **sum of open-trade-risk ≤ max_portfolio_risk_pct**, and deduct from budget as trades open.

```python
class RiskBudget:
    def __init__(self, equity: float, cap_pct: float = 3.0):
        self.equity = equity
        self.cap = cap_pct
        self.used = 0.0

    def request(self, risk_pct: float) -> float:
        """Return the risk_pct actually granted (may be clipped to remaining)."""
        remaining = self.cap - self.used
        grant = max(0.0, min(risk_pct, remaining))
        self.used += grant
        return grant

    def release(self, risk_pct: float):
        """Called when a trade closes. Never go below zero."""
        self.used = max(0.0, self.used - risk_pct)

    def reset_daily(self):
        self.used = 0.0
```

Every signal asks for budget before it sends. If the grant is 0, the signal is dropped for the session. If it's clipped (e.g., asked for 1%, got 0.6%), resize lots downward — do NOT let a fractional grant slip through at the original size.

---

## Concurrent-trade limits on the EA side

Portfolio caps belong in the brain, but the EA needs a belt-and-suspenders check — the brain can crash, the bridge can stale. EA checks `PositionsTotal()` and filters by `magic` + `symbol`.

```cpp
int CountMyPositions(const long magic, const string sym = "") {
    int count = 0;
    for (int i = PositionsTotal() - 1; i >= 0; i--) {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        if (PositionGetInteger(POSITION_MAGIC) != magic) continue;
        if (sym != "" && PositionGetString(POSITION_SYMBOL) != sym) continue;
        count++;
    }
    return count;
}

bool EACanOpen(const int max_per_symbol, const int max_total) {
    if (CountMyPositions(InpMagic, _Symbol) >= max_per_symbol) {
        LogSkip("symbol_cap");
        return false;
    }
    if (CountMyPositions(InpMagic) >= max_total) {
        LogSkip("magic_cap");
        return false;
    }
    return true;
}
```

**Why both**: the brain tracks its intent (what it thinks is open); the EA tracks reality (what the terminal reports). They drift — slipped fills, manual closes, server restarts.

---

## Margin utilization: the silent killer

At 1:500 leverage, each 0.10 XAUUSD lot consumes ~$40 margin. Ten positions = $400. On a $5,000 account that's 8% — fine. On a $500 account that's 80% — one adverse tick = margin call.

```python
def margin_ok(equity: float, margin_used: float, incoming_margin: float,
              soft_cap_pct: float = 30.0, hard_cap_pct: float = 50.0) -> tuple[bool, str]:
    util = (margin_used + incoming_margin) / equity * 100
    if util >= hard_cap_pct:
        return False, f"HARD margin cap {util:.1f}% ≥ {hard_cap_pct}%"
    if util >= soft_cap_pct:
        return False, f"SOFT margin cap {util:.1f}% ≥ {soft_cap_pct}% — raise intentionally"
    return True, "ok"
```

Read live values via `mt5.account_info()`:

```python
info = mt5.account_info()
equity = info.equity
margin_used = info.margin          # already deducted by MT5
margin_free = info.margin_free
margin_level = info.margin_level   # (equity / margin) * 100; <100 = can't open more
```

**Kill-switch**: if `margin_level < 200`, close all new-signal intent, log, and alert.

---

## Portfolio-level daily kill-switch

Per-trade stops are not enough. The account-level daily loss is the line that matters.

```python
class DailyKillSwitch:
    def __init__(self, max_daily_loss_pct: float = 3.0):
        self.start_equity = None
        self.cap = max_daily_loss_pct
        self.tripped = False

    def tick(self, equity: float, now) -> bool:
        # Reset at broker midnight (use server time, not local)
        if self.start_equity is None or now.date() != self.day:
            self.start_equity = equity
            self.day = now.date()
            self.tripped = False
        dd = (self.start_equity - equity) / self.start_equity * 100
        if dd >= self.cap:
            self.tripped = True
        return self.tripped
```

When tripped: (a) stop generating new signals, (b) optionally close all open positions, (c) send Telegram alert, (d) stay tripped until manual reset or next trading day.

---

## Correlation-aware lot sizing

If you insist on running 3 trades in the same cluster, size each one down:

```python
def cluster_adjusted_risk(base_risk_pct: float, cluster_open_count: int,
                          cluster_beta: float = 1.0) -> float:
    """base_risk_pct / (1 + additional_exposure)"""
    if cluster_open_count == 0:
        return base_risk_pct
    # 2nd trade = half, 3rd = third, etc.
    return base_risk_pct / (1 + cluster_open_count * cluster_beta)
```

So asking for 1% risk on the 2nd XAUUSD long returns 0.5%. On the 3rd: 0.33%. The portfolio-cluster-sum stays bounded.

---

## Rules (non-negotiable)

1. **Compute, don't assume correlation.** Rerun weekly. Log the matrix to disk for audit.
2. **Cluster-level caps come before symbol-level caps.** The risk-off cluster is the dangerous one.
3. **Every new signal asks the RiskBudget before sending to the bridge.** No "oops, we went over 3%".
4. **Both brain and EA enforce concurrent-trade limits.** Belt and suspenders.
5. **Margin level < 200 is a hard stop.** No new trades, period.
6. **Daily kill-switch is account-wide, not per-symbol.** Tripping XAUUSD should not leave EURUSD running wild.
7. **Natural hedges are allowed, stacking same-direction cluster is blocked.** Long EURUSD + long GBPUSD + long AUDUSD = one big short-USD trade — count it as such.

---

## Common bugs

1. **Double-counting margin.** `account_info().margin` already includes existing trades. Don't re-sum from positions.
2. **Using static correlation from 2 years ago.** Gold ↔ S&P correlation *flipped* in 2022. Rerun.
3. **Reset daily kill-switch on local midnight, not broker midnight.** On a GMT+3 broker you'll reset 3 hours early/late.
4. **Cluster ID assigned to new symbol without recomputing.** If a symbol isn't in the matrix, cluster-lookup returns None → the check silently passes. Default to "unknown = most-conservative cluster".
5. **Brain tracking opens without reading back from terminal.** A slipped fill / rejected order leaves the brain thinking it's short when nothing opened. Poll `positions_get()` every N ticks and reconcile.
6. **Closing order for kill-switch uses market order at wide spread.** Use `ORDER_TYPE_CLOSE_BY` where possible, or set a wide deviation. Don't fail-to-close because price moved 5 pts.
7. **Same magic number across symbols.** Makes `CountMyPositions(magic, sym)` ambiguous. Use `magic = base + symbol_hash` so each (strategy, symbol) gets a unique magic.

---

## Reconciliation loop (brain ↔ terminal)

```python
def reconcile(expected: dict[int, dict], terminal_positions: list) -> dict:
    """Expected: {magic: {...}}. Returns a diff."""
    terminal_by_ticket = {p.ticket: p for p in terminal_positions}
    expected_tickets = {v["ticket"] for v in expected.values() if "ticket" in v}
    ghost_in_brain = expected_tickets - set(terminal_by_ticket)       # brain thinks open, gone
    ghost_on_terminal = set(terminal_by_ticket) - expected_tickets    # open on broker, brain unaware
    return {"ghost_in_brain": list(ghost_in_brain),
            "ghost_on_terminal": list(ghost_on_terminal)}
```

Run every 30s. If either ghost set is non-empty, alert and freeze new signals until resolved.

---

## GitHub references

- **EA31337-classes** — `Position.mqh`, `Order.mqh` helpers for counting and filtering positions by magic/symbol.
- **freqtrade** — `protections/` module has correlation-protection, cooldown-period, stoploss-guard patterns worth porting.
- **jesse-ai/jesse** — Python backtester with built-in portfolio-level risk routing; study `jesse.services.selectors`.
- **quantconnect/Lean** — `PortfolioConstructionModel` abstraction; `MaximumDrawdownPercentPerSecurity`.
- **pmorissette/bt** — Python backtester designed around portfolio weights first, individual trades second.
- **TheGloriousCodex/mlfinlab** — `portfolio_optimization/` (HRP = Hierarchical Risk Parity, CLA) for when you graduate beyond hard caps.

---

## Extension workflow

When you add a new symbol:

1. Add to `SYMBOLS` list in `correlation.py`. Rerun `correlation_matrix()`.
2. Inspect the new row/column. Any |ρ| ≥ 0.6 with an existing symbol? → same cluster.
3. Backtest single-symbol on the new symbol with the existing strategy. If Sharpe < 1.0 standalone, don't add.
4. Bump `max_open_trades` only if the new cluster is genuinely uncorrelated (ρ < 0.3 with all existing clusters).
5. Update `signs` dict for natural-hedge detection (is "long" this symbol USD-weak or USD-strong?).
6. Run a 2-week paper trade on the expanded portfolio before live. Watch aggregate drawdown, not per-symbol.

When you change cluster thresholds (e.g., 0.6 → 0.5):

1. Rerun `cluster()` — expect more symbols to merge.
2. Tighten `max_trades_per_cluster` proportionally (if clusters shrink in number, per-cluster cap shrinks too).
3. Replay last 3 months through the cap logic to confirm no false-blocks on previously-allowed good trades.

---

## Quick sanity checks

Run these before every live session:

```python
info = mt5.account_info()
print(f"Equity: ${info.equity:.2f}  Margin: ${info.margin:.2f}  Free: ${info.margin_free:.2f}")
print(f"Margin level: {info.margin_level:.0f}%")
positions = mt5.positions_get()
print(f"Open positions: {len(positions)}")
for p in positions:
    print(f"  {p.symbol} {p.type} {p.volume} magic={p.magic} profit={p.profit:.2f}")
corr = correlation_matrix()
print("\nCorrelation matrix (last 1000 H1 bars):")
print(corr.round(2))
print("\nClusters:", cluster(corr))
```

If margin level is < 300% or any cluster already has 2+ positions, **do not start** new signals until you understand why.
