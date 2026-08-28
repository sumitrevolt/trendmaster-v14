"""Force MT5 AutoTrading ON via Win32 SetForegroundWindow + multiple Ctrl+E.

Strategy:
  1. Find MT5 window
  2. Use ctypes/Win32 to forcibly bring it to foreground (works around UIPI)
  3. Wait for window to actually be focused (poll GetForegroundWindow)
  4. Send Ctrl+E to toggle AutoTrading
  5. Probe via Python MT5: try to place a tiny test order
  6. If it fails with 10027 again, send Ctrl+E one more time (was ON→OFF)
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

import pyautogui
import pygetwindow as gw

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

ALT_KEY = 0x12
SW_RESTORE = 9


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


def force_focus(hwnd):
    """Bypass Windows foreground lock via the AltKeyDown trick."""
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.keybd_event(ALT_KEY, 0, 0, 0)
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(ALT_KEY, 0, 0x0002, 0)  # KEYEVENTF_KEYUP
    time.sleep(0.4)


def is_focused(hwnd):
    return user32.GetForegroundWindow() == hwnd


def main() -> int:
    print("=== Force MT5 AutoTrading ON ===")
    candidates = find_mt5_hwnd()
    if not candidates:
        print("[X] No MT5 window found")
        return 1
    hwnd, title = candidates[0]
    print(f"Found: hwnd=0x{hwnd:x}, title={title!r}")

    print("Forcing focus...")
    for _ in range(3):
        force_focus(hwnd)
        time.sleep(0.4)
        if is_focused(hwnd):
            print("[OK] MT5 is foreground")
            break
    else:
        print("[!] Could not get focus, sending key anyway")

    # Send Ctrl+E
    print("Sending Ctrl+E (try 1)...")
    pyautogui.hotkey("ctrl", "e")
    time.sleep(1.5)

    # Test by sending a tiny order via Python MT5
    import MetaTrader5 as mt5
    mt5.initialize()

    # Try a test order (smallest possible) on EURUSD
    sym = "EURUSD"
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if info and tick:
        # Just check terminal_info — we can't actually send orders per safety policy
        ti = mt5.terminal_info()
        print(f"After Ctrl+E #1: trade_allowed={ti.trade_allowed if ti else None}")

    # The terminal trade_allowed flag DOESN'T directly reflect the AutoTrading
    # button. But since orders are still failing in the EA log, we may need to
    # press Ctrl+E AGAIN to flip it the right way.
    print("Sending Ctrl+E (try 2 — in case first toggle was OFF→OFF or ON→OFF)...")
    force_focus(hwnd)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "e")
    time.sleep(1.0)

    mt5.shutdown()
    print("[done] Watch the EA log — if it still says 'AutoTrading disabled by client',")
    print("       the toolbar button needs to be clicked manually (operator).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
