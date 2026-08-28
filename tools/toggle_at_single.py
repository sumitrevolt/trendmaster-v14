"""Send single WM_COMMAND id=32850 to toggle MT5 AutoTrading ONCE.
Verify state before+after via mt5.terminal_info().trade_allowed.
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
WM_COMMAND = 0x0111


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
    print(f"hwnd=0x{hwnd:x}")
    before = get_state()
    print(f"BEFORE: trade_allowed={before}")
    user32.PostMessageW(hwnd, WM_COMMAND, 32850, 0)
    time.sleep(2.0)
    after = get_state()
    print(f"AFTER : trade_allowed={after}")
    if after is True:
        print("[OK] AutoTrading is now ON.")
        return 0
    elif after is False and before is True:
        print("[FLIP] Was ON, now OFF — sending again to flip back...")
        user32.PostMessageW(hwnd, WM_COMMAND, 32850, 0)
        time.sleep(2.0)
        final = get_state()
        print(f"FINAL: trade_allowed={final}")
    else:
        # before=False, after=False — toggle didn't work, try again
        print("[Retry] State didn't change. Sending one more time...")
        user32.PostMessageW(hwnd, WM_COMMAND, 32850, 0)
        time.sleep(2.0)
        final = get_state()
        print(f"FINAL: trade_allowed={final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
