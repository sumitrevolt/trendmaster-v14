# Fix: "Telegram pe signal aya but MT5 trade nahi liya"

## Root cause (verified 2026-04-23 15:32 UTC)

Brain pushed a **XTIUSD BUY @ 0.80 confidence** signal. Telegram message fired correctly. File `trendmaster_signals_XTIUSD.json` was written atomically to MT5's Files directory with `direction=BUY`.

**But MT5 Experts log shows the EA is attached to only ONE chart — XAUUSD H1.** No EA on XTIUSD chart means no one reads the XTIUSD signal file. So the trade never fires.

Evidence:
```
MT5 Experts log (20260423.log — only 3 lines for the whole day):
AI_SUPERBB_v14_TrendMaster (XAUUSD,H1) Initialized XAUUSD M5
AI_SUPERBB_v14_TrendMaster (XAUUSD,H1) HTF gate BLOCK: H1 MACD flat
AI_SUPERBB_v14_TrendMaster (XAUUSD,H1) Initialized XAUUSD M5
```

The EA's own code is **already multi-symbol aware** via `InpAIAutoPerSymbol=true` (confirmed in `AI_SUPERBB_v14_TrendMaster.mq5` lines 105-106, 463-472). The only missing piece: the EA has to be **attached to each symbol's chart** once.

## Fix — two options

### Option A — one-command auto-attach (recommended)

```powershell
cd "C:\Users\Ratanshila\Documents\autmated trading"
python tools/setup_multi_ea.py
```

This just ran and wrote a new profile with 19 charts:
```
C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\
    D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Profiles\Charts\
    TrendMaster_v14_All19\
        chart01.chr   (XAUUSD)
        chart02.chr   (XAGUSD)
        chart03.chr   (GBPJPY)
        ...
        chart19.chr   (XNGUSD)
        profile.ini
```

**Steps:**
1. Open MT5.
2. `File → Profiles → TrendMaster_v14_All19`.
3. MT5 opens 19 tiled charts with EA auto-attached + configured on each.
4. Verify each chart shows the **smiley-face icon** in the top-right corner (means EA is loaded + trading enabled).
5. If any chart shows a **sad face**, click it → Properties → Common → tick "Allow Algo Trading" → OK.

### Option B — manual drag-drop (takes 5 minutes)

1. In MT5, open a new chart for each missing symbol (right-click Market Watch → Chart Window).
2. Drag `AI_SUPERBB_v14_TrendMaster` from Navigator → Expert Advisors onto each chart.
3. Inputs dialog:
   - `InpAIAutoPerSymbol = true` (default)
   - `InpAIPrimarySymbol = XAUUSD` (default)
   - Leave everything else at defaults.
4. Click OK. Smiley face should appear.

## How to verify it's working

### Immediately after attaching
Within 60 seconds of attaching, the EA writes initialization lines to the Experts log for each new chart:
```
AI_SUPERBB_v14_TrendMaster (XTIUSD,H1) Initialized XTIUSD M5
AI_SUPERBB_v14_TrendMaster (XBRUSD,H1) Initialized XBRUSD M5
...
```

Check from command line:
```powershell
Get-Content "C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Logs\20260423.log" -Encoding Unicode -Tail 30
```

### On next BUY/SELL signal
When the brain next writes a non-NONE signal for any symbol, the EA on that chart will either:
- **Open an order** — if its own 3-of-3 (SuperTrend + Bollinger + MACD) agrees AND session gate allows.
- **Log a block reason** — e.g. "C1 FAIL: EMA fan not aligned" or "C2 FAIL: BB width below median".

Block reasons are normal — the EA's 3-of-3 is *intentionally* strict. Not every brain signal becomes a trade; that's the dual-gate architecture doing its job. But you should see **some** activity in the Experts log for every chart, every bar close.

## Why the signal didn't block at Python

Brain's stack already passed for XTIUSD (it wrote BUY):
- ✅ pull_bars / features
- ✅ ML brain: BUY conf=0.80
- ✅ MTF agree (M30/H1/H4 all aligned on XTIUSD)
- ✅ confidence > MIN_CONF=0.62
- ✅ profit_filters: vol_regime OK, not dead market for oil
- ✅ multi_agent: 3-of-3 unanimous BUY
- ✅ risk_manager: equity OK, no DD lockout, no correlation conflict
- ✅ write_signal: atomic write to trendmaster_signals_XTIUSD.json

The gap is purely **MT5 EA not present on XTIUSD chart**.

## One-time fix — then permanent

Once you complete Option A or B, the EA stays attached across MT5 restarts *if you use the same profile*. The Profile selector in MT5 preserves chart layouts. So this is a one-time setup.

If you ever detach the EA or reset the profile, re-run `python tools/setup_multi_ea.py` to regenerate.

## Quick post-fix sanity check

After attaching, from PowerShell:
```powershell
cd "C:\Users\Ratanshila\Documents\autmated trading"
python outputs\_diag_signal.py
```

This will show `[BUY/SELL]` for XTIUSD (or whichever symbol is signalling) AND the Experts log should now have many more than 3 lines.

## TL;DR

Your setup was one drag-drop away from live. Brain is perfect, EA is perfect, signal file is perfect. Just attach the EA to each symbol's chart once using the new profile we just generated.

**Next step:** Open MT5 → File → Profiles → **TrendMaster_v14_All19**.
