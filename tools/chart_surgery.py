"""
chart_surgery.py — edit chart01.chr in place:
  1. Remove any indicator block referencing AI_AMD_SMC_Indicator.ex5
     (the TV-MATCH style overlay that clutters v14's output)
  2. Switch chart period to H4 (240 minutes)
  3. Re-write EA inputs block for H4-tuned thresholds
  4. Remove autotrade history noise names
  5. Preserve UTF-16 LE BOM + \r\n line endings (MT5 is picky)

USAGE:   python tools\\chart_surgery.py
         (MT5 must be closed first — otherwise it overwrites on exit)
"""

from __future__ import annotations
import re, shutil, os, time
from pathlib import Path

CHR = Path(
    r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal"
    r"\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Profiles\Charts\Default\chart01.chr"
)

# ---------- read ----------
raw = CHR.read_bytes()
if not raw.startswith(b"\xff\xfe"):
    raise SystemExit("chart01.chr is not UTF-16 LE BOM — refusing to edit")
text = raw[2:].decode("utf-16-le")
print(f"[read] {CHR.name} size={len(raw)} bytes, {text.count(chr(10)) + 1} lines")

backup = CHR.with_suffix(".chr.bak")
backup.write_bytes(raw)
print(f"[bak ] {backup}")

# ---------- 1) drop AI_AMD_SMC_Indicator block ----------
# Indicator blocks span from <indicator> ... </indicator>
# We drop any block whose body mentions AI_AMD_SMC_Indicator.ex5
ind_block_re = re.compile(r"<indicator>.*?</indicator>\r?\n?", re.DOTALL)
removed_ind = 0


def drop_if_match(m: re.Match) -> str:
    global removed_ind
    body = m.group(0)
    if "AI_AMD_SMC_Indicator" in body or "TV-MATCH" in body.upper() or "TVMATCH" in body.upper():
        removed_ind += 1
        return ""
    return body


text = ind_block_re.sub(drop_if_match, text)
print(f"[drop] indicator blocks removed: {removed_ind}")


# ---------- 2) switch period to 240 (H4) ----------
def set_or_insert(field: str, value: str, scope: str = "top") -> tuple[str, bool]:
    """Update field=... if present in top-level; else insert near top."""
    pattern = re.compile(rf"(?m)^{re.escape(field)}=.*$")
    if pattern.search(text):
        return pattern.sub(f"{field}={value}", text, count=1), True
    return text, False


for fld, val in (("period", "240"), ("period_size", "240"), ("period_type", "0")):
    new_text, changed = set_or_insert(fld, val)
    if changed:
        text = new_text
        print(f"[set ] {fld}={val}")
    else:
        # Only period should need inserting; others always exist
        print(f"[miss] {fld} not present in chart file (no-op)")

# ---------- 3) H4-tuned EA inputs ----------
# Only fields that appear inside the <expert> block
H4_INPUTS = {
    "InpADX_Min": "25.0",  # slightly tighter trend gate on H4
    "InpADX_Period": "14",
    "InpST_Period": "14",  # slower ST for H4
    "InpST_Mult": "3.0",
    "InpEMA_Fast": "20",
    "InpEMA_Slow": "50",
    "InpEMA_Trend": "200",
    "InpBB_Period": "20",
    "InpBB_Dev": "2.0",
    "InpMACD_Fast": "12",
    "InpMACD_Slow": "26",
    "InpMACD_Sig": "9",
    "InpATR_Period": "14",
    "InpRequireAll3": "true",
    "InpSL_AtrMult": "1.2",  # tighter SL on H4 (lower noise)
    "InpTP_AtrMult": "3.5",  # bigger TP on H4 (1:2.9 RR)
    "InpUsePartial1": "true",
    "InpUsePartial2": "true",
    "InpChandelierLook": "10",
    "InpChandelierAtr": "2.5",
    "InpCooldownSecs": "7200",  # 2h between entries (H4 context)
    "InpUseSessionFilt": "true",
    "InpBlockNewsWin": "true",
    "InpAIRequired": "false",  # advisory until we see 50 trades
    "InpRiskPct": "1.0",
    "InpAdaptiveSize": "true",
    "InpMaxRiskPct": "2.0",
    "InpMaxDailyLossPc": "3.0",
    "InpMaxSpreadAtrPc": "0.20",
    # visuals ON
    "InpShowEMAs": "true",
    "InpShowBB": "true",
    "InpShowSuperTrend": "true",
    "InpShowArrows": "true",
    "InpShowSLTPLines": "true",
    "InpDrawBars": "250",
}

expert_re = re.compile(r"(<expert>\r?\n)(.*?)(\r?\n</expert>)", re.DOTALL)
m = expert_re.search(text)
if not m:
    raise SystemExit("no <expert> block found")
head, body, tail = m.groups()
inputs_applied = 0
for key, val in H4_INPUTS.items():
    key_re = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    if key_re.search(body):
        body = key_re.sub(f"{key}={val}", body, count=1)
    else:
        body = body.rstrip() + f"\r\n{key}={val}"
    inputs_applied += 1
text = text[: m.start()] + head + body + tail + text[m.end() :]
print(f"[set ] EA inputs retuned for H4: {inputs_applied} keys")

# ---------- 4) clean autotrade history noise ----------
autotrade_re = re.compile(r"(?m)^name=autotrade #\d+ .*$\r?\n?")
n_at = len(autotrade_re.findall(text))
text = autotrade_re.sub("", text)
print(f"[drop] autotrade lines stripped: {n_at}")

# ---------- write ----------
out = b"\xff\xfe" + text.encode("utf-16-le")
CHR.write_bytes(out)
print(f"[ok  ] wrote {len(out)} bytes (was {len(raw)})")
