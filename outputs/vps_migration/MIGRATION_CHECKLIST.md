# TrendMaster → Free VPS Migration Checklist

## Reality check (read once)
- Stack is **Windows-only** (MT5 terminal + EA + Python brain + executor + dashboard).
- No always-free Windows VPS exists. Best free route = **Octa's own free VPS**
  (check eligibility in your Octa account / Octa Personal Area → VPS section).
- Fallback: any low-cost Windows VPS (~₹400–600/mo) or a 1-month free trial to prove the setup.
- Oracle/AWS free tiers are Linux — **cannot** run MT5. Do not waste time there.

## Phase 1 — Get the server (you)
1. Octa Personal Area → VPS → check free eligibility → activate → note **RDP IP, user, password**.
2. RDP in, install **MetaTrader 5 (Octa build)**, log into the trading account once.
   - If the account is LIVE: expect a confirmation flow; keep 2FA handy.

## Phase 2 — Package locally (me / one command)
3. On this PC, from repo root:
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File outputs\vps_migration\package_stack.ps1
   ```
   → produces `outputs\vps_migration\trendmaster_stack.zip`
   (code + tools + config/.env + EA + startup scripts + brain_state.json).

## Phase 3 — Deploy on VPS
4. Copy the zip into the RDP session (clipboard file copy or redirected drive).
5. Extract, e.g. to `C:\trendmaster\`.
6. Elevated PowerShell in that folder:
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File server_bootstrap.ps1
   ```
   Installs Python 3.11 + .venv + deps, copies the EA into MT5, starts
   brain + dashboard (:8765) + executor + webhook/ngrok, verifies health.
7. In MT5: open the EA in MetaEditor → **Compile** → attach to charts → **AlgoTrading ON**.
8. ngrok: run `ngrok config add-authtoken <token>` once on the VPS
   (token from https://dashboard.ngrok.com) so the TV webhook tunnel works.

## Phase 4 — SAFE CUTOVER (no double trading)
9. Pick a quiet moment. **Stop the LOCAL stack first**:
   `stop_bot.cmd` (and close local MT5 or detach the EA).
10. Verify on the VPS: dashboard :8765 shows brain ALIVE, MT5 OK, signals ticking
    (`logs\trend_master_brain.out` fresh, `find_brain.cmd`).
11. Only then let the VPS trade. Never run local + VPS stacks simultaneously —
    both write signals and both would execute → duplicate positions.

## Phase 5 — Post-migration
- Scheduled tasks/watchdogs: re-run `tools\install_master_autostart_schtask.cmd` on the VPS.
- Keep local copy as cold backup; sync `logs\brain_state.json` occasionally.
- Dashboard is bound to 127.0.0.1 — access via RDP, or re-enable ngrok tunnel if wanted.
- **Security:** the zip contains `config\.env` (Telegram token, API keys). Never
  upload it to a shared drive; transfer only over RDP/private channel.

## Verify commands (on VPS)
- Dashboard: `curl http://localhost:8765/` → 200
- Brain: `check_brain.cmd` / `find_brain.cmd`
- Watchpet: `.venv\Scripts\python.exe tools\watchpet_brain_alive.py` → `[OK] brain alive`
