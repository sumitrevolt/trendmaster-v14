"""Toggle MT5 AutoTrading via Ctrl+E (OS-level keystroke).

This forces all attached EAs to re-evaluate their state — equivalent to
re-attaching the EA on every chart. Use when EA's tick handler is stuck
(bar-close trigger no longer firing).

Method:
  1. Focus MT5 window via pygetwindow
  2. Send Ctrl+E (MT5's global AutoTrading toggle) — turns OFF
  3. Sleep 2 sec
  4. Send Ctrl+E again — turns ON, re-initializes EAs
"""
from __future__ import annotations
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pyautogui
import pygetwindow as gw

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


def find_mt5_window():
    """Find the MetaTrader 5 main window."""
    for w in gw.getAllWindows():
        if not w.title:
            continue
        # MT5 window titles: "<account_id> - <broker>: Demo Account - <type> - <name> - [<chart>]"
        if "OctaFX" in w.title or "MetaTrader" in w.title or "MT5" in w.title:
            return w
    return None


def main() -> int:
    print("=== MT5 AutoTrading toggle ===")
    mt5_win = find_mt5_window()
    if not mt5_win:
        print("[X] MT5 window not found")
        print("Visible windows:")
        for w in gw.getAllWindows():
            if w.title.strip():
                safe_title = (w.title or "").encode("ascii", "replace").decode("ascii")
                print(f"  {safe_title!r}")
        return 1

    safe_title = mt5_win.title.encode("ascii", "replace").decode("ascii")
    print(f"Found MT5: {safe_title!r}")
    print(f"  pos: ({mt5_win.left},{mt5_win.top})  size: {mt5_win.width}x{mt5_win.height}")

    # Bring to foreground
    try:
        if mt5_win.isMinimized:
            mt5_win.restore()
        mt5_win.activate()
    except Exception as e:
        print(f"[!] activate threw (often benign): {e}")
    time.sleep(0.8)

    # Verify foreground
    try:
        active = gw.getActiveWindow()
        if active and "OctaFX" in (active.title or ""):
            print(f"  [ok] MT5 is foreground")
        else:
            print(f"  [warn] foreground is: {(active.title if active else None)!r}")
    except Exception:
        pass

    # METHOD: cycle through all charts via Ctrl+F6 (next chart) and on each:
    # - F7 opens Expert Properties dialog
    # - Enter clicks OK -> EA re-initializes on that chart
    NUM_CHARTS = 9   # we have 8+ charts open; do 9 cycles to be safe
    for i in range(NUM_CHARTS):
        print(f"\n--- chart {i+1}/{NUM_CHARTS} ---")
        # Re-focus MT5 every iteration (dialogs may steal focus briefly)
        try:
            mt5_win.activate()
        except Exception:
            pass
        time.sleep(0.4)
        print("  F7 (open Expert Properties)...")
        pyautogui.press("f7")
        time.sleep(1.8)
        print("  Enter (click OK -> re-init)...")
        pyautogui.press("enter")
        time.sleep(1.5)
        print("  Ctrl+F6 (next chart)...")
        pyautogui.hotkey("ctrl", "f6")
        time.sleep(0.8)
    print("\n[OK] cycled through chart tabs with F7+Enter on each.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
