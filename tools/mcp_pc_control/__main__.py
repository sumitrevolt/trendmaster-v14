from __future__ import annotations

import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pyautogui
import pygetwindow as gw
from mcp.server.fastmcp import FastMCP, Image

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_PATH = PROJECT_ROOT / "logs" / "pc_control.jsonl"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

BLOCKED_KEYWORDS = [
    k.strip().lower() for k in os.environ.get("PC_CONTROL_BLOCK_FOREGROUND", "").split(";") if k.strip()
]

DRY_RUN = os.environ.get("PC_CONTROL_DRY_RUN", "").lower() in {"1", "true", "yes"}

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

mcp = FastMCP("pc-control")


def _audit(action: str, payload: dict) -> None:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        **payload,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _foreground_title() -> str:
    try:
        w = gw.getActiveWindow()
        return w.title if w else ""
    except Exception:
        return ""


def _blocked_by(title: str) -> str | None:
    low = title.lower()
    for kw in BLOCKED_KEYWORDS:
        if kw and kw in low:
            return kw
    return None


def _refuse(action: str, title: str, blocked: str) -> dict:
    rec = {
        "ok": False,
        "refused": True,
        "reason": f"foreground window '{title}' matches blocklist keyword '{blocked}'",
        "foreground_title": title,
    }
    _audit(action, rec)
    return rec


@mcp.tool()
def get_foreground_window() -> dict:
    """Return the active window title, screen size, and whether the blocklist would
    refuse a write action right now. Always call this BEFORE click/type/key actions."""
    title = _foreground_title()
    blocked = _blocked_by(title)
    sz = pyautogui.size()
    out = {
        "title": title,
        "blocked": bool(blocked),
        "blocked_by": blocked,
        "screen_width": sz.width,
        "screen_height": sz.height,
        "blocklist_keywords": BLOCKED_KEYWORDS,
        "dry_run": DRY_RUN,
    }
    _audit("get_foreground_window", out)
    return out


@mcp.tool()
def list_windows() -> list[dict]:
    """List visible windows with title and bounds. Use this to find a window to focus."""
    out: list[dict] = []
    active = None
    try:
        active = gw.getActiveWindow()
    except Exception:
        pass
    for w in gw.getAllWindows():
        try:
            if not w.title or not w.visible:
                continue
            out.append(
                {
                    "title": w.title,
                    "left": w.left,
                    "top": w.top,
                    "width": w.width,
                    "height": w.height,
                    "is_active": active is not None and w._hWnd == active._hWnd,
                }
            )
        except Exception:
            pass
    _audit("list_windows", {"count": len(out)})
    return out


@mcp.tool()
def focus_window(title_substring: str) -> dict:
    """Bring the first window whose title contains `title_substring` to the foreground.
    Returns ok=False if it would land on a blocklist window — that prevents accidental
    focus of MetaTrader/banking. To intentionally focus a blocked window, the operator
    must do it manually."""
    matches = [w for w in gw.getAllWindows() if w.title and title_substring.lower() in w.title.lower()]
    if not matches:
        out = {"ok": False, "reason": f"no window matches '{title_substring}'"}
        _audit("focus_window", out)
        return out
    w = matches[0]
    blocked = _blocked_by(w.title)
    if blocked:
        out = {
            "ok": False,
            "refused": True,
            "reason": f"target window '{w.title}' matches blocklist keyword '{blocked}'",
        }
        _audit("focus_window", out)
        return out
    try:
        if w.isMinimized:
            w.restore()
        w.activate()
        time.sleep(0.3)
        out = {"ok": True, "title": w.title}
    except Exception as e:
        out = {"ok": False, "reason": f"activate failed: {e}"}
    _audit("focus_window", out)
    return out


@mcp.tool()
def screenshot(region: list[int] | None = None) -> Image:
    """Capture screen (or rectangular region [x, y, width, height]) as PNG.
    Read-only — never blocked."""
    if region:
        if len(region) != 4:
            raise ValueError("region must be [x, y, width, height]")
        img = pyautogui.screenshot(region=tuple(region))
    else:
        img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    _audit(
        "screenshot",
        {
            "width": img.width,
            "height": img.height,
            "region": region,
            "foreground_title": _foreground_title(),
        },
    )
    return Image(data=buf.getvalue(), format="png")


@mcp.tool()
def mouse_move(x: int, y: int, duration: float = 0.2) -> dict:
    """Move the mouse cursor (no click). Permitted on blocked foreground since
    a hover doesn't change state."""
    if DRY_RUN:
        out = {"ok": True, "dry_run": True, "x": x, "y": y}
    else:
        pyautogui.moveTo(x, y, duration=max(0.0, duration))
        out = {"ok": True, "x": x, "y": y}
    _audit("mouse_move", out)
    return out


@mcp.tool()
def mouse_click(
    x: int,
    y: int,
    button: Literal["left", "right", "middle"] = "left",
    clicks: int = 1,
) -> dict:
    """Click at screen coordinate. REFUSED if foreground window matches the blocklist
    (MetaTrader/OctaFX/banking). Operator must change focus manually first."""
    title = _foreground_title()
    blocked = _blocked_by(title)
    if blocked:
        return _refuse("mouse_click", title, blocked)
    if DRY_RUN:
        out = {
            "ok": True,
            "dry_run": True,
            "x": x,
            "y": y,
            "button": button,
            "clicks": clicks,
            "foreground_title": title,
        }
        _audit("mouse_click", out)
        return out
    pyautogui.click(x=x, y=y, button=button, clicks=clicks)
    out = {
        "ok": True,
        "x": x,
        "y": y,
        "button": button,
        "clicks": clicks,
        "foreground_title": title,
    }
    _audit("mouse_click", out)
    return out


@mcp.tool()
def type_text(text: str, interval: float = 0.02) -> dict:
    """Type characters into the focused window. REFUSED if foreground matches the
    blocklist. `interval` is seconds between keystrokes."""
    title = _foreground_title()
    blocked = _blocked_by(title)
    if blocked:
        return _refuse("type_text", title, blocked)
    if DRY_RUN:
        out = {
            "ok": True,
            "dry_run": True,
            "chars": len(text),
            "foreground_title": title,
        }
        _audit("type_text", out)
        return out
    pyautogui.write(text, interval=max(0.0, interval))
    out = {"ok": True, "chars": len(text), "foreground_title": title}
    _audit("type_text", out)
    return out


@mcp.tool()
def key_press(keys: list[str]) -> dict:
    """Press a key or key combination. Single key: ['enter']. Combo: ['ctrl','s'].
    REFUSED if foreground matches the blocklist."""
    title = _foreground_title()
    blocked = _blocked_by(title)
    if blocked:
        return _refuse("key_press", title, blocked)
    if not keys:
        out = {"ok": False, "reason": "empty keys list"}
        _audit("key_press", out)
        return out
    if DRY_RUN:
        out = {"ok": True, "dry_run": True, "keys": keys, "foreground_title": title}
        _audit("key_press", out)
        return out
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)
    out = {"ok": True, "keys": keys, "foreground_title": title}
    _audit("key_press", out)
    return out


def main() -> None:
    _audit(
        "startup",
        {
            "blocklist": BLOCKED_KEYWORDS,
            "dry_run": DRY_RUN,
            "python": sys.version.split()[0],
            "cwd": str(Path.cwd()),
        },
    )
    mcp.run()


if __name__ == "__main__":
    main()
