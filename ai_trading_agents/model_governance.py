"""
model_governance.py — model cards + champion/challenger framework.

Why this exists
---------------
Every serious ML organisation treats deployed models as first-class
governed artefacts:

  * Who trained this? When? From what data?
  * What metrics did it hit — on training, on out-of-fold, on live?
  * What features is it using?
  * When was it promoted from challenger to champion?
  * Can we roll it back cleanly if live AUC drops?

This module provides:

  * `ModelCard` — schema for the JSON we write alongside every .pkl.
  * `register(card)` — persists the card and updates the registry.
  * `Champion/Challenger` tracking — each team has a `champion` and
    optionally a `challenger`. Live predictions use the champion; the
    challenger runs in shadow and its metrics accumulate. When the
    challenger beats the champion by a configurable margin over a
    configurable window, `promote()` swaps them — atomically.
  * `rollback()` — revert the champion to the previous version.

Storage
-------
  `ai_trading_agents/ml_models/governance.json` — the registry.
  `ai_trading_agents/ml_models/cards/<name>.json` — one card per model.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("model_governance")


@dataclass
class ModelCard:
    name: str  # e.g. "lgbm_METALS"
    version: str  # e.g. "v3-cpcv-2026-04-23"
    team: str  # "METALS" | "FOREX" | "CRYPTO" | "COMMODITIES"
    model_kind: str  # "lightgbm" | "sklearn" | "meta-labeler" | "hmm" | "online"
    trained_at: str  # ISO 8601
    trained_on_rows: int
    feature_cols: List[str] = field(default_factory=list)
    cv_method: str = "none"  # "none" | "holdout" | "cpcv"
    train_metrics: Dict[str, float] = field(default_factory=dict)
    oos_metrics: Dict[str, float] = field(default_factory=dict)
    hyperparams: Dict[str, Any] = field(default_factory=dict)
    data_checksum: str = ""
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeploymentEntry:
    team: str
    champion_version: str
    champion_since: str
    previous_version: str = ""  # for rollback
    challenger_version: str = ""  # optional shadow model
    challenger_since: str = ""
    challenger_metrics: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


class Governance:
    """Load / mutate / save the governance.json registry."""

    def __init__(self, models_dir: Optional[Path] = None):
        self.dir = Path(models_dir) if models_dir else (Path(__file__).resolve().parent / "ml_models")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cards_dir = self.dir / "cards"
        self.cards_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.dir / "governance.json"

    # ---------- low-level IO ----------
    def _load(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": 1, "updated_at": "", "deployments": {}}
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("governance load failed: %s", e)
            return {"version": 1, "updated_at": "", "deployments": {}}

    def _save(self, payload: Dict[str, Any]) -> None:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp = self.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.registry_path)

    # ---------- card ops ----------
    def register_card(self, card: ModelCard) -> str:
        path = self.cards_dir / f"{card.name}_{card.version}.json"
        path.write_text(json.dumps(card.as_dict(), indent=2), encoding="utf-8")
        return str(path)

    def list_cards(self, team: Optional[str] = None) -> List[Dict]:
        out: List[Dict] = []
        for p in sorted(self.cards_dir.glob("*.json")):
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
                if team is None or obj.get("team") == team:
                    out.append(obj)
            except Exception:
                continue
        return out

    # ---------- deployment ops ----------
    def get_deployment(self, team: str) -> Optional[DeploymentEntry]:
        reg = self._load()
        dep = reg.get("deployments", {}).get(team)
        if not dep:
            return None
        return DeploymentEntry(**dep)

    def set_champion(self, team: str, version: str) -> DeploymentEntry:
        """Promote `version` to champion. Stamps previous_version for rollback."""
        reg = self._load()
        dep = reg.setdefault("deployments", {}).setdefault(team, {})
        dep["team"] = team
        dep["previous_version"] = dep.get("champion_version", "")
        dep["champion_version"] = version
        dep["champion_since"] = datetime.now(timezone.utc).isoformat()
        self._save(reg)
        return DeploymentEntry(**dep)

    def set_challenger(self, team: str, version: str, metrics: Optional[Dict[str, float]] = None) -> DeploymentEntry:
        reg = self._load()
        dep = reg.setdefault("deployments", {}).setdefault(team, {})
        dep["team"] = team
        dep.setdefault("champion_version", "")
        dep.setdefault("champion_since", "")
        dep["challenger_version"] = version
        dep["challenger_since"] = datetime.now(timezone.utc).isoformat()
        dep["challenger_metrics"] = metrics or {}
        self._save(reg)
        return DeploymentEntry(**{k: v for k, v in dep.items() if k in DeploymentEntry.__dataclass_fields__})

    def should_promote(self, team: str, champion_metric: float, challenger_metric: float, margin: float = 0.02) -> bool:
        """Promote challenger if it beats champion by `margin`."""
        return (challenger_metric - champion_metric) >= margin

    def promote_challenger(self, team: str) -> Optional[DeploymentEntry]:
        """Swap challenger → champion atomically."""
        reg = self._load()
        dep = reg.get("deployments", {}).get(team)
        if not dep or not dep.get("challenger_version"):
            return None
        new_champion = dep["challenger_version"]
        dep["previous_version"] = dep.get("champion_version", "")
        dep["champion_version"] = new_champion
        dep["champion_since"] = datetime.now(timezone.utc).isoformat()
        dep["challenger_version"] = ""
        dep["challenger_since"] = ""
        dep["challenger_metrics"] = {}
        self._save(reg)
        return DeploymentEntry(**{k: v for k, v in dep.items() if k in DeploymentEntry.__dataclass_fields__})

    def rollback(self, team: str) -> Optional[DeploymentEntry]:
        """Swap champion → previous_version."""
        reg = self._load()
        dep = reg.get("deployments", {}).get(team)
        if not dep or not dep.get("previous_version"):
            return None
        dep["previous_version"], dep["champion_version"] = (
            dep["champion_version"],
            dep["previous_version"],
        )
        dep["champion_since"] = datetime.now(timezone.utc).isoformat()
        self._save(reg)
        return DeploymentEntry(**{k: v for k, v in dep.items() if k in DeploymentEntry.__dataclass_fields__})

    def deployments(self) -> Dict[str, DeploymentEntry]:
        reg = self._load()
        return {team: DeploymentEntry(**dep) for team, dep in reg.get("deployments", {}).items()}


__all__ = ["ModelCard", "DeploymentEntry", "Governance"]
