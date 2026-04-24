# TrendMaster v14 — Visual Indicators Upgrade

**Date:** 2026-04-22 10:36 IST
**New EA version compiled:** 0 errors, 0 warnings (103,186 B .ex5)
**Brain PID:** 23028 (alive, 250 ms tick)
**MT5 PID:** 8804 (reloaded with new EA at 10:34:52)

---

## What changed

The v14 EA previously only showed a text dashboard in the top-left corner — no indicator lines or signal markers on the price chart. Users complained: *"chart me indicators and signals nahi dikhrahe"*.

This upgrade adds **real chart objects** drawn on the price panel, refreshed every 1 second by the EA's existing `OnTimer()` heartbeat.

### Added inputs (chart-overlay group)

All default to **true** — no user action needed.

| Input | Default | Effect |
|---|---|---|
| `InpShowEMAs` | true | Draw EMA20 (gold), EMA50 (blue), EMA200 (magenta) |
| `InpShowBB` | true | Draw Bollinger upper / middle / lower (light blue / gray) |
| `InpShowSuperTrend` | true | Draw SuperTrend line (green when up, red when down) |
| `InpShowArrows` | true | Place BUY/SELL arrow at any closed bar where 3-of-3 fires |
| `InpShowSLTPLines` | true | Horizontal lines at Entry (yellow dot) / SL (red dash) / TP (green dash) for every open position |
| `InpDrawBars` | 300 | How many bars of history get the overlay |
| `InpCol*` | various | Colors are user-editable per indicator |

### New code in `AI_SUPERBB_v14_TrendMaster.mq5`

- `DeleteTrendWithPrefix()` — wipe only our objects by `PFX` prefix, leave user drawings alone
- `DrawSegment()` — thin helper around `OBJ_TREND` (non-ray, background)
- `DrawPolyline()` — connect indicator buffer values bar-to-bar
- `DrawSTPolyline()` — SuperTrend line with per-bar color based on direction
- `DrawArrowAt()` — `OBJ_ARROW_BUY` / `OBJ_ARROW_SELL` at 3-of-3 bars
- `DrawSLTPLines()` — hlines on open positions with Entry/SL/TP labels
- `DrawIndicatorLines()` — master function, called once per second from `OnTimer()`

`OnTimer()` now also calls `ChartRedraw(0)` to force visual refresh.
`OnDeinit()` already calls `ObjectsDeleteAll(0, PFX)` → removing the EA cleans up all overlays automatically.

## End-to-end verification

```
--- MT5 log (fresh after EA reload) ---
10:34:52.821  AI_SUPERBB_v14_TrendMaster (XAUUSD,M5)  [TMv14] Initialized XAUUSD M5

--- Brain ---
2026-04-22 10:35:10  TrendMaster brain online | symbol=XAUUSD tf=M5 interval=250ms model=rule

--- Signal file ---
{"direction":"NONE","confidence":0.5,"ts":1776834363,"symbol":"XAUUSD","brain":"TrendMaster_v14"}
mtime: 2026-04-22 10:36:03  (advancing every ~250ms)
```

## What you will now see on the chart

Within 1 second of MT5 focusing the XAUUSD M5 chart:

1. Three EMA lines curving across the price (yellow/gold, blue, magenta)
2. Bollinger Band envelope (two sky-blue lines + gray midline)
3. SuperTrend step-line that's green during up-regimes and red during down-regimes
4. On any prior bar where all 3 confirmations aligned: a small up/down arrow at that bar's extreme
5. For any open position: three horizontal lines — yellow dotted (entry), red dashed (SL), green dashed (TP)
6. The existing text dashboard in the top-left corner (unchanged)

Next M5 bar closes at 10:40, 10:45, 10:50 — watch for either new `agreed=3/3` lines or a live arrow + entry on the chart.

## Files touched

- `AI_SUPERBB_v14_TrendMaster.mq5` — added VISUAL input group + `DrawIndicatorLines()` suite
- `AI_SUPERBB_v14_TrendMaster.ex5` — recompiled (103 KB)
- `tools/compile_ea.py` — reusable compile-via-CLI helper (copy, compile, read UTF-16 log)
- `tools/find_mt5.py` — MT5 install discovery helper
- `VISUAL_UPGRADE_STATUS.md` — this file

## How to revert or tweak

- **Turn off all lines but keep arrows:** set `InpShowEMAs=false`, `InpShowBB=false`, `InpShowSuperTrend=false` on the EA inputs panel.
- **Draw more/less history:** change `InpDrawBars` (default 300 = 25 hours on M5).
- **Change colors:** edit the `InpCol*` inputs — no recompile needed.
- **Recompile after edits:** run `C:\Users\Ratanshila\compile_ea.bat` — it copies source from the workspace into MT5's MQL5\Experts folder and compiles.
