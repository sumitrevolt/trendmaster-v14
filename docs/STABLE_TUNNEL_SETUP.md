# Stable tunnel setup — replace the rotating quick URL

**Why this exists:** Cloudflare quick tunnels (`cloudflared tunnel --url ...`) get a fresh random `https://<random>.trycloudflare.com` URL every time `cloudflared.exe` restarts. The watchdog restarts it on every outage. Every restart **breaks all 76 TradingView alerts** because their webhook URL is hardcoded to the old random hostname. You need to manually re-paste the new URL into 76 alerts every time.

This document fixes that. After setup, you have one URL like `https://trader-sumit.ngrok-free.app/tv-signal` (or your own domain) that **never changes**, even across reboots.

Three paths, pick one:

| Path | Cost | URL form | Best for |
|---|---|---|---|
| **0 (FREE)** — ngrok free static domain | $0 | `xxxxx.ngrok-free.app` | Just want it stable now, no spend |
| **A** — Cloudflare named tunnel | ~$10/yr (domain) | `tv.trader.yourdomain.com` | Long-term, own your URL |
| **B** — ngrok paid plan | ~$8/mo | reserved subdomain | Don't want a domain, want unlimited bandwidth |

**Recommendation:** start with Path 0 (free, 5 minutes). If you outgrow ngrok-free's quota or want your own domain later, migrate to Path A — the rest of the system (launcher / watchdog / verifier) doesn't care which mode you're in, just flip `TUNNEL_MODE` in `.env`.

---

## Path 0 — ngrok free static domain (FREE, recommended for fast start)

### Cost & limits

* **$0**. ngrok's free tier (since 2024) gives every account **1 reserved static domain** like `your-name.ngrok-free.app`.
* Free-tier limits to be aware of:
  * 1 active tunnel at a time
  * Bandwidth fair-use (well above what 76 webhook alerts/day will ever need)
  * Some IP-block restrictions (rarely an issue from TradingView)

### Setup (5 minutes)

#### 1. Sign up

Go to <https://dashboard.ngrok.com/signup> — free, email + password. No card required.

#### 2. Install ngrok

```cmd
winget install ngrok.ngrok
```

If `winget` not available, download from <https://ngrok.com/download> and place `ngrok.exe` in `tools\` next to `cloudflared.exe`.

#### 3. Add your authtoken

From `dashboard.ngrok.com → Your Authtoken`, copy the value, then:

```cmd
ngrok config add-authtoken <PASTE_TOKEN_HERE>
```

#### 4. Claim a static domain

`dashboard.ngrok.com → Universal Gateway → Domains → + New Domain`. Pick any name (e.g. `trader-sumit.ngrok-free.app`). It's yours forever (or until you delete it).

#### 5. Add to `config/.env`

```
TUNNEL_MODE=ngrok
NGROK_DOMAIN=trader-sumit.ngrok-free.app
TV_PUBLIC_URL=https://trader-sumit.ngrok-free.app
```

#### 6. Bring it up

```cmd
start_tv_webhook.cmd
```

The launcher reads `TUNNEL_MODE=ngrok` and runs `ngrok http 5005 --domain=trader-sumit.ngrok-free.app` instead of the cloudflared path. The watchdog pings `TV_PUBLIC_URL/health` every 5 min.

#### 7. Update TradingView alerts (one-time)

Replace all 76 alert webhook URLs with:

```
https://trader-sumit.ngrok-free.app/tv-signal
```

This URL is yours permanently. Watchdog can restart ngrok 100 times — alerts keep working.

### Verify

```cmd
.venv\Scripts\python.exe tools\verify_tv_pipeline.py
```

Should show:
* `Public:  https://trader-sumit.ngrok-free.app`
* `[OK] Public /health  (status=200)`

---

## Path A — Cloudflare named tunnel (your own domain)

### Cost & requirements

* A domain you control: ~$8–12/year. Easiest source is **Cloudflare Registrar** itself (`dash.cloudflare.com → Domain Registration`) — at-cost pricing, automatically uses Cloudflare DNS.
* That's it. The tunnel itself is **free** for personal use; you just need a domain because Cloudflare uses your DNS to route the public hostname to the tunnel.

### Why it works

A Cloudflare *named* tunnel is identified by a UUID, not a URL. You point a DNS hostname (e.g. `tv.trader.yourdomain.com`) at that UUID via a CNAME-like record. Cloudflare routes any request hitting that hostname through the tunnel to your local `127.0.0.1:5005`. The hostname is yours; it never rotates.

### One-time setup

```cmd
cd /d "C:\Users\Ratanshila\Documents\autmated trading"

REM 1. Auth cloudflared with your Cloudflare account.
REM    Browser pops; pick the zone for the domain you want to use.
tools\cloudflared.exe tunnel login
```

This drops a credentials file at `C:\Users\Ratanshila\.cloudflared\cert.pem`.

```cmd
REM 2. Create a named tunnel. Pick any name you like.
tools\cloudflared.exe tunnel create trendmaster-tv
```

Output looks like:
```
Created tunnel trendmaster-tv with id 8e2c4d... (UUID)
Tunnel credentials written to C:\Users\Ratanshila\.cloudflared\<UUID>.json
```

