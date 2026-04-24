---
name: trading-order-execution
description: "Order execution mechanics for an MT5 Expert Advisor. Use when building or debugging the actual trade-send layer: order types (market/limit/stop/stop-limit), FILLING_MODE handling, deviation/slippage, partial fills, requote retry logic, retcode table, modify/close flows, broker-specific quirks (OctaFX / ICMarkets / Exness), hedging vs netting accounts. The layer between 'we decided to trade' and 'the broker confirmed it'."
---

# trading-order-execution

Between your strategy and your PnL sits the order execution layer. Most retail code gets this wrong in subtle ways that only bite during volatile periods: wrong filling mode, missing deviation, unhandled requotes, SL/TP inside stops level. This skill covers the mechanics cleanly.

**Core principle:** every order-send is a request that can fail 20 different ways. Handle retcodes explicitly — log the rejection reason, decide retry vs. abandon, never assume success.

## When to use

- Writing the `SendOrder` / `ModifyPosition` / `ClosePosition` helpers.
- Debugging rejected orders (`retcode != TRADE_RETCODE_DONE`).
- Porting between brokers (they implement FILLING_MODE differently).
- Choosing between market / limit / stop orders for a given entry style.
- Handling partial fills on larger lot sizes.
- Supporting both hedging and netting accounts.

## 1. Order types — when to use each

| Type | When price | Use for | Risk |
|---|---|---|---|
| **Market** | Any | Immediate entry after signal | Slippage in fast markets |
| **Buy/Sell Limit** | Pullback to level | Entry at a specific level, no chase | May never fill |
| **Buy/Sell Stop** | Breakout level | Entry on confirmation of momentum | Fills in the worst tick of a breakout |
| **Stop-Limit** | Level with cap | Breakout entry with max slippage | Complex; fewer brokers support |

**For this project:** market orders from the 4-filter funnel. Limit/stop pending orders are only useful for specific strategies (ORB, pullback limits).

## 2. Canonical market-order send (MQL5)

```cpp
bool SendMarket(int dir_sign, double lots, double sl_px, double tp_px,
                string comment, int magic)
{
    MqlTradeRequest req;  ZeroMemory(req);
    MqlTradeResult  res;  ZeroMemory(res);

    MqlTick tick;
    if(!SymbolInfoTick(_Symbol, tick)) {
        DBG("SendMarket: no tick");
        return false;
    }

    req.action       = TRADE_ACTION_DEAL;
    req.symbol       = _Symbol;
    req.volume       = NormalizeLot(lots);
    req.type         = (dir_sign > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
    req.price        = (dir_sign > 0) ? tick.ask : tick.bid;
    req.sl           = ClampSLTP(sl_px, req.type, req.price);
    req.tp           = ClampSLTP(tp_px, req.type, req.price);
    req.deviation    = InpMaxDeviationPts;        // e.g. 20 points
    req.magic        = magic;
    req.comment      = comment;
    req.type_filling = PickFilling();             // see §4
    req.type_time    = ORDER_TIME_GTC;

    if(!OrderSend(req, res)) {
        DBG(StringFormat("OrderSend failed: code=%d comment=%s",
                         res.retcode, res.comment));
        return HandleRetcode(res.retcode, req);
    }
    if(res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_PLACED) {
        DBG(StringFormat("OrderSend bad retcode: %d", res.retcode));
        return HandleRetcode(res.retcode, req);
    }
    DBG(StringFormat("Order OK: ticket=%d deal=%d volume=%.2f",
                     res.order, res.deal, res.volume));
    return true;
}
```

Every field matters. Missing `deviation` causes `TRADE_RETCODE_REQUOTE`. Wrong `type_filling` causes `TRADE_RETCODE_INVALID_FILL`. Missing `magic` means your EA can't find its own positions on restart.

## 3. Lot normalization

Broker rejects non-step-aligned volumes. Always clamp:

