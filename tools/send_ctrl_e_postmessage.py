"""Send Ctrl+E directly to MT5 via Win32 PostMessage WM_KEYDOWN/UP.

This works even without keyboard focus, and bypasses pyautogui issues.
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

import MetaTrader5 as mt5

user32 = ctypes.windll.user32
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_CONTROL = 0x11
VK_E = 0x45


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


def get_state():
    mt5.initialize()
    ti = mt5.terminal_info()
    state = ti.trade_allowed if ti else None
    mt5.shutdown()
    return state


def main():
    hwnd, title = find_mt5_hwnd()[0]
    print(f"hwnd=0x{hwnd:x}, title={title!r}")
    print(f"BEFORE: trade_allowed={get_state()}")

    # Send Ctrl+E via PostMessage
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_CONTROL, 0)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_E, 0)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_KEYUP, VK_E, 0)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_KEYUP, VK_CONTROL, 0)
    time.sleep(2.0)

    print(f"AFTER : trade_allowed={get_state()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
