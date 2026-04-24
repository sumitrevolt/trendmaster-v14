---
name: trading-deploy-monitor
description: "Deployment and monitoring for an MT5 + Python trading stack. Use when containerizing the Python brain, running MT5 on Linux via Wine+Docker, wrapping the brain as a Windows service, adding Prometheus/Grafana metrics, sending Telegram/Discord alerts on fills or errors, rotating logs, and exposing the dashboard safely via tailscale/ngrok. Covers the gap between 'it runs on my machine' and '24/7 unattended'."
---

# trading-deploy-monitor

A trading bot that only runs when you're at your desk isn't a trading bot — it's a toy. This skill covers the operational glue needed to run the stack 24/7: containerization, service wrapping, metrics, alerts, log hygiene, and safe remote access.

Patterns are distilled from `finautica/metatrader5-docker`, `gmag11/MetaTrader5-Docker`, `slowfound/metatrader5-quant-server-python` (MT5+VNC+Flask in Docker), and freqtrade's production deployment playbook.

## When to use

- Moving the bot from your laptop to a VPS / home server for 24/7 operation.
- Running MT5 on Linux via Wine (native MT5 is Windows-only).
- Adding Prometheus metrics and Grafana dashboards.
- Wiring Telegram / Discord alerts on fills, errors, daily kill-switch trips.
- Setting up log rotation so disks don't fill up.
- Exposing the dashboard to your phone via tailscale or ngrok.

## 1. Deployment topology — three viable shapes

| Topology | Pros | Cons | When |
|---|---|---|---|
| **A. All on Windows** | MT5 native, simple | Single point of failure; no native container tooling | This project's current state; fine for retail |
| **B. MT5 on Windows, brain in Docker on Linux** | Brain restarts cleanly, easy scaling | Cross-host bridge file needs a shared location (SMB/Syncthing) | Best for a team or home-lab |
| **C. MT5 in Docker (Wine) + brain in Docker** | Fully Linux; cloud-deployable | Wine flakiness, VNC overhead, slightly slower tick processing | VPS deployment |

Start with A. Move to B when you need the brain's reliability decoupled from MT5. Only go to C if you genuinely need Linux-native (e.g. cheap VPS), and be ready to debug Wine.

## 2. Topology A — Windows-native (this project)

### Python brain as a scheduled task

Instead of running `pythonw` from a shell, register as a Windows scheduled task so it auto-starts on boot and relaunches on failure.

```powershell
# run once as admin
$action  = New-ScheduledTaskAction -Execute "pythonw.exe" `
           -Argument "C:\...\ai_trading_agents\trend_master_brain.py"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "trendmaster-brain" -Action $action `
                       -Trigger $trigger -Settings $settings -User "SYSTEM"
```

### MT5 auto-start on Windows login

MT5 already supports this natively: right-click the MT5 shortcut → `Send to → Desktop` → `Windows + R` → `shell:startup` → drop the shortcut in. Done.

### Windows service via NSSM (more robust)

For truly unattended operation — survives RDP disconnects, user profile reloads — wrap `pythonw` as a service with NSSM (the Non-Sucking Service Manager):

```powershell
# one-time install
nssm install trendmaster-brain pythonw.exe "C:\...\trend_master_brain.py"
nssm set    trendmaster-brain AppDirectory "C:\...\"
nssm set    trendmaster-brain AppStdout    "C:\...\logs\brain.out"
nssm set    trendmaster-brain AppStderr    "C:\...\logs\brain.err"
nssm set    trendmaster-brain AppRotateFiles 1
nssm set    trendmaster-brain AppRotateBytes 5242880
nssm start  trendmaster-brain
```

Repeat for the dashboard. NSSM handles restart-on-crash, log rotation, and clean shutdowns — all the things a batch-start-loop fakes badly.

## 3. Topology C — Docker for MT5

If you want MT5 in a container (Linux / VPS), the reference patterns are:

### finautica/metatrader5-docker

Base image is Debian + Wine + MT5. Mount a volume for MT5's `MQL5/` folder so the EA, signal files, and logs survive container rebuilds. Expose KasmVNC on a port for remote chart access.

```yaml
# docker-compose.yml (simplified)
services:
  mt5:
    image: finautica/metatrader5-docker:latest
    container_name: mt5
    ports:
      - "127.0.0.1:6901:6901"     # KasmVNC web
      - "127.0.0.1:18812:18812"   # rpyc bridge (optional)
    volumes:
      - ./mt5/config:/config:rw                 # terminal.ini, profile
      - ./mt5/MQL5:/mt5/MQL5:rw                 # EAs + Files/
      - /etc/localtime:/etc/localtime:ro
    environment:
      VNC_PW: "${VNC_PW}"
    restart: unless-stopped
```

### gmag11/MetaTrader5-Docker

Alternative, lighter image with VNC web server. Simpler but less configurable.

### slowfound/metatrader5-quant-server-python

MT5 + VNC + a Flask API in one container. Read this one for how to expose the MT5 Python bridge over HTTP — useful if your brain runs on a different host.

