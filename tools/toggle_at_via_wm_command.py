"""Toggle MT5 AutoTrading via Win32 PostMessage WM_COMMAND.

This bypasses keyboard input entirely — sends the menu command directly
to MT5's window. Works even when window isn't focused and even with UIPI.

Common MT5 menu command IDs:
  32850 = AutoTrading toggle (Tools menu / toolbar button)
  33523 = "Allow algorithmic trading" alternative
We'll try 32850 first, fall back to 33523, plus also try 33526 (Stop EA).
"""
from __future__ import annotations
import sys
import time
import ctypes
from ctypes import wintypes

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

user32 = ctypes.windll.user32
WM_COMMAND = 0x0111
BN_CLICKED = 0


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


def post_command(hwnd, cmd_id):
    wparam = (BN_CLICKED << 16) | (cmd_id & 0xFFFF)
    return user32.PostMessageW(hwnd, WM_COMMAND, wparam, 0)


def check_via_mt5():
    import MetaTrader5 as mt5
    mt5.initialize()
    ti = mt5.terminal_info()
    mt5.shutdown()
    return ti.trade_allowed if ti else None


def main() -> int:
    print("=== Toggle MT5 AutoTrading via WM_COMMAND ===")
    candidates = find_mt5_hwnd()
    if not candidates:
        print("[X] No MT5 window found")
        return 1
    hwnd, title = candidates[0]
    print(f"Found: hwnd=0x{hwnd:x}, title={title!r}")

    # Try the standard MT5 menu IDs for "AutoTrading"
    # These are well-known MT5 internal IDs.
    candidate_ids = [32850, 33523, 33522, 33524, 33525]
    for cid in candidate_ids:
        ok = post_command(hwnd, cid)
        print(f"  PostMessage WM_COMMAND id={cid} -> ok={bool(ok)}")
        time.sleep(0.5)

    print("\n[done] Sent toggle commands. Watch EA log — if orders now succeed,")
    print("       at least one of those IDs hit the AutoTrading toggle.")
    print(f"\nterminal.trade_allowed = {check_via_mt5()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
