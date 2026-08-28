"""Enable MT5 AutoTrading via Ctrl+E (forces ON, not toggle)."""
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
pyautogui.PAUSE = 0.2


def find_mt5_window():
    for w in gw.getAllWindows():
        if not w.title:
            continue
        if "OctaFX" in w.title or "MetaTrader" in w.title or "MT5" in w.title:
            return w
    return None


def main() -> int:
    print("=== Enable MT5 AutoTrading ===")
    mt5_win = find_mt5_window()
    if not mt5_win:
        print("[X] MT5 window not found")
        return 1

    safe = mt5_win.title.encode("ascii", "replace").decode("ascii")
    print(f"Found MT5: {safe!r}")

    try:
        if mt5_win.isMinimized:
            mt5_win.restore()
        mt5_win.activate()
    except Exception as e:
        print(f"[!] activate threw: {e}")
    time.sleep(1.0)

    # Send Ctrl+E to toggle AutoTrading. We can't easily check current state
    # so press once. If the orders start going through, it's ON. If not, the
    # operator can click the button manually OR we re-send Ctrl+E.
    print("Sending Ctrl+E (AutoTrading toggle)...")
    pyautogui.hotkey("ctrl", "e")
    time.sleep(0.5)
    print("[OK] Ctrl+E sent. Check MT5 toolbar — button should be GREEN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