### Brain container

```dockerfile
# Dockerfile.brain
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ai_trading_agents ./ai_trading_agents
COPY config ./config
COPY tools ./tools
CMD ["python", "-u", "ai_trading_agents/trend_master_brain.py"]
```

```yaml
# docker-compose.yml (brain + dashboard sidecar)
services:
  brain:
    build: { context: ., dockerfile: Dockerfile.brain }
    volumes:
      - ./mt5/MQL5/Files:/mt5files:rw        # shared signal/debug files
    environment:
      MT5_HOST: mt5
      SIGNAL_PATH: /mt5files/trendmaster_signals.json
    depends_on: [mt5]
    restart: unless-stopped

  dashboard:
    build: { context: ., dockerfile: Dockerfile.dashboard }
    ports: ["127.0.0.1:8000:8000"]
    volumes:
      - ./mt5/MQL5/Files:/mt5files:ro
    restart: unless-stopped
```

**Wine gotchas:**

- MT5 ticks are slower inside Wine — ~5-10% CPU overhead per chart.
- Some MT5 indicators with complex DLL calls fail silently. Stick to built-ins.
- Fonts in VNC look atrocious without `fonts-liberation` in the Dockerfile.
- Terminal may refuse to connect on first boot until you manually log in once via VNC. Automate with `expect` or VNC macro if possible.

## 4. Metrics — Prometheus

Emit structured metrics from the brain. A minimal setup:

```python
# brain — expose /metrics
from prometheus_client import Counter, Gauge, start_http_server

signals_written   = Counter("brain_signals_total", "Signals written", ["direction"])
agent_vote_gauge  = Gauge("brain_agent_vote", "Vote per agent", ["agent"])
tick_latency_ms   = Gauge("brain_tick_latency_ms", "Latency of tick_once in ms")
mt5_connected     = Gauge("brain_mt5_connected", "1 if MT5 session up")

start_http_server(9100)   # scraped by Prometheus

# in tick_once:
signals_written.labels(direction=final_dir).inc()
for v in agent_votes:
    agent_vote_gauge.labels(agent=v.name).set(v.vote)
```

**Prometheus scrape config:**

```yaml
scrape_configs:
  - job_name: trendmaster-brain
    scrape_interval: 5s
    static_configs:
      - targets: ["brain:9100"]
```

### Useful dashboards in Grafana

Four panels cover 90% of day-to-day ops:

1. **Signal age** (from `(time() - max_over_time(brain_signal_last_write_ts[1m]))`) — alerts when > 15 s.
2. **Agent votes over time** — a stacked area chart showing each agent's vote; visual "why isn't it trading".
3. **Equity curve** — scrape MT5 account equity via a sidecar and plot as a line.
4. **Trade outcomes** — bar chart of PnL per trade, colored by win/loss.

### Prom alertmanager rules

```yaml
groups:
  - name: trading
    rules:
      - alert: BrainStale
        expr: (time() - brain_last_tick_ts) > 20
        for: 1m
        labels: { severity: critical }
        annotations:
          summary: "Brain hasn't ticked in 20+s on {{ $labels.instance }}"

      - alert: MT5Disconnected
        expr: brain_mt5_connected == 0
        for: 30s
        labels: { severity: critical }

      - alert: DailyKillSwitchTripped
        expr: ea_daily_kill == 1
        labels: { severity: warning }
```

Hook these to Telegram or Discord via alertmanager webhook — see §5.

## 5. Alerts — Telegram / Discord

Both are equivalently easy; pick one based on where your notifications already live.

### Telegram (BotFather)

```python
import requests
TG_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_CHAT  = os.environ["TG_CHAT_ID"]

def tg_send(msg: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as e:
        log.warning("tg send failed: %s", e)
```

Use from the brain on: crash, MT5 disconnect, daily kill-switch trip. Keep it spartan — one line per alert, no retries, never block the trading loop on a failed send.

### Discord webhook

```python
DISCORD_URL = os.environ["DISCORD_WEBHOOK_URL"]

def discord_send(msg: str):
    try: requests.post(DISCORD_URL, json={"content": msg}, timeout=5)
    except Exception: pass
```

### What to alert on (and what NOT)

**Do alert:**

- Brain crashed / failed to restart
- MT5 session disconnected > 30 s
- Daily kill-switch tripped
- Spread > 10× normal for > 5 min (market conditions bad)
- Disk > 90% full on the host
- New trade opened / closed (optional — can be noisy)

**Don't alert:**

