"""
switch_openclaw_models.py - swap OpenClaw agent models in openclaw.json.

Why: Copilot's claude-opus-4.6 route was returning 400 model_not_supported
on 2026-04-29 evening. Per Sumit, switch trader/reviewer/architect/debugger
to claude-sonnet-4.6 (also Copilot-routed, also registered in defaults.models).

Usage:
    python tools/switch_openclaw_models.py FROM_MODEL TO_MODEL [agent_ids...]

Example:
    python tools/switch_openclaw_models.py \
        github-copilot/claude-opus-4.6 \
        github-copilot/claude-sonnet-4.6 \
        trader reviewer architect debugger
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONFIG = Path(os.environ.get("USERPROFILE", "")) / ".openclaw" / "openclaw.json"


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    from_model = argv[1]
    to_model = argv[2]
    agent_ids = set(argv[3:])

    if not CONFIG.exists():
        print(f"ERR: config not found at {CONFIG}", file=sys.stderr)
        return 1

    j = json.loads(CONFIG.read_text(encoding="utf-8"))
    changed: list[str] = []
    for agent in j.get("agents", {}).get("list", []):
        if agent.get("id") in agent_ids and agent.get("model") == from_model:
            agent["model"] = to_model
            changed.append(agent["id"])

    if not changed:
        print(f"NOCHANGE: no agents matched id IN {sorted(agent_ids)} AND model={from_model}")
        return 0

    CONFIG.write_text(json.dumps(j, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"SWITCHED {from_model} -> {to_model} for: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