```cpp
double NormalizeLot(double lots)
{
    double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double mn   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double mx   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double l    = MathFloor(lots / step) * step;           // round DOWN
    l = MathMax(mn, MathMin(mx, l));
    int digs = (int)MathMax(0, -MathLog10(step));          // lot precision digits
    return NormalizeDouble(l, digs);
}
```

**Round down**, not nearest — rounding up can exceed your risk budget.

## 4. Filling mode — the single most common rejection

Brokers support different subsets of fill modes. MT5 will return `TRADE_RETCODE_INVALID_FILL` (10030) if you pick unsupported.

| Mode | Meaning | Typical support |
|---|---|---|
| `ORDER_FILLING_FOK` | Fill or Kill — all or nothing | ECN / STP brokers |
| `ORDER_FILLING_IOC` | Immediate or Cancel — partial fill OK | Most brokers |
| `ORDER_FILLING_RETURN` | Order sits if not filled | Market-maker brokers |
| `ORDER_FILLING_BOC` | Book or Cancel | Rarer |

### Dynamically pick a supported mode

```cpp
ENUM_ORDER_TYPE_FILLING PickFilling()
{
    int modes = (int)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
    // modes is a bitmask over SYMBOL_FILLING_FOK / SYMBOL_FILLING_IOC
    if((modes & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
    if((modes & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
    return ORDER_FILLING_RETURN;   // fallback — market-maker brokers
}
```

Common broker defaults:

- **OctaFX / Exness / ICMarkets** → IOC usually supported, FOK often too.
- **XM / FBS** → varies; always probe via `PickFilling`.

## 5. SL/TP clamping to STOPS_LEVEL

Brokers enforce a minimum distance between current price and SL/TP. Submit inside that and you get `TRADE_RETCODE_INVALID_STOPS` (10016).

```cpp
double ClampSLTP(double px, ENUM_ORDER_TYPE type, double ref_price)
{
    if(px <= 0) return 0;
    double stops_pts = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
    double min_dist  = MathMax(stops_pts * _Point, 5 * _Point);

    if(type == ORDER_TYPE_BUY) {
        // SL below, TP above
        if(px < ref_price && ref_price - px < min_dist) px = ref_price - min_dist;
        if(px > ref_price && px - ref_price < min_dist) px = ref_price + min_dist;
    } else if(type == ORDER_TYPE_SELL) {
        if(px > ref_price && px - ref_price < min_dist) px = ref_price + min_dist;
        if(px < ref_price && ref_price - px < min_dist) px = ref_price - min_dist;
    }
    return NormalizeDouble(px, _Digits);
}
```

**Freeze level** (`SYMBOL_TRADE_FREEZE_LEVEL`) is a secondary concept — the distance within which you can't *modify* existing orders. Check both when modifying.

## 6. Deviation / slippage

`req.deviation` is the maximum acceptable price deviation (in points) between your requested price and the execution price, on market orders. Too small → requotes. Too large → silent slippage eats profits.

