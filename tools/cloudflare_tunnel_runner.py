"""Cloudflare Tunnel runner — replaces ngrok-free as the public webhook
exposure layer. Two reasons it's better:
  1. Cloudflare's free tier doesn't have the 2-hour auto-disconnect that
     ngrok-free.dev's reserved domains suffer.
  2. Named tunnels keep the SAME hostname forever — no need to re-paste
     URLs into TradingView alerts after every restart.

This runner is invoked by start_tv_webhook.cmd when TUNNEL_MODE=cloudflare.

Operator first-time setup (one-time, ~3 min):
  1. Run outputs/install_cloudflared.cmd
  2. cloudflared tunnel login            (browser auth, accept any free domain)
  3. cloudflared tunnel create trendmaster
  4. Note the UUID printed; paste into config/.env as CLOUDFLARE_TUNNEL_UUID
  5. cloudflared tunnel route dns trendmaster bot-tv.<your-cf-domain>
     OR use the operator's existing CF domain
  6. Set CLOUDFLARE_HOSTNAME in .env to the routed name

After that, this script:
  - Reads CLOUDFLARE_TUNNEL_UUID + CLOUDFLARE_HOSTNAME from env
  - Writes a config.yml in %USERPROFILE%/.cloudflared/
  - Spawns `cloudflared tunnel run <uuid>` and stays alive
  - Watchdog (health_watchdog.py) monitors it
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path.home() / ".cloudflared"


def find_cloudflared() -> Path | None:
    """Look for cloudflared.exe in common install paths."""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" /
            "Packages" / "Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe" /
            "cloudflared.exe",
        ROOT / "tools" / "cloudflared.exe",
        Path("C:/Program Files (x86)/cloudflared/cloudflared.exe"),
        Path("C:/Program Files/cloudflared/cloudflared.exe"),
    ]
    # Also scan PATH
    path_dirs = (os.environ.get("PATH") or "").split(os.pathsep)
    for d in path_dirs:
        candidates.append(Path(d) / "cloudflared.exe")
    # winget glob fallback
    winget_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_root.exists():
        for sub in winget_root.glob("Cloudflare.cloudflared_*"):
            candidates.append(sub / "cloudflared.exe")

    for c in candidates:
        try:
            if c.is_file():
                return c
        except Exception:
            continue
    return None


def write_config(uuid: str, hostname: str, local_port: int = 5005) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cred = CONFIG_DIR / f"{uuid}.json"
    cfg = CONFIG_DIR / "config.yml"
    cfg.write_text(f"""# trendmaster cloudflare tunnel config
tunnel: {uuid}
credentials-file: {cred}

ingress:
  - hostname: {hostname}
    service: http://localhost:{local_port}
  - service: http_status:404
""", encoding="utf-8")
    return cfg


def main() -> int:
    # Load .env
    env_file = ROOT / "config" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    uuid = os.environ.get("CLOUDFLARE_TUNNEL_UUID", "").strip()
    hostname = os.environ.get("CLOUDFLARE_HOSTNAME", "").strip()
    local_port = int(os.environ.get("TV_WEBHOOK_PORT", "5005"))

    cf = find_cloudflared()
    if not cf:
        print("[X] cloudflared.exe not found.")
        print("    Run: outputs/install_cloudflared.cmd  (winget install Cloudflare.cloudflared)")
        return 2

    print(f"[OK] cloudflared: {cf}")

    # Mode selection: NAMED tunnel (preferred) or QUICK tunnel (fallback)
    if uuid and hostname:
        print(f"[OK] named tunnel: {hostname} (uuid={uuid[:8]}...)")
        cfg = write_config(uuid, hostname, local_port)
        print(f"[OK] wrote config: {cfg}")
        cmd = [str(cf), "tunnel", "--config", str(cfg), "run", uuid]
    else:
        print("[INFO] no CLOUDFLARE_TUNNEL_UUID + CLOUDFLARE_HOSTNAME — falling back to quick tunnel")
        print("       URL will rotate on restart. Run install_cloudflared.cmd → setup_named_tunnel.cmd")
        print("       to migrate to a stable hostname.")
        cmd = [str(cf), "tunnel", "--url", f"http://localhost:{local_port}"]

    log_path = ROOT / "logs" / "cloudflare_tunnel.log"
    print(f"[OK] log: {log_path}")
    print(f"[OK] launching: {' '.join(cmd)}")

    with open(log_path, "ab", buffering=0) as logf:
        proc = subprocess.Popen(
            cmd, stdout=logf, stderr=subprocess.STDOUT,
            cwd=str(ROOT)
        )
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            return 0
    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