**Copy the UUID** — you need it in step 3 and the .env.

```cmd
REM 3. Route a hostname to the tunnel.
REM    Replace tv.trader.yourdomain.com with whatever subdomain you want
REM    on a domain you've added to Cloudflare DNS.
tools\cloudflared.exe tunnel route dns trendmaster-tv tv.trader.yourdomain.com
```

Cloudflare creates the DNS record automatically. Verify in `dash.cloudflare.com → DNS → Records` — you should see a CNAME for `tv.trader.yourdomain.com` → `<UUID>.cfargotunnel.com`.

### Config file

Create `config/cloudflared.yml` (the launcher reads this):

```yaml
# config/cloudflared.yml
tunnel: <PASTE_YOUR_UUID_HERE>
credentials-file: C:\Users\Ratanshila\.cloudflared\<UUID>.json

ingress:
  - hostname: tv.trader.yourdomain.com
    service: http://127.0.0.1:5005
  - service: http_status:404
```

### Add to `config/.env`

```
TUNNEL_MODE=named
TV_PUBLIC_URL=https://tv.trader.yourdomain.com
CLOUDFLARED_CONFIG=config/cloudflared.yml
```

### Bring it up

```cmd
start_tv_webhook.cmd
```

The launcher reads `TUNNEL_MODE=named` and starts `cloudflared.exe tunnel --config config\cloudflared.yml run` instead of the quick-tunnel path. The watchdog pings `TV_PUBLIC_URL/health` instead of trying to scrape a URL out of the err log.

### Update your TradingView alerts (one-time)

Once. Forever. Replace whatever quick-tunnel URL you had in all 76 alerts with:

```
https://tv.trader.yourdomain.com/tv-signal
```

Any future receiver / cloudflared restart leaves this URL unchanged. The watchdog can restart `cloudflared.exe` 50 times a day and your TV alerts keep working.

### Verify

```cmd
.venv\Scripts\python.exe tools\verify_tv_pipeline.py
```

Look for:
* `Public:  https://tv.trader.yourdomain.com`
* `[OK] Public /health  (status=200)`

---

## Path B — ngrok paid plan (alternative)

If you don't want to deal with a domain.

### Cost

* ngrok personal plan: ~$8/mo (gives you 1 reserved domain)
* Or "static domain" addon on free tier — depends on current ngrok pricing; check `ngrok.com/pricing`

### Setup

1. Sign up at ngrok.com, paid plan, claim a reserved domain like `trader-sumit.ngrok.app`.
2. Install ngrok: `winget install ngrok.ngrok` (or download to `tools\ngrok.exe`).
3. Auth: `ngrok config add-authtoken <token from ngrok dashboard>`
4. Add to `config/.env`:
   ```
   TUNNEL_MODE=ngrok
   TV_PUBLIC_URL=https://trader-sumit.ngrok.app
   NGROK_DOMAIN=trader-sumit.ngrok.app
   ```
5. The launcher will run `ngrok http 5005 --domain=trader-sumit.ngrok.app` instead of cloudflared.

### Trade-offs vs Cloudflare named tunnel

| | Cloudflare named | ngrok paid |
|---|---|---|
| Cost | ~$10/yr (domain) | ~$96/yr ($8/mo) |
| URL stability | Permanent (your domain) | Permanent (reserved subdomain) |
| Bandwidth limit | Effectively none | 5 GB/mo on $8 plan |
| Setup complexity | Higher (domain + DNS + tunnel) | Lower |
| Lock-in | None (it's your domain) | ngrok subdomain |

For a trading bot that runs 24/7, Cloudflare wins long-term on cost and sovereignty. ngrok wins on first-day convenience.

---

## Troubleshooting

### "tunnel credentials file not found"
Path in `config/cloudflared.yml::credentials-file` doesn't match where `cloudflared tunnel create` wrote it. Re-check `C:\Users\Ratanshila\.cloudflared\` for the `<UUID>.json` file and update the YAML.

### "no such host" when curl-ing the public URL
DNS hasn't propagated yet (takes <5 min for Cloudflare-managed domains). Wait a couple of minutes. If still failing after 10 min: `dash.cloudflare.com → DNS → Records`, confirm the CNAME exists with **proxy status orange (proxied)**. If it's grey (DNS-only), tunnel won't route — toggle to orange.

### "502 Bad Gateway" from public URL
Tunnel is up but `127.0.0.1:5005` isn't responding. Receiver is dead. Run `tools\verify_tv_pipeline.py` to diagnose; restart with `start_tv_webhook.cmd` if needed.

### Want to delete the named tunnel and start over

```cmd
tools\cloudflared.exe tunnel delete trendmaster-tv
REM Then re-run the create + route + config.yml steps above with a new name.
```

---

## Rollback to quick tunnel

If a named tunnel becomes problematic (rare), comment out `TUNNEL_MODE=named` in `config/.env` (or set `TUNNEL_MODE=quick`) and restart `start_tv_webhook.cmd`. Behaviour reverts to the original rotating-URL quick tunnel, you re-paste a fresh URL into your TV alerts as before.