**Rule of thumb:**
- **Quiet markets:** 10-20 points
- **Normal trading:** 20-30 points
- **News / volatile:** 50-100 points (or don't trade)

Set as an input, don't hard-code:

```cpp
input int InpMaxDeviationPts = 30;
```

For XAUUSD specifically, 30 points = $0.30; during a normal minute, this is plenty. Around NFP it's useless — which is why the news filter exists.

## 7. Retcode handling

Every broker reply comes with a `retcode`. The common ones:

| Retcode | Constant | Meaning | Action |
|---|---|---|---|
| 10004 | `TRADE_RETCODE_REQUOTE` | Price moved | Retry with wider deviation, up to 2× |
| 10006 | `TRADE_RETCODE_REJECT` | Generic reject | Check `comment`; no retry |
| 10008 | `TRADE_RETCODE_PLACED` | Pending order placed | Success for pending |
| 10009 | `TRADE_RETCODE_DONE` | Market order filled | Success |
| 10010 | `TRADE_RETCODE_DONE_PARTIAL` | Partial fill | Handle remaining volume (§9) |
| 10013 | `TRADE_RETCODE_INVALID` | Malformed request | Log full request, fix code |
| 10014 | `TRADE_RETCODE_INVALID_VOLUME` | Lot rejected | Re-normalize; check step |
| 10015 | `TRADE_RETCODE_INVALID_PRICE` | Stale price | Refresh tick, retry once |
| 10016 | `TRADE_RETCODE_INVALID_STOPS` | SL/TP too close | Apply `ClampSLTP`; resubmit |
| 10017 | `TRADE_RETCODE_TRADE_DISABLED` | Trading disabled by broker | Don't retry |
| 10018 | `TRADE_RETCODE_MARKET_CLOSED` | Out of session | Don't retry |
| 10019 | `TRADE_RETCODE_NO_MONEY` | Not enough margin | Reduce size |
| 10021 | `TRADE_RETCODE_PRICE_OFF` | Quotes outdated | Refresh, retry |
| 10030 | `TRADE_RETCODE_INVALID_FILL` | Filling mode unsupported | Try next mode (§4) |
| 10040 | `TRADE_RETCODE_TRADE_TIMEOUT` | Broker slow | Retry once |

### Retry logic

```cpp
bool HandleRetcode(uint code, MqlTradeRequest &req)
{
    static int retries = 0;
    if(retries >= 2) { retries = 0; return false; }
    retries++;

    switch(code) {
        case TRADE_RETCODE_REQUOTE:
        case TRADE_RETCODE_PRICE_OFF:
        case TRADE_RETCODE_INVALID_PRICE:
        {
            // refresh tick, widen deviation
            MqlTick t; SymbolInfoTick(_Symbol, t);
            req.price = (req.type == ORDER_TYPE_BUY) ? t.ask : t.bid;
            req.deviation *= 2;
            MqlTradeResult r; ZeroMemory(r);
            OrderSend(req, r);
            return (r.retcode == TRADE_RETCODE_DONE);
        }
        case TRADE_RETCODE_INVALID_FILL:
            // next filling mode
            req.type_filling = (req.type_filling == ORDER_FILLING_FOK) ?
                               ORDER_FILLING_IOC : ORDER_FILLING_RETURN;
            MqlTradeResult r; ZeroMemory(r);
            OrderSend(req, r);
            return (r.retcode == TRADE_RETCODE_DONE);
        default:
            return false;
    }
}
```

Max 2 retries per order — prevents infinite loops if broker is sick.

## 8. Modify position (move SL / TP / trail)

```cpp
bool ModifySL(ulong ticket, double new_sl, double new_tp = 0)
{
    if(!PositionSelectByTicket(ticket)) return false;
    double cur_sl = PositionGetDouble(POSITION_SL);
    double cur_tp = PositionGetDouble(POSITION_TP);
    new_tp = (new_tp == 0) ? cur_tp : new_tp;

    // skip no-op modifies (broker rejects/counts them against rate limits)
    double min_move = 3 * _Point;
    if(MathAbs(new_sl - cur_sl) < min_move && MathAbs(new_tp - cur_tp) < min_move)
        return true;

    MqlTradeRequest req; ZeroMemory(req);
    MqlTradeResult  res; ZeroMemory(res);
    req.action   = TRADE_ACTION_SLTP;
    req.position = ticket;
    req.symbol   = _Symbol;
    req.sl       = ClampSLTP(new_sl, (ENUM_ORDER_TYPE)PositionGetInteger(POSITION_TYPE),
                             PositionGetDouble(POSITION_PRICE_CURRENT));
    req.tp       = ClampSLTP(new_tp, (ENUM_ORDER_TYPE)PositionGetInteger(POSITION_TYPE),
                             PositionGetDouble(POSITION_PRICE_CURRENT));
    if(!OrderSend(req, res)) return false;
    return (res.retcode == TRADE_RETCODE_DONE);
}
```

**Never loosen a stop** (move SL further from price — always protective). Guard in `TryTrail`:

```cpp
if(dir > 0 && new_sl <= cur_sl) return;   // don't move long SL down
if(dir < 0 && new_sl >= cur_sl) return;   // don't move short SL up
```

## 9. Partial fills

Rare on retail accounts, common on larger sizes or during fast markets. If `result.retcode == TRADE_RETCODE_DONE_PARTIAL`:

```cpp
double filled = result.volume;
double remaining = req.volume - filled;
if(remaining > SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) {
    // decide: chase with another market order, or accept partial
    if(InpChasePartials) {
        req.volume = NormalizeLot(remaining);
        OrderSend(req, result);   // second attempt
    } else {
        DBG(StringFormat("partial fill %.2f of %.2f, accepted", filled, req.volume));
    }
}
```

For retail, usually accept the partial — chasing in a fast market can make it worse.

## 10. Close position

Full close:

```cpp
bool ClosePosition(ulong ticket)
{
    if(!PositionSelectByTicket(ticket)) return false;
    double vol = PositionGetDouble(POSITION_VOLUME);

    MqlTick t; SymbolInfoTick(_Symbol, t);
    ENUM_ORDER_TYPE close_type = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
                                  ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
    double close_price = (close_type == ORDER_TYPE_SELL) ? t.bid : t.ask;

    MqlTradeRequest req; ZeroMemory(req);
    MqlTradeResult  res; ZeroMemory(res);
    req.action       = TRADE_ACTION_DEAL;
    req.position     = ticket;
    req.symbol       = _Symbol;
    req.volume       = vol;
    req.type         = close_type;
    req.price        = close_price;
    req.deviation    = InpMaxDeviationPts;
    req.magic        = InpMagic;
    req.type_filling = PickFilling();
    return OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE;
}
```

Partial close: set `req.volume = smaller_than_position`. Broker closes proportionally.

## 11. Hedging vs netting accounts

MT5 accounts come in two flavors:

- **Hedging** — you can hold opposite positions simultaneously (BUY 0.1 + SELL 0.1 coexist). Most retail accounts.
- **Netting** — positions aggregate into a single net position per symbol. Stock-trading accounts typically.

Check with:

```cpp
ENUM_ACCOUNT_MARGIN_MODE mode = (ENUM_ACCOUNT_MARGIN_MODE)
                                AccountInfoInteger(ACCOUNT_MARGIN_MODE);
bool is_hedging = (mode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);
```

### Behavior differences

- On netting, `BUY 0.1` + `SELL 0.1` = **position closed**, not two positions.
- On netting, `ClosePosition(ticket)` doesn't exist the same way — you send an opposite deal.
- `PositionsTotal()` on netting = up to 1 position per symbol. On hedging = any number.

For robust code: iterate `PositionsTotal()` and filter by symbol+magic — works for both. Write close/modify in terms of tickets (hedging) but fall back to opposing-deal logic on netting.

## 12. Broker-specific quirks

| Broker | Quirk |
|---|---|
| **OctaFX Demo** (this project) | Standard MT5, IOC supported, STOPS_LEVEL usually low (5-10 pts for XAUUSD) |
| **ICMarkets Raw** | Tight spreads, no requotes usually, FOK supported — good for news strategies |
| **Exness** | Wide instrument list, but STOPS_LEVEL on exotics can be high (100+ pts) |
| **XM / FBS** | Market-maker, more requotes, try FILLING_RETURN if FOK/IOC rejects |
| **FXCM** | Sometimes rejects `deviation < 10` for minors — bump to 20 |
| **Pepperstone** | Razor account has no minimum STOPS_LEVEL (0 pts on many pairs) |

Rule: probe `SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL)` and `SYMBOL_FILLING_MODE` on startup and log them. Don't assume.

## 13. Deal history — what the broker actually did

After a successful send, query history for audit:

```cpp
HistorySelect(TimeCurrent() - 3600, TimeCurrent());
for(int i = 0; i < HistoryDealsTotal(); i++) {
    ulong deal_ticket = HistoryDealGetTicket(i);
    if(HistoryDealGetInteger(deal_ticket, DEAL_ORDER) == result.order) {
        double fill_price  = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
        double commission  = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
        double swap        = HistoryDealGetDouble(deal_ticket, DEAL_SWAP);
        DBG(StringFormat("filled @ %.5f, commission=%.2f, swap=%.2f",
                         fill_price, commission, swap));
    }
}
```

Check fill vs. requested price = slippage. Track over time; if median slippage > 10 pts, switch broker or widen deviation.

## 14. Python-side order sending (alternative)

If you ever send orders from Python (bypassing the EA):

```python
import MetaTrader5 as mt5

def send_market(symbol: str, side: int, lots: float, sl: float, tp: float, magic: int):
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if not info or not tick: return None

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       float(lots),
        "type":         mt5.ORDER_TYPE_BUY if side > 0 else mt5.ORDER_TYPE_SELL,
        "price":        tick.ask if side > 0 else tick.bid,
        "sl":           float(sl),
        "tp":           float(tp),
        "deviation":    30,
        "magic":        magic,
        "comment":      "brain-direct",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(req)
    if result is None:
        print(f"order_send returned None: {mt5.last_error()}")
        return None
    return result
```

**Don't mix EA and Python order-sending on the same account** — they'll race for position management. Pick one.

## 15. Idempotency — avoiding double orders

If brain + EA both decide to open, you could end up with 2× position. Solutions:

- **Magic numbers separate concerns**: EA uses `InpMagic=20260422`; brain-direct sends (if any) use a different magic.
- **Before sending, check positions**: `CountPositionsByMagic(magic) == 0` before opening.
- **State file with pending intent**: brain writes "intent to open" to a file, EA clears it on fill. Brain refuses re-intents while pending.

## 16. Common execution bugs

- **Forgetting `deviation`** → first volatile tick causes `REQUOTE`, trade missed.
- **SL in points vs. price** → `req.sl = 50` is price 50, not 50 points below. Always compute as a price value.
- **Modify rate-limited** → broker caps modifies per minute; add `min_move` skip-noop.
- **Magic collision** → two EAs with same magic fight over the same position.
- **Refreshing tick too late** → quote moves between tick-fetch and order-send; refresh inside `SendMarket`, not seconds earlier.
- **Mixing Bid/Ask** → BUY uses Ask, SELL uses Bid. Inversion = immediate slippage.
- **`_Symbol` for position commands on a multi-symbol EA** → iterate positions by their own symbol, not `_Symbol`.

## 17. GitHub references

- `EA31337/EA31337-classes` — production-grade `Trade.mqh` with requote/fill handling.
- `MetaQuotes official code base` → search "CTrade class" — the official wrapper.
- `jimtin/python_trading_bot` — clean Python-side order-send example.
- `khramkov/Python-MQL5-Expert-Advisor` — socket-based alternative for brain-direct sending.

## Extension workflow

Adding a new retcode handler:

1. Log the raw retcode + comment first. Know what you're handling.
2. Decide: retry, abort, or fallback?
3. Cap retries globally per order (2-3 max).
4. Add a Prometheus counter (`orders_rejected_total{retcode="10016"}`) — quickly surfaces patterns.

Supporting a new broker:

1. On startup, log all `SYMBOL_TRADE_*`, `SYMBOL_FILLING_MODE`, `SYMBOL_VOLUME_*` for the primary symbol.
2. Try a test trade in demo; check fill price vs. requested.
3. Adjust `InpMaxDeviationPts` if requotes appear.
4. Add broker-specific notes to §12.
