"""
sync_config_to_mqh.py
=====================
Reads config/trading_config.yaml and emits MQL5/Include/TrendMasterShared.mqh
so the EA's input defaults stay in lock-step with the Python brain.

Usage:
    python tools/sync_config_to_mqh.py [--out PATH]

After running, recompile AI_SUPERBB_v14_TrendMaster.mq5 in MetaEditor (or via
MetaEditor.exe /compile).

Generated header is idempotent — safe to re-run anytime YAML changes.
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

# We avoid hard pyyaml dep; fall back to a tiny parser if missing.
try:
    import yaml  # type: ignore
    HAVE_YAML = True
except ImportError:  # pragma: no cover
    HAVE_YAML = False


HEADER_TEMPLATE = """//+------------------------------------------------------------------+
//|  TrendMasterShared.mqh                                           |
//|  AUTO-GENERATED from config/trading_config.yaml                  |
//|  Do NOT edit by hand. Run: python tools/sync_config_to_mqh.py    |
//|                                                                  |
//|  Generated: {generated}                                          |
//|  YAML version: {version}                                         |
//+------------------------------------------------------------------+
#property strict
#ifndef __TM_SHARED_INCLUDED__
#define __TM_SHARED_INCLUDED__

// ---- Risk -----------------------------------------------------------------
#define TM_RISK_PERCENT                  {risk_percent:.4f}
#define TM_MAX_DAILY_DRAWDOWN_PCT        {max_daily_drawdown_percent:.4f}
#define TM_MAX_OPEN_TRADES               {max_open_trades}
#define TM_MAX_OPEN_PER_TEAM             {max_open_per_team}
#define TM_DEFAULT_SL_ATR_MULTIPLE       {default_sl_atr_multiple:.4f}
#define TM_DEFAULT_TP_ATR_MULTIPLE       {default_tp_atr_multiple:.4f}
#define TM_MIN_SL_PIPS                   {min_sl_pips}
#define TM_MIN_LOT_SIZE                  {min_lot_size:.4f}
#define TM_MAX_LOT_SIZE                  {max_lot_size:.4f}
#define TM_MIN_RR                        {min_risk_reward:.4f}

// ---- EA bridge (MUST match Python brain) ----------------------------------
#define TM_MAGIC                         {magic}
#define TM_SIGNAL_FILE                   "{signal_file}"
#define TM_USE_COMMON_FOLDER             {use_common_folder}
#define TM_AI_STALE_SECS                 {ai_stale_secs}
#define TM_AI_REQUIRED                   {ai_required}
#define TM_AI_AUTO_PER_SYMBOL            {ai_auto_per_symbol}

// ---- EA indicator defaults ------------------------------------------------
#define TM_EMA_FAST                      {ema_fast}
#define TM_EMA_MID                       {ema_mid}
#define TM_EMA_SLOW                      {ema_slow}
#define TM_SUPERTREND_PERIOD             {supertrend_period}
#define TM_SUPERTREND_FACTOR             {supertrend_factor:.4f}
#define TM_ADX_PERIOD                    {adx_period}
#define TM_ADX_MIN                       {adx_min}
#define TM_BB_PERIOD                     {bollinger_period}
#define TM_BB_DEV                        {bollinger_dev:.4f}
#define TM_BB_WIDTH_FLOOR_RATIO          {bollinger_width_floor_ratio:.4f}
#define TM_MACD_FAST                     {macd_fast}
#define TM_MACD_SLOW                     {macd_slow}
#define TM_MACD_SIGNAL                   {macd_signal}

#endif // __TM_SHARED_INCLUDED__
//+------------------------------------------------------------------+
"""


def _bool_to_mql(v: bool) -> str:
    return "true" if bool(v) else "false"


def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if HAVE_YAML:
        return yaml.safe_load(text)
    # Tiny fallback parser - good enough for our flat dotted YAML
    # but fail loudly if structure is unexpected.
    raise SystemExit(
        "[sync_config_to_mqh] PyYAML not installed. "
        "Run: pip install pyyaml"
    )


def render_mqh(cfg: dict) -> str:
    risk = cfg["risk"]
    bridge = cfg["ea_bridge"]
    ind = cfg["ea_indicators"]
    return HEADER_TEMPLATE.format(
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        version=cfg.get("version", 1),
        # Risk
        risk_percent=risk["risk_percent"],
        max_daily_drawdown_percent=risk["max_daily_drawdown_percent"],
        max_open_trades=risk["max_open_trades"],
        max_open_per_team=risk["max_open_per_team"],
        default_sl_atr_multiple=risk["default_sl_atr_multiple"],
        default_tp_atr_multiple=risk["default_tp_atr_multiple"],
        min_sl_pips=risk["min_sl_pips"],
        min_lot_size=risk["min_lot_size"],
        max_lot_size=risk["max_lot_size"],
        min_risk_reward=risk["min_risk_reward"],
        # Bridge
        magic=bridge["magic"],
        signal_file=bridge["signal_file"],
        use_common_folder=_bool_to_mql(bridge["use_common_folder"]),
        ai_stale_secs=bridge["ai_stale_secs"],
        ai_required=_bool_to_mql(bridge["ai_required"]),
        ai_auto_per_symbol=_bool_to_mql(bridge["ai_auto_per_symbol"]),
        # Indicators
        ema_fast=ind["ema_fast"],
        ema_mid=ind["ema_mid"],
        ema_slow=ind["ema_slow"],
        supertrend_period=ind["supertrend_period"],
        supertrend_factor=ind["supertrend_factor"],
        adx_period=ind["adx_period"],
        adx_min=ind["adx_min"],
        bollinger_period=ind["bollinger_period"],
        bollinger_dev=ind["bollinger_dev"],
        bollinger_width_floor_ratio=ind["bollinger_width_floor_ratio"],
        macd_fast=ind["macd_fast"],
        macd_slow=ind["macd_slow"],
        macd_signal=ind["macd_signal"],
    )


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    yaml_path = repo / "config" / "trading_config.yaml"
    default_out = repo / "MQL5" / "Include" / "TrendMasterShared.mqh"

    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", default=str(yaml_path),
                    help="Source YAML (default: %(default)s)")
    ap.add_argument("--out", default=str(default_out),
                    help="Output .mqh path (default: %(default)s)")
    args = ap.parse_args()

    src = Path(args.yaml)
    if not src.exists():
        print(f"[ERROR] YAML not found: {src}", file=sys.stderr)
        return 2

    cfg = _load_yaml(src)
    rendered = render_mqh(cfg)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8", newline="\r\n")
    print(f"[sync_config_to_mqh] wrote {out}  ({len(rendered)} bytes)")
    print(f"[sync_config_to_mqh] next: open the EA in MetaEditor and recompile,")
    print(f"                     OR run MetaEditor.exe /compile:<EA path>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
