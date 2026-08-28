"""Find which WM_COMMAND id toggles MT5 AutoTrading.
Tests each candidate ID one at a time, checks state, toggles back if needed."""
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


def post(hwnd, cid):
    user32.PostMessageW(hwnd, WM_COMMAND, cid, 0)


def main():
    hwnd, title = find_mt5_hwnd()[0]
    print(f"hwnd=0x{hwnd:x}")
    initial = get_state()
    print(f"INITIAL state: trade_allowed={initial}")

    # Test IDs from the toolbar entries we saw in terminal.ini Toolbar_488:
    # 32904, 32842, 33730, 32850, 39159, 39158, 32878, 32879, 32851, 32848,
    # 32910, 32909, 32908, 32911, 32912, 33527, 32906, 32905, 32933
    candidate_ids = [32904, 32842, 33730, 32850, 39159, 39158, 32878,
                     32879, 32851, 32848, 32933, 33527, 32906, 32905,
                     32842, 33522, 33523, 33524, 33525, 33526]
    for cid in candidate_ids:
        before = get_state()
        post(hwnd, cid)
        time.sleep(1.2)
        after = get_state()
        if after != before:
            print(f"  *** id={cid} CHANGED state: {before} -> {after}")
            if after is True:
                print("  >>> AutoTrading is now ON. Done.")
                return 0
            # If we toggled OFF, toggle back with same id
            print(f"  re-sending id={cid} to flip back...")
            post(hwnd, cid)
            time.sleep(1.5)
            print(f"  re-check: {get_state()}")
            if get_state() is True:
                return 0
        else:
            print(f"  id={cid} no change (state={after})")

    final = get_state()
    print(f"\nFINAL state: trade_allowed={final}")
    return 0 if final else 1


if __name__ == "__main__":
    sys.exit(main())
