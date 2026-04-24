"""CLI smoke tests — parser wiring only, no side-effects."""

from __future__ import annotations

import pytest

import main as cli


def test_build_parser_exposes_all_subcommands():
    p = cli.build_parser()
    args = p.parse_args(["health"])
    assert args.cmd == "health"
    args = p.parse_args(["scan", "--min-votes", "2"])
    assert args.cmd == "scan" and args.min_votes == 2
    args = p.parse_args(["backtest", "XAUUSD", "--csv", "x.csv"])
    assert args.cmd == "backtest" and args.symbol == "XAUUSD"


def test_parser_rejects_unknown_subcommand():
    p = cli.build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["does-not-exist"])
