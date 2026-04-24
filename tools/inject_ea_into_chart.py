"""
Inject the v14 EA <expert> block into MT5's active chart profile,
write a standalone .tpl template, and make sure common.ini has
AutoTrading (Experts Enabled) switched on.
"""

from __future__ import annotations
import shutil, sys, re, time
from pathlib import Path

DATA_PATH = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075")
CHART_FILE = DATA_PATH / "MQL5" / "Profiles" / "Charts" / "Default" / "chart01.chr"
TEMPLATE_TGT = DATA_PATH / "MQL5" / "Profiles" / "Templates" / "TrendMaster_v14.tpl"
COMMON_INI = DATA_PATH / "config" / "common.ini"

ROOT = Path(__file__).resolve().parent.parent
EXPERT_BLOCK_SRC = ROOT / "tools" / "trendmaster_v14_expert_block.txt"


def backup(p: Path) -> Path:
    bk = p.with_suffix(p.suffix + f".bak-v14-{int(time.time())}")
    shutil.copy2(p, bk)
    return bk


def inject_expert_into_chart(chart_text: str, expert_block: str) -> str:
    """
    Place the <expert>...</expert> block right before the first <window>.
    If there's already an <expert> block, replace it.
    """
    if "<expert>" in chart_text:
        replacement = expert_block + "\n"
        chart_text = re.sub(
            r"<expert>.*?</expert>\s*",
            lambda _m: replacement,
            chart_text,
            count=1,
            flags=re.DOTALL,
        )
        return chart_text
    # Find first <window> and insert before it
    idx = chart_text.find("<window>")
    if idx < 0:
        raise RuntimeError("chart file has no <window> section")
    # Keep original file's newline convention
    return chart_text[:idx] + expert_block + "\n" + chart_text[idx:]


def make_standalone_tpl(expert_block: str) -> str:
    """Minimal template that re-applies just the EA on any chart."""
    return "<chart>\nid=1\n" + expert_block + "\n" + "<window>\nheight=100\nobjects=0\n</window>\n</chart>\n"


def ensure_autotrading(ini_text: str) -> str:
    """Make sure [Experts] Enabled=1 in common.ini."""
    # Simple line-based toggle inside [Experts]
    lines = ini_text.splitlines()
    out, in_exp = [], False
    saw_enabled = False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            if in_exp and not saw_enabled:
                out.append("Enabled=1")
                saw_enabled = True
            in_exp = s.lower() == "[experts]"
        if in_exp and s.lower().startswith("enabled"):
            out.append("Enabled=1")
            saw_enabled = True
            continue
        out.append(line)
    if in_exp and not saw_enabled:
        out.append("Enabled=1")
    return "\n".join(out) + ("\n" if ini_text.endswith("\n") else "")


def main() -> int:
    print("=" * 60)
    print("  v14 EA injector")
    print("=" * 60)

    if not CHART_FILE.exists():
        print(f"[X] chart file not found: {CHART_FILE}")
        return 1
    if not EXPERT_BLOCK_SRC.exists():
        print(f"[X] expert block file not found: {EXPERT_BLOCK_SRC}")
        return 1

    expert = EXPERT_BLOCK_SRC.read_text(encoding="ascii").strip()

    # ---- 1. Standalone template ---------------------------------------
    TEMPLATE_TGT.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_TGT.write_text(make_standalone_tpl(expert), encoding="ascii")
    print(f"[OK] wrote standalone template: {TEMPLATE_TGT}  ({TEMPLATE_TGT.stat().st_size} bytes)")

    # ---- 2. Inject into chart01.chr -----------------------------------
    bk = backup(CHART_FILE)
    print(f"[OK] chart backup: {bk.name}  ({bk.stat().st_size} bytes)")

    raw = (
        CHART_FILE.read_text(encoding="utf-16le")
        if CHART_FILE.read_bytes()[:2] == b"\xff\xfe"
        else CHART_FILE.read_text(encoding="ascii")
    )
    new = inject_expert_into_chart(raw, expert)
    # Preserve original encoding
    if CHART_FILE.read_bytes()[:2] == b"\xff\xfe":
        CHART_FILE.write_text(new, encoding="utf-16le")
    else:
        CHART_FILE.write_text(new, encoding="ascii")
    print(f"[OK] injected <expert> block into {CHART_FILE.name}")
    print(f"      new size: {CHART_FILE.stat().st_size} bytes (was {bk.stat().st_size})")

    # ---- 3. common.ini — ensure Experts Enabled=1 ---------------------
    if COMMON_INI.exists():
        ini_bk = backup(COMMON_INI)
        orig = COMMON_INI.read_text(encoding="ascii", errors="ignore")
        patched = ensure_autotrading(orig)
        if patched != orig:
            COMMON_INI.write_text(patched, encoding="ascii")
            print(f"[OK] common.ini patched (Experts Enabled=1). backup: {ini_bk.name}")
        else:
            print("[OK] common.ini already has Experts Enabled=1 (no change)")
            ini_bk.unlink(missing_ok=True)

    print("\n=== INJECTION DONE ===")
    print("Restart MT5 for the EA to attach on the XAUUSD M5 chart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
