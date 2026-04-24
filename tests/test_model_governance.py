"""Unit tests for ai_trading_agents.model_governance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_trading_agents.model_governance import (
    DeploymentEntry,
    Governance,
    ModelCard,
)


def test_register_card_writes_json(tmp_path):
    g = Governance(models_dir=tmp_path)
    card = ModelCard(
        name="lgbm_METALS",
        version="v1",
        team="METALS",
        model_kind="lightgbm",
        trained_at="2026-04-23T00:00:00Z",
        trained_on_rows=241,
        feature_cols=["f1", "f2"],
        cv_method="cpcv",
        train_metrics={"auc": 0.82},
        oos_metrics={"auc": 0.73},
    )
    path = g.register_card(card)
    assert Path(path).exists()
    loaded = json.loads(Path(path).read_text())
    assert loaded["team"] == "METALS"


def test_list_cards_filters_by_team(tmp_path):
    g = Governance(models_dir=tmp_path)
    g.register_card(
        ModelCard(name="a", version="v1", team="METALS", model_kind="lgbm", trained_at="t", trained_on_rows=0)
    )
    g.register_card(
        ModelCard(name="b", version="v1", team="CRYPTO", model_kind="lgbm", trained_at="t", trained_on_rows=0)
    )
    metals = g.list_cards(team="METALS")
    crypto = g.list_cards(team="CRYPTO")
    assert len(metals) == 1
    assert len(crypto) == 1


def test_set_and_rollback_champion(tmp_path):
    g = Governance(models_dir=tmp_path)
    g.set_champion("METALS", "v1")
    g.set_champion("METALS", "v2")
    dep = g.get_deployment("METALS")
    assert dep.champion_version == "v2"
    assert dep.previous_version == "v1"
    out = g.rollback("METALS")
    assert out.champion_version == "v1"
    assert out.previous_version == "v2"


def test_challenger_flow(tmp_path):
    g = Governance(models_dir=tmp_path)
    g.set_champion("METALS", "v1")
    g.set_challenger("METALS", "v2", metrics={"auc": 0.75})
    dep = g.get_deployment("METALS")
    assert dep.challenger_version == "v2"
    # Promote.
    out = g.promote_challenger("METALS")
    assert out.champion_version == "v2"
    assert out.challenger_version == ""


def test_should_promote_margin():
    g = Governance(models_dir=Path("/tmp/test_gov_nonexistent_" + "x" * 8))
    assert g.should_promote("METALS", 0.70, 0.73, margin=0.02) is True
    assert g.should_promote("METALS", 0.70, 0.71, margin=0.02) is False


def test_rollback_without_previous_returns_none(tmp_path):
    g = Governance(models_dir=tmp_path)
    # No deployment set up.
    assert g.rollback("METALS") is None


def test_deployments_returns_dict(tmp_path):
    g = Governance(models_dir=tmp_path)
    g.set_champion("METALS", "v1")
    g.set_champion("CRYPTO", "v1")
    deps = g.deployments()
    assert "METALS" in deps
    assert "CRYPTO" in deps
    assert isinstance(deps["METALS"], DeploymentEntry)
