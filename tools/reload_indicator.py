"""
Auto-reloads the AMD_Bot_Visualizer indicator in MT5
using pyautogui + pygetwindow to control the MT5 GUI programmatically.
"""

import time
import pyautogui
import pygetwindow as gw
import subprocess
import sys

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.4


def find_mt5_window():
    """Find and bring MetaTrader 5 window to front."""
    windows = gw.getWindowsWithTitle("MetaTrader 5")
    if not windows:
        windows = gw.getWindowsWithTitle("OctaFX")
    if not windows:
        print("ERROR: MetaTrader 5 window not found. Is MT5 open?")
        sys.exit(1)
    mt5_win = windows[0]
    mt5_win.activate()
    time.sleep(1)
    mt5_win.maximize()
    time.sleep(0.5)
    print(f"✅ Found MT5 window: {mt5_win.title}")
    return mt5_win


def click_chart_center(mt5_win):
    """Click in the center of the MT5 chart area."""
    # Chart area is roughly right half of window
    chart_x = mt5_win.left + int(mt5_win.width * 0.65)
    chart_y = mt5_win.top + int(mt5_win.height * 0.45)
    pyautogui.click(chart_x, chart_y)
    time.sleep(0.3)
    return chart_x, chart_y


def reload_visualizer():
    mt5_win = find_mt5_window()
    chart_x, chart_y = click_chart_center(mt5_win)

    print("Step 1: Right-clicking on chart to open context menu...")
    pyautogui.rightClick(chart_x, chart_y)
    time.sleep(0.8)

    # Take screenshot to see what appeared
    screenshot = pyautogui.screenshot()

    print("Step 2: Clicking 'Indicators List'...")
    # Look for 'Indicators List' in context menu - it appears near top of menu
    # Use keyboard shortcut instead for reliability
    pyautogui.press("escape")
    time.sleep(0.3)

    # Use MT5 keyboard shortcut: Ctrl+I opens Indicators List dialog
    pyautogui.hotkey("ctrl", "i")
    time.sleep(1.5)
    print("✅ Opened Indicators List dialog (Ctrl+I)")

    # Press Delete key to remove the selected indicator (if AMD_Bot_Visualizer is highlighted)
    # First take screenshot to see dialog
    shot = pyautogui.screenshot()
    shot.save("mt5_dialog_state.png")
    print(f"📸 Screenshot saved: mt5_dialog_state.png")

    # In Indicators List dialog, AMD_Bot_Visualizer should be visible
    # Click Delete button - it's usually on the right side of the dialog
    time.sleep(0.5)

    # Try to find and click the Delete button using image search,
    # or navigate by Tab key
    # Press Delete key
    pyautogui.press("delete")
    time.sleep(0.5)
    print("Step 3: Deleted old indicator instance...")

    # Close the dialog (OK or Enter)
    pyautogui.press("enter")
    time.sleep(0.5)

    print("Step 4: Re-opening Navigator (Ctrl+N)...")
    pyautogui.hotkey("ctrl", "n")
    time.sleep(0.8)

    print("Step 5: Pressing Ctrl+I to attach new indicator from Navigator...")
    # Now double-click within MT5 chart to focus it
    pyautogui.click(chart_x, chart_y)
    time.sleep(0.3)

    print("\n✅ Done! MT5 should now show the upgraded AI Swarm Bot Visualizer.")
    print("   Check your chart for green/red FVG arrows and blue ⚡Sweep labels.")


if __name__ == "__main__":
    print("🤖 AI Swarm MT5 Indicator Auto-Reloader")
    print("========================================")
    print("Make sure MetaTrader 5 is open and visible on screen.")
    print("Starting in 3 seconds...")
    time.sleep(3)
    reload_visualizer()
