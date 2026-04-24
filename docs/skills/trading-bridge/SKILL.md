---
name: trading-bridge
description: "Bridge contract between a Python signal brain and an MT5 Expert Advisor. Use when defining, evolving, or debugging the JSON signal file that the brain writes and the EA reads. Covers the schema, atomic writes, staleness checks, path resolution, backward-compatible versioning, debug sidecars, and socket-based alternatives. Keeps the two processes loosely coupled so either can crash without dragging the other down."
---

# trading-bridge

The single most important interface in this stack is the one between the Python brain and the MQL5 EA. If that bridge is flaky, everything downstream is flaky. If it's clean, the two processes can evolve independently and either can crash without taking the other with it.

This skill codifies the file-based JSON bridge used in this project (`trendmaster_signals.json`), plus sockets and named pipes as alternatives with the right trade-offs noted.

## When to use

- Adding a new field to the signal (e.g. `tp_price`, `sl_price`, `urgency`).
- Porting the bridge to another EA or another language.
- Debugging "EA sees stale signal" / "EA ignores signal" bugs.
- Deciding whether to swap file-based for sockets (usually: don't).

## 1. Why file-based?

Three options for brain ↔ EA IPC:

| Method | Pros | Cons |
|---|---|---|
| **JSON file** | Language-agnostic, survives restarts, inspectable by hand, atomic on Windows via `os.replace` | Polling adds 1-2 s latency |
| **TCP socket** | Sub-ms latency | One side crashing hangs the other; MT5 network code is fragile; hard to debug |
| **Named pipe** | Fast, local-only | Windows-specific; MT5 has limited API |

For a trading bot making entries off M30/H1/H4 bars, **file-based is the right answer** — the polling latency is a non-issue at that cadence and the robustness gains are enormous. The one time you need sub-ms is scalping on tick data, and that's not this system.

## 2. Signal schema (v1)

```json
{
  "schema":     1,
  "ts":         1745327013.42,
  "symbol":     "XAUUSD",
  "direction":  "BUY",
  "confidence": 0.68,
  "agents": {
    "dir":   "BUY",
    "votes": [
      {"name": "trend_h4",    "vote":  1, "reason": "clean bull fan"},
      {"name": "momentum_h1", "vote":  1, "reason": "macd hist rising +6.42"},
      {"name": "timing_m30",  "vote":  1, "reason": "above ema20 rsi=58.3"}
    ]
  }
}
```

**Design rules:**

- `schema` is explicit. Bump on any breaking change.
- `ts` is POSIX seconds — easy to compare with `TimeCurrent()` after subtracting broker GMT offset if needed.
- `direction` is a string, not an int. A `1`/`-1`/`0` int is unreadable when you `cat` the file during debugging.
- Keep the object *flat on the hot path*: `direction` and `confidence` are top-level; everything else lives under nested keys so a lazy EA can skip them.
- Prefer keys the EA doesn't need under a single nested object like `agents` so future additions don't touch the top level.

### Optional fields (recommended)

- `sl_price`, `tp_price` — brain-recommended stops; EA can override.
- `size_hint` — preferred lot (brain may know equity or a Kelly fraction you don't want to recompute in MQL5).
- `urgency` — `"now"` vs. `"on_next_bar"` if you want brain-driven pacing.
- `reason` — human-readable one-liner for the top-level decision.

### Versioning

Add new fields as optional. Never repurpose an existing field. If you must break the shape, bump `schema` and let the EA refuse mismatched versions:

```cpp
if(j["schema"].ToInt() != SIGNAL_SCHEMA_V) {
    DBG("signal schema mismatch, refusing");
    return;
}
```

## 3. Atomic write (Python side)

Never write directly to the target path. The EA may read a half-written file and crash or misparse.

```python
import json, os, tempfile

def write_signal(path: str, payload: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))   # compact, no whitespace
    os.replace(tmp, path)      # atomic rename on Windows + POSIX
```

**Rules:**

- `os.replace`, not `os.rename` — the former overwrites on Windows, the latter errors.
- Same filesystem for tmp and target, always. `os.replace` across filesystems is not atomic.
- Use compact JSON (no `indent=`) — smaller file = faster reads + less chance of partial read.
- Write to the **MT5 sandbox** files directory: `<MT5>/MQL5/Files/`. Writing elsewhere means the EA needs absolute paths and `FILE_COMMON` flags.

## 4. Read (MQL5 side)

MT5's native `FileOpen`/`FileReadString` is awkward for JSON. Either parse the small schema by hand, or use a community JSON lib (`JAson.mqh` by Sergeev is the common choice).

### Hand-parse (fine for a small, fixed schema)

```cpp
bool ReadSignal(string &direction, double &confidence, datetime &ts)
{
    int h = FileOpen("trendmaster_signals.json", FILE_READ|FILE_TXT|FILE_ANSI);
    if(h == INVALID_HANDLE) return false;
    string blob = "";
    while(!FileIsEnding(h)) blob += FileReadString(h);
    FileClose(h);

    // Tiny regex-free extractors
    direction  = JsonGetStr(blob, "direction");
    confidence = JsonGetNum(blob, "confidence");
    ts         = (datetime)JsonGetNum(blob, "ts");
    return StringLen(direction) > 0;
}
```

Where `JsonGetStr`/`JsonGetNum` are 10-line helpers that find `"key"`, step past `:`, and capture to the next `,`/`}`. This avoids pulling in a library for a 4-field payload.

### With JAson.mqh

```cpp
#include <JAson.mqh>

CJAVal j;
if(!j.Deserialize(blob)) { DBG("bad json"); return; }
string direction = j["direction"].ToStr();
double conf      = j["confidence"].ToDbl();
datetime ts      = (datetime)j["ts"].ToInt();
```

Use a library the moment the schema has nested arrays (e.g. reading `agents.votes`).

## 5. Staleness check

The EA **must** refuse to trade on an old signal. The brain might be dead, frozen, or behind on ticks.

```cpp
input int InpMaxSignalAgeSec = 10;      // 3s tick + 7s slack

int age = (int)(TimeCurrent() - ts);
if(age > InpMaxSignalAgeSec) {
    DBG(StringFormat("signal stale age=%ds, refuse entry", age));
    return;
}
```

**Clock skew caveat:** `TimeCurrent()` is server time; `ts` is UTC from Python. Some brokers run GMT+2/+3 with DST. Either:

- Have Python write `ts` in the broker's local time (complicates the brain), **or**
- Have MQL5 convert `TimeCurrent()` to UTC (add offset from `TimeTradeServer` - `TimeGMT`).

The second is safer; the first breaks at DST.

## 6. Path resolution

Three legitimate locations for the signal file, in order of preference:

1. **MT5 data folder `Files/`** — `<MT5>/MQL5/Files/trendmaster_signals.json`. Accessible via plain `FileOpen` in MQL5 with no special flags.
2. **MT5 common folder `Common/Files/`** — shared across multiple terminals on the same machine. Use `FILE_COMMON` flag in `FileOpen`.
3. **Absolute path** (not recommended) — requires `FILE_SANDBOX` bypass which MQL5 doesn't grant; only works via DLL import. Avoid.

Python must know which the EA expects. Put it in `config/settings.py`:

```python
SIGNAL_DIR = r"C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\<hash>\MQL5\Files"
SIGNAL_PATH = os.path.join(SIGNAL_DIR, "trendmaster_signals.json")
```

Log the resolved path on brain startup. Path mismatches are the #1 cause of "brain is running, EA sees nothing".

## 7. Debug sidecar

Write a second, verbose file that never gates trading. The EA ignores it; humans read it.

```python
DEBUG_PATH = SIGNAL_PATH.replace(".json", ".debug.json")

debug = {
    "ml_direction":  ml_direction,
    "ml_confidence": ml_confidence,
    "agent_dir":     agent_dir_int,
    "frame_ages":    {tf: age_sec for tf, age_sec in frame_ages.items()},
    "features": {
        "rsi14_h1":  float(feats["rsi14"].iloc[-1]),
        "adx14_h4":  float(adx_h4.iloc[-1]),
        "macd_h_h1": float(feats["macd_h"].iloc[-1]),
    },
    "skipped_reason": "agent_dir_zero" if agent_dir == 0 else None,
}
with open(DEBUG_PATH + ".tmp", "w") as f: json.dump(debug, f, indent=2)
os.replace(DEBUG_PATH + ".tmp", DEBUG_PATH)
```

This file is what `dashboard.py` reads for the diagnostics panel. Keep it out of the hot path (write every N ticks if perf matters).

## 8. Reverse direction (EA → brain)

If the brain ever needs to know what the EA actually did (order filled, SL hit), the EA writes `ea_state.json`:

```json
{
  "ts": 1745327060.1,
  "open_positions": [
    {"ticket": 12345, "side": "BUY", "volume": 0.10,
     "entry": 3240.55, "sl": 3234.20, "tp": 3253.30}
  ],
  "last_trade": {"ticket": 12344, "pnl": 18.40, "closed_ts": 1745326812.9}
}
```

Same atomic-write discipline, same schema-versioning rule. Useful for:

- Dashboard showing live open trades (brain reads → dashboard serves).
- Training labels from real executions (backtest vs. live accuracy).
- Detecting "brain said BUY, EA didn't send" — an ops alert.

## 9. Socket alternative (when you really need latency)

If sub-second latency becomes a real requirement (scalping on tick data), swap the file for a local TCP socket. Python runs the server, EA connects. Keep the same JSON payload over the wire — don't optimise to binary until you've measured.

Caveats:

- MT5 socket API is `SocketCreate/SocketConnect/SocketSend`, WinAPI-style, no async.
- A dropped connection mid-send hangs the EA's `OnTimer`. Guard with `SocketIsReadable` + short timeouts.
- Firewalls on Windows occasionally block localhost sockets randomly.
- Harder to debug than a file. You can't `cat` a socket.

For this project's cadence (bars, not ticks), **files win**.

## 10. Common bridge bugs

- **Brain writing to wrong directory** → log absolute resolved path on startup.
- **EA reading stale file because clock is off** → sync clocks or compute UTC on both sides.
- **`JsonGetStr` returns empty** → JSON uses double quotes, MQL5 strings use double quotes too; ensure proper escaping of the match needle (`"\"direction\""`).
- **EA locks the file on read** → MT5 `FileOpen` without `FILE_SHARE_READ` flag blocks writers. Use `FILE_READ|FILE_SHARE_READ|FILE_SHARE_WRITE`.
- **Python writes BOM by accident** → `open(..., encoding='utf-8-sig')` adds BOM; use `'utf-8'` plain.
- **Schema drift** → brain writes v2 fields; EA built against v1 ignores or crashes. Always write `schema: N`, always check on the EA side.

## 11. Testing the bridge

Two tests worth having:

### 11a. End-to-end smoke

```python
def test_bridge_roundtrip(tmp_path):
    p = tmp_path / "sig.json"
    write_signal(str(p), {"schema": 1, "ts": time.time(),
                          "symbol": "XAUUSD", "direction": "BUY", "confidence": 0.6})
    with open(p) as f: d = json.load(f)
    assert d["direction"] == "BUY"
    assert d["schema"] == 1
```

### 11b. Partial-write safety

```python
def test_concurrent_writer_no_half_read(tmp_path):
    p = tmp_path / "sig.json"
    # spawn 100 writers + 100 readers; reader must never see invalid JSON
    ...
```

If the second test ever fails, `os.replace` is not atomic on the target filesystem — you're probably writing to a network drive. Move to a local drive.

## 12. GitHub references

- `khramkov/Python-MQL5-Expert-Advisor` — socket-based brain↔EA if you want to see the alternative pattern.
- `jimtin/algorithmic_trading_bot` — file-based with a cleaner schema generator.
- `vasyl-synytskyi/MetaTrader5-socket-bridge` — minimal socket reference, 200 LOC total.
- `JAson.mqh` from MQL5 code base — battle-tested JSON parser for anything beyond hand-rolled.

## Extension workflow

Adding a new field:

1. Add it to the Python write_signal payload (optional, with default).
2. **Don't** bump `schema` — additions are backward-compatible.
3. Extend the EA reader to consume it, guarded by a null check.
4. Add a dashboard row so you can see it live.
5. Only after both sides are shipped and stable, consider making it required.

Bumping schema (breaking change):

1. Write new EA build that accepts both `schema=1` and `schema=2`.
2. Deploy EA first, validate it reads old files fine.
3. Switch brain to writing `schema=2`.
4. After a week stable, drop `schema=1` support from EA on next release.

Never flip the brain and EA in the same release — you lose the ability to roll back either side independently.
