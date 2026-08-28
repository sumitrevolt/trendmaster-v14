"""Find the WM_COMMAND id that fixes error 10027.

Strategy: send candidate ID, wait, check EA log for new entry.
If the new entry has 'Order succeeded' or no 10027 → that's the right ID.
"""
from __future__ import annotations
import sys
import time
import ctypes
import os
from ctypes import wintypes
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

user32 = ctypes.windll.user32
WM_COMMAND = 0x0111

LOG_PATH = Path(os.environ["APPDATA"]) / "MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Logs/20260505.log"


def find_mt5_hwnd():
    result = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if "OctaFX" in title or "MetaTrader" in title:
            result.append((hwnd, title))
        return True
    user32.EnumWindows(callback, 0)
    return result


def post(hwnd, cid):
    user32.PostMessageW(hwnd, WM_COMMAND, cid, 0)


def log_size():
    return LOG_PATH.stat().st_size


def has_recent_success():
    """Check if any of the last ~30 log lines indicate order success (no 10027)."""
    try:
        text = LOG_PATH.read_text(errors="replace", encoding="utf-16-le")
    except Exception:
        text = LOG_PATH.read_text(errors="replace")
    lines = text.splitlines()[-50:]
    success_lines = [l for l in lines if "Order success" in l or "deal #" in l.lower() or "OrderSend: done" in l]
    fail_lines = [l for l in lines if "10027" in l or "AutoTrading disabled" in l]
    return success_lines, fail_lines


def main():
    hwnd, title = find_mt5_hwnd()[0]
    print(f"hwnd=0x{hwnd:x}")
    # Wider sweep — many IDs to test (toolbar 488 had a long list)
    candidates = [
        32842, 32850, 32851, 32904, 32908, 32909, 32910, 32911, 32912,
        32848, 32878, 32879, 32905, 32906, 32933, 33522, 33523, 33524,
        33525, 33526, 33527, 33730, 39158, 39159,
        # Range scan around 32850 to find adjacent
        32847, 32849, 32852, 32853, 32854, 32855,
        # Range scan around 33522
        33520, 33521, 33528, 33529, 33530,
    ]
    for cid in candidates:
        print(f"\n--- Test id={cid} ---")
        post(hwnd, cid)
        time.sleep(2.5)  # let MT5 process + EA next OnTimer eval (every 60s; but order attempts come from earlier evals dedupped)
        # Force a fresh signal by resetting the receiver dedup or just wait for the next 60s eval
        # We won't wait for full 60s per id — just check if log changed and check fail/success state
        successes, fails = has_recent_success()
        print(f"  recent success lines: {len(successes)}")
        print(f"  recent 10027 fail lines: {len(fails)}")
        if successes:
            print(f"  *** id={cid} MAY BE THE RIGHT ONE — found success: {successes[-1][:120]}")
            return 0


if __name__ == "__main__":
    sys.exit(main())
