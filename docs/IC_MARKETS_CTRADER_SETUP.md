# IC Markets cTrader dual-broker setup

**Goal:** Every Rocket Prime signal that fires on TradingView triggers a trade on BOTH:
- OctaFX MT5 (existing, via `python_signal_executor.py`)
- IC Markets cTrader (new, via `ctrader_executor.py`)

## Architecture

```
TV Rocket Prime fires
        |
        v
  webhook receiver
        |
        v
  tv_executor.write_tv_signal()
        |
        v
  trendmaster_signals_<SYM>.json  (in MT5 Files dir)
        |
        +-- python_signal_executor.py  ->  OctaFX MT5  (works today)
        |
        +-- ctrader_executor.py        ->  IC Markets cTrader  (NEW)
```

Both executors poll the SAME signal files. Same signal → 2 trades on 2 brokers simultaneously.

## One-time setup (you must do, ~15 min)

### Step 1 — Register an Open API app

1. Go to [https://openapi.ctrader.com/](https://openapi.ctrader.com/) and sign in with your cTID (cTrader ID) — same login you use on cTrader desktop / IC Markets cTrader.
2. Click **"Create New Application"**.
3. Fill: name = "TrendMaster v14", description = "Personal algo trading bridge".
4. Redirect URI: `http://127.0.0.1:8765/ctrader-oauth/callback`  (this matches our local helper)
5. Submit → wait for approval (usually instant for personal apps).
6. Once approved, copy **Client ID** and **Client Secret**.

### Step 2 — Add credentials to `config\.env`

```
CTRADER_CLIENT_ID=<paste here>
CTRADER_CLIENT_SECRET=<paste here>
CTRADER_HOST=live.ctraderapi.com    (or demo.ctraderapi.com if testing)
CTRADER_PORT=5035
```

### Step 3 — Run OAuth flow (one-time)

```cmd
.venv\Scripts\python.exe tools\ctrader_oauth.py
```

This will:
1. Open browser to cTrader's authorize page.
2. You log in + click "Authorize" (grants the app trade permission on your account).
3. Redirect back to `127.0.0.1:8765/ctrader-oauth/callback` — local helper captures the code.
4. Exchange code for `access_token` + `refresh_token` + `account_id`.
5. Append to `config\.env`:

```
CTRADER_ACCESS_TOKEN=<auto-filled>
CTRADER_REFRESH_TOKEN=<auto-filled>
CTRADER_ACCOUNT_ID=<auto-filled>
```

Tokens are valid for ~30 days. Refresh token persists longer; executor auto-renews access token using it.

### Step 4 — Start the cTrader executor

```cmd
.venv\Scripts\python.exe tools\ctrader_executor.py
```

It will:
- Connect to cTrader Open API.
- Authenticate app + account.
- Watch MT5 Files dir for new signals (same files OctaFX executor reads).
- Place orders on IC Markets cTrader for each fresh signal.

Run via VBS launcher for hidden background mode (similar to `python_signal_executor`).

## Verification

```cmd
:: Check executor running
powershell "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*ctrader_executor*' } | Format-Table ProcessId"

:: Check log
type logs\ctrader_executor.log | findstr /v "heartbeat"
```

Look for: `cTrader connected: account=<your_account_id>`. Heartbeat lines confirm polling.

After next Rocket Prime signal: verify TWO new positions open — one on OctaFX (via MT5) AND one on IC Markets cTrader.

## Risk parity (operator policy)

Same `FIXED_LOT_SIZE = 0.01` applies on both brokers. Each signal opens 0.01 lot on OctaFX + 0.01 lot on IC Markets = combined 0.02 lot exposure per signal pair. If you want to halve risk per broker, set FIXED_LOT to 0.005 in both executors' config.

## Killswitch

If you need to stop ONLY the IC Markets side (e.g., spread blew out on cTrader but OctaFX is fine):
```cmd
powershell "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*ctrader_executor*' } | ForEach-Object { taskkill /F /PID $_.ProcessId }"
```

OctaFX continues unaffected. Watchdogs may auto-respawn — disable the schtask too if you want it permanently off.
