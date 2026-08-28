# TV Alert Bridge — fix Rocket Prime "no direction" rejects

**Problem solved:** Rocket Prime indicator's Pine source uses Pine's `alert()`
runtime call which OVERRIDES whatever message template you type in TV's
alert dialog. Result: webhook receives only `#### BTCUSD ####` (17 chars,
no direction). Bot rejects with "REJECT no-direction" → zero trades.

**Solution:** A companion Pine indicator `rocket_prime_alert_bridge.pine`
that reads RP's plots via `input.source()` and re-emits proper
directional alerts via `alertcondition()`. Pine's `alertcondition()` is
declarative — TV respects the message template you set in the alert
dialog. The bug only affects `alert()`.

## Setup steps (one-time per pair × timeframe)

### Step 1 — install the bridge indicator

1. Open `tools/tv_alert_setup/rocket_prime_alert_bridge.pine` in this
   repo. Copy the entire Pine source.
2. In TradingView, open Pine Editor (bottom panel `Pine Editor` tab).
3. Paste, click **Save** → name it "RP Alert Bridge" → save.
4. Click **Add to chart**. The indicator appears in a sub-pane.

### Step 2 — bind RP's plots

1. Click the gear icon on "RP Alert Bridge" in chart.
2. **RP Buy plot** dropdown → pick Rocket Prime's "Buy Observation"
   plot (or whatever RP names its Long signal — could be "p0", "Long",
   "Buy Signal", etc. — pick the one that goes non-zero on BUY).
3. **RP Sell plot** dropdown → pick the equivalent for SELL.
4. **Cross-up threshold** — leave at 0.0 for spike-style plots (default
   RP behavior). Set to 0.5 if RP uses boolean 1/0 plots.
5. Apply.

You should see green up-triangles and red down-triangles on the bridge
sub-pane confirming when each direction fires.

### Step 3 — create alerts on the bridge (NOT on RP directly)

For BTCUSD 5m as an example:

**BUY alert:**
- Right-click chart → Create Alert (or click + button)
- Condition: select **"RP Alert Bridge"** → **"BUY signal"**
- Options: **Once Per Bar Close** (or "Once Per Bar" if you want every fire)
- Webhook URL: `https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret=5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14&symbol=BTCUSD&tf=5`
  (this is the operator's existing webhook URL — adjust symbol+tf per pair)
- Notification: enable webhook
- Message: leave default OR set explicitly:

  ```
  BUY|{{ticker}}|tf={{interval}}|p0={{plot_0}}|p1={{plot_1}}
  ```

  This format is already understood by `ai_trading_agents/tv_executor.py`.

**SELL alert** — same as above but pick **"SELL signal"** condition,
and message starts with `SELL|`.

### Step 4 — disable old RP-direct alerts

Delete or disable the old "RP fires alert from inside Pine" alerts —
they'll keep generating no-direction rejects otherwise. The bridge
alerts replace them.

## How many alerts total

Per pair × timeframe = 2 alerts (1 BUY + 1 SELL).

Operator's current 5-pair setup (XAUUSD, EURUSD, USDJPY, GBPUSD, BTCUSD)
× 4 timeframes (M5, M15, M30, H1) × 2 directions = **40 alerts**.

Matches the existing `outputs/03_recreate_rp_alerts_2026-05-09.cmd`
naming, but the actual content/condition differs — those were
RP-direct, these are bridge-routed.

## Verification

After setup, when next BUY signal fires:

1. Bridge sub-pane shows green up-triangle.
2. Webhook log (`logs/tv_webhook.log`) shows:
   ```
   TEXT mode parse: symbol=BTCUSD direction=BUY tf=5 body=BUY|BTCUSD|tf=5|p0=...
   TV→EA OK  symbol=BTCUSD dir=BUY tf=M5 ...
   ```
3. python_executor places the trade (subject to safeguards/concentration).

If you see `dir=NONE` instead of `dir=BUY`, the bridge isn't bound to
the right RP plot — re-check Step 2.

## Why this fix is structurally clean

- Bridge has zero dependencies on RP's internal Pine code (can't be
  broken by an RP update).
- `alertcondition()` is the ONLY Pine alert mechanism that respects
  the user-typed message template — guaranteed to forward direction.
- Plot-source binding via `input.source()` works with any indicator
  that exposes its observation plots (most do).
- Bot's existing TV parser (`tv_executor.py`) already handles the
  `BUY|SYMBOL|tf=N|...` format — no bot changes needed.

## If RP's plots are NOT exposed (closed-source / private)

Some commercial RP variants don't expose plots externally. In that
case the bridge can't bind. Fallbacks (in order of preference):

1. **Replace the indicator** — find an open-source RP equivalent with
   accessible plots.
2. **Use TradingView "Cross" alert on the indicator's visible plot**
   in the chart UI — TV's "Cross" alert type respects message templates
   even though it's not `alertcondition()`.
3. **OCR the chart** — last resort, requires Chrome+Playwright pipeline.
   Not recommended for live trading.