- Every tick
- Missed signals (they happen)
- Agent disagreements (that's normal operation)

A bot that pings you every 3 seconds gets muted, and muted alerts are worse than none.

## 6. Log hygiene

Three rules:

1. **Rotate**. Use `RotatingFileHandler` in Python, NSSM's AppRotate in Windows, `logrotate` on Linux. 5 MB × 7 files is plenty.
2. **Separate**. `brain.log` (decisions), `brain.err` (exceptions), `orders.log` (order-send results) — three files, grep-friendly.
3. **Structured where it matters**. JSON lines for anything a dashboard consumes:

```python
import json, time, logging
class JsonFmt(logging.Formatter):
    def format(self, r):
        return json.dumps({"ts": time.time(), "lvl": r.levelname,
                           "msg": r.getMessage(), "logger": r.name})
```

**Never** log account passwords, full tokens, or full order payloads with sensitive fields. Use a redactor or a whitelist.

## 7. Remote access — safely

You'll want to check the dashboard from your phone. Options, safest first:

### tailscale (recommended)

Zero-config mesh VPN. Install on your host and your phone; the dashboard at `http://100.x.x.x:8000/` is reachable only from devices you've added to your tailnet. No ports exposed to the public internet.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### Cloudflare tunnel

Runs a binary that outbound-connects to Cloudflare, giving you a `https://trendmaster.<your-domain>.com` URL with optional access control. No inbound ports. Requires a domain on Cloudflare.

### ngrok (quick, less safe)

`ngrok http 8000` gives you a public URL instantly. Free tier changes the URL every restart; paid tier has stable URLs + basic auth. **Always enable basic auth** — public tunnels to a trading dashboard advertise your balance.

### Never

- Port-forward `8000` from your router without auth.
- Bind FastAPI to `0.0.0.0` unless behind tailscale/tunnel.
- Store credentials in the dashboard HTML or query strings.

## 8. Credentials & secrets

Keep MT5 login, API tokens, webhook URLs out of the code tree.

- **Development:** `.env` file + `python-dotenv`, git-ignored.
- **Docker:** pass via `environment:` from compose + a `.env` file outside the repo.
- **Windows service:** set per-service env with `nssm set <name> AppEnvironmentExtra`.
- **Production on a VPS:** a proper secrets manager (Doppler, 1Password CLI, HashiCorp Vault) if the bot has real money.

Never commit `.env`. Rotate broker passwords after ANY machine loss / re-install.

## 9. Backup & disaster recovery

State to back up:
- `trend_master_brain.log` and `brain.err` (for postmortems)
- Any trained model files (`*.pkl`)
- `config/` directory
- MT5's `profiles/default/symbols.raw` and `default.tpl` (chart state)
- A snapshot of `MQL5/Files/trendmaster_signals.json` if you need to replay decisions

State NOT worth backing up:
- `Tester/` cache, `.hst` files — easy to regenerate
- `Logs/` older than a month — rotated out anyway

Test the restore on a fresh machine once per quarter. Untested backups are half a backup.

## 10. Common ops gotchas

- **Wine in Docker + news filter that calls HTTPS** → the MT5 side of WebRequest fails with "invalid certificate" unless you mount `/etc/ssl/certs/` from the host. Alternative: do the fetch in the Python brain and write results to a file the EA reads.
- **Prometheus scraping over tailscale** → works; bind `start_http_server(9100)` to `0.0.0.0` (or explicit `100.x.x.x`) and add the target to Prom.
- **Docker container time skew** → cron-sync NTP inside the container, or mount `/etc/localtime`. Drift > 1 s makes signal staleness checks misfire.
- **Grafana dashboard loading balance shows $0.00** → MT5 Python bridge not connected from inside the container; expose via rpyc on port 18812 (see slowfound's repo).
- **NSSM restart loop on brain crashing at startup** → MT5 not running yet. Add a `DependsOn` in NSSM config pointing at MT5.

## 11. GitHub references

- `finautica/metatrader5-docker` — Debian + Wine + MT5 + KasmVNC; current reference Docker image.
- `gmag11/MetaTrader5-Docker` — lighter alternative, VNC-only.
- `slowfound/metatrader5-quant-server-python` — full MT5+VNC+Flask API stack; good production pattern.
- `bahadirumutiscimen/silicon-metatrader5` — macOS Apple Silicon + Docker; useful if your dev machine is a Mac.
- `jimtin/python_trading_bot` — simple reference for Telegram alerts + MT5 bridge.
- `freqtrade/freqtrade` docs → "Installation → Docker" section for a canonical compose layout.

## Extension workflow

Adding a new metric:

1. Define in `metrics.py` alongside existing ones. Label by agent/symbol/TF consistently.
2. Export via `prometheus_client` on port 9100.
3. Add a Grafana panel (save the dashboard as JSON, commit it).
4. Add an alertmanager rule if the metric warrants paging.

Adding a new alert channel:

1. Wrap in a `notify_<channel>(msg)` helper that swallows errors.
2. Route from a central `notify()` dispatcher so you don't sprinkle `requests.post` throughout the code.
3. Add a kill switch env var (`DISABLE_ALERTS=1`) for use during maintenance.

Moving from Windows to Linux:

1. Start with brain-in-Docker on the same Windows box (topology B) — the brain is pure Python, works identically.
2. Validate for a week.
3. Then attempt MT5-in-Wine-in-Docker (topology C) on a test VPS; keep production on Windows until the VPS instance has ticked reliably for a month.
