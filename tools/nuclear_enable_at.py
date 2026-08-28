"""Last-ditch attempt: use raw keybd_event Win32 API to send Ctrl+E.
Combined with foreground-window forcing via the Alt-key trick.
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
kernel32 = ctypes.windll.kernel32

VK_CONTROL = 0x11
VK_E = 0x45
VK_MENU = 0x12  # Alt
KEYEVENTF_KEYUP = 0x0002

SW_SHOW = 5
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


def get_state():
    mt5.initialize()
    ti = mt5.terminal_info()
    state = ti.trade_allowed if ti else None
    mt5.shutdown()
    return state


def force_foreground(hwnd):
    """Bypass Windows foreground-stealing protection.
    The 'AttachThreadInput' trick + Alt-key tap works most of the time."""
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, SW_SHOW)
    # AttachThreadInput trick
    fg = user32.GetForegroundWindow()
    cur_thread = kernel32.GetCurrentThreadId()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    user32.AttachThreadInput(cur_thread, fg_thread, True)
    user32.AttachThreadInput(cur_thread, target_thread, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(hwnd)
    user32.AttachThreadInput(cur_thread, fg_thread, False)
    user32.AttachThreadInput(cur_thread, target_thread, False)
    time.sleep(0.6)
    return user32.GetForegroundWindow() == hwnd


def send_ctrl_e_raw():
    """Send Ctrl+E using the lowest-level Win32 keyboard API."""
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_E, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_E, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def main():
    candidates = find_mt5_hwnd()
    if not candidates:
        print("[X] No MT5 window")
        return 1
    hwnd, title = candidates[0]
    print(f"hwnd=0x{hwnd:x}  title={title!r}")
    print(f"BEFORE: trade_allowed={get_state()}")

    print("Attempt 1: AttachThreadInput + SetForegroundWindow + Ctrl+E")
    ok = force_foreground(hwnd)
    print(f"  foreground={ok}")
    send_ctrl_e_raw()
    time.sleep(2.0)
    print(f"  AFTER1: trade_allowed={get_state()}")

    print("\nAttempt 2: Try again (in case Ctrl+E toggled wrong way)")
    ok = force_foreground(hwnd)
    print(f"  foreground={ok}")
    send_ctrl_e_raw()
    time.sleep(2.0)
    print(f"  AFTER2: trade_allowed={get_state()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
