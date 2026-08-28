"""RETIRED 2026-08-22 — merged into tools/dashboard_server.py (single source of truth).

Canonical dashboard: http://localhost:8765  (System tab = former mission view)
Original preserved at archive/old_dashboards/mission_control.py.
This stub keeps old bookmarks alive: :8001 -> :8765
"""
from __future__ import annotations

import http.server
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
TARGET = "http://127.0.0.1:8765/"


class Redirect(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", TARGET)
        self.end_headers()

    do_POST = do_GET

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"[stub] mission_control retired -> redirecting :{PORT} -> {TARGET}")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Redirect).serve_forever()
