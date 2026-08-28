"""cTrader Open API — OAuth2 helper.

Run ONCE after registering an Open API app at openapi.ctrader.com.

Flow:
  1. Open browser to cTrader's auth page (with Client ID + redirect URI).
  2. Operator logs in + clicks Authorize.
  3. cTrader redirects to http://127.0.0.1:8765/ctrader-oauth/callback?code=XXX
  4. Local handler captures `code`.
  5. Exchange `code` for access_token + refresh_token via POST /apps/token.
  6. Discover account_id (first IC Markets cTrader account).
  7. Append to config\\.env.

Reads from config\\.env:
  CTRADER_CLIENT_ID
  CTRADER_CLIENT_SECRET

Writes to config\\.env:
  CTRADER_ACCESS_TOKEN
  CTRADER_REFRESH_TOKEN
  CTRADER_ACCOUNT_ID
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "config" / ".env"

REDIRECT = "http://127.0.0.1:8766/ctrader-oauth/callback"   # 8766 to avoid clashing with dashboard 8765
SCOPES = "trading"
AUTH_URL = "https://openapi.ctrader.com/apps/auth"
TOKEN_URL = "https://openapi.ctrader.com/apps/token"


def _load_env():
    if not ENV.exists():
        print(f"FATAL: {ENV} missing")
        sys.exit(1)
    out = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _append_env(updates: dict):
    """Append new KEY=VALUE lines, replacing existing if present."""
    if not ENV.exists():
        ENV.write_text("")
    text = ENV.read_text(encoding="utf-8")
    for k, v in updates.items():
        line = f"{k}={v}"
        if f"{k}=" in text:
            # replace existing line
            new_lines = []
            for ln in text.splitlines():
                if ln.startswith(f"{k}="):
                    new_lines.append(line)
                else:
                    new_lines.append(ln)
            text = "\n".join(new_lines)
        else:
            if not text.endswith("\n"):
                text += "\n"
            text += f"# cTrader Open API token (added {time.strftime('%Y-%m-%d %H:%M:%S')})\n{line}\n"
    ENV.write_text(text, encoding="utf-8")


# Capture the auth code via a tiny one-shot HTTP server
_captured_code = {"value": None}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/ctrader-oauth/callback"):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            _captured_code["value"] = (qs.get("code") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:Arial;text-align:center;padding:40px'>"
                b"<h2>cTrader auth captured.</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args, **kwargs):  # silence default logging
        pass


def main() -> int:
    env = _load_env()
    cid = env.get("CTRADER_CLIENT_ID", "").strip()
    csec = env.get("CTRADER_CLIENT_SECRET", "").strip()
    if not cid or not csec:
        print("FATAL: CTRADER_CLIENT_ID / CTRADER_CLIENT_SECRET missing in config/.env")
        print("       Register an app at https://openapi.ctrader.com/ first.")
        return 1

    # Spawn local HTTP server to catch redirect
    srv = HTTPServer(("127.0.0.1", 8766), _Handler)
    Thread(target=srv.serve_forever, daemon=True).start()
    print("[OK] Local callback server up on 127.0.0.1:8766")

    # Open browser to auth page
    auth_qs = urllib.parse.urlencode({
        "client_id": cid,
        "redirect_uri": REDIRECT,
        "scope": SCOPES,
    })
    url = f"{AUTH_URL}?{auth_qs}"
    print(f"\nOpening browser:\n  {url}\n")
    webbrowser.open(url)
    print("Sign in to cTrader if prompted, then click 'Authorize'.")
    print("Waiting for redirect...")

    # Wait up to 5 min
    for _ in range(300):
        if _captured_code["value"]:
            break
        time.sleep(1)
    code = _captured_code["value"]
    srv.shutdown()
    if not code:
        print("[X] Timeout waiting for auth code.")
        return 2
    print(f"[OK] code captured: {code[:20]}...")

    # Exchange code for tokens
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": cid,
        "client_secret": csec,
    }).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            tok = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[X] Token exchange failed: {e}")
        return 3

    access = tok.get("accessToken") or tok.get("access_token")
    refresh = tok.get("refreshToken") or tok.get("refresh_token")
    if not access:
        print(f"[X] No accessToken in response: {tok}")
        return 4
    print(f"[OK] access_token: {access[:18]}... (length {len(access)})")
    print(f"[OK] refresh_token: {refresh[:18]}... (length {len(refresh)})" if refresh else "[!] no refresh_token")

    # Persist
    updates = {"CTRADER_ACCESS_TOKEN": access}
    if refresh:
        updates["CTRADER_REFRESH_TOKEN"] = refresh
    _append_env(updates)
    print(f"[OK] Wrote tokens to {ENV}")

    print("\nNext step: discover your IC Markets cTrader account_id.")
    print("Run:  .venv\\Scripts\\python.exe tools\\ctrader_executor.py --discover-accounts")
    print("That will list your linked accounts; pick the IC Markets one and add to .env.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
