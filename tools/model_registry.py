"""
tools/model_registry.py - versioned LightGBM model storage.

Layout
------
    models/
    |- {symbol}/
    |   |- 20260422T103000.lgb
    |   |- 20260422T103000.json
    |   |- latest.lgb
    |   \- latest.json
    \- index.json
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
MODELS = _ROOT / "models"
INDEX  = MODELS / "index.json"

logger = logging.getLogger("model_registry")


def _now_version() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _load_index() -> dict:
    if not INDEX.exists():
        return {}
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_index(idx: dict) -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(idx, indent=2), encoding="utf-8")


def register_model(symbol: str, booster: Any, metadata: dict) -> Path:
    """Persist a booster + metadata. Returns the model file path."""
    symbol = symbol.upper()
    sym_dir = MODELS / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)
    base = _now_version()
    ver = base
    i = 1
    while (sym_dir / f"{ver}.lgb").exists():
        i += 1
        ver = f"{base}-{i}"

    model_path = sym_dir / f"{ver}.lgb"
    meta_path  = sym_dir / f"{ver}.json"
    booster.save_model(str(model_path))
    metadata = dict(metadata, symbol=symbol, version=ver, created_utc=ver)
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    shutil.copy2(model_path, sym_dir / "latest.lgb")
    shutil.copy2(meta_path,  sym_dir / "latest.json")

    idx = _load_index()
    idx.setdefault(symbol, []).append(ver)
    _save_index(idx)
    logger.info("registered %s version %s", symbol, ver)
    return model_path


def list_versions(symbol: str) -> List[str]:
    return _load_index().get(symbol.upper(), [])


def latest_model_path(symbol: str) -> Optional[Path]:
    p = MODELS / symbol.upper() / "latest.lgb"
    return p if p.exists() else None


def latest_metadata(symbol: str) -> Optional[dict]:
    p = MODELS / symbol.upper() / "latest.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def rollback_to(symbol: str, version: str) -> bool:
    sym_dir = MODELS / symbol.upper()
    m = sym_dir / f"{version}.lgb"
    j = sym_dir / f"{version}.json"
    if not (m.exists() and j.exists()):
        logger.error("cannot rollback: %s %s missing", symbol, version)
        return False
    shutil.copy2(m, sym_dir / "latest.lgb")
    shutil.copy2(j, sym_dir / "latest.json")
    logger.info("%s rolled back to %s", symbol, version)
    return True


__all__ = [
    "register_model", "list_versions", "latest_model_path",
    "latest_metadata", "rollback_to",
]
