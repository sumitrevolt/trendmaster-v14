"""
ADVANCED AGENT TRAINING SYSTEM — ML-Powered Self-Learning
============================================================
Uses CPU-based Machine Learning to continuously improve trade quality.

LEVEL 1: Statistical Learning (always active)
  - Win rate per symbol, session, indicator combo
  - Adaptive thresholds that auto-adjust based on results
  - Market regime detection (trending vs ranging)

LEVEL 2: ML Pattern Recognition (activates after 50+ trades)
  - Decision Tree classifier predicts WIN/LOSS probability
  - Learns which exact feature combinations produce wins
  - Auto-adjusts confidence based on prediction

LEVEL 3: Auto-Management
  - Auto-disable symbols with <35% win rate (after 10+ trades)
  - Auto-boost symbols with >65% win rate
  - Auto-adjust score thresholds per symbol
  - Blacklist bad session hours per symbol

USES CPU ONLY — no GPU required. Lightweight sklearn models.
"""

import json
import os
import logging
import math
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))
TRAINING_FILE = os.path.join(_DIR, "agent_training_data.json")

# Try to import ML libraries (XGBoost > LightGBM > sklearn fallback)
ML_AVAILABLE = False
ML_ENGINE = "none"  # "xgboost", "lightgbm", "sklearn", or "none"
try:
    from xgboost import XGBClassifier
    from sklearn.model_selection import cross_val_score, StratifiedKFold
    from sklearn.preprocessing import LabelEncoder
    from sklearn.ensemble import VotingClassifier
    from sklearn.tree import DecisionTreeClassifier
    import numpy as np
    ML_AVAILABLE = True
    ML_ENGINE = "xgboost"
    logger.info("✅ ML Training: XGBoost + cross-validation loaded (UPGRADED)")
except ImportError:
    try:
        from lightgbm import LGBMClassifier
        from sklearn.model_selection import cross_val_score, StratifiedKFold
        from sklearn.preprocessing import LabelEncoder
        from sklearn.ensemble import VotingClassifier
        from sklearn.tree import DecisionTreeClassifier
        import numpy as np
        ML_AVAILABLE = True
        ML_ENGINE = "lightgbm"
        logger.info("✅ ML Training: LightGBM + cross-validation loaded (UPGRADED)")
    except ImportError:
        try:
            from sklearn.tree import DecisionTreeClassifier
            from sklearn.model_selection import cross_val_score, StratifiedKFold
            from sklearn.preprocessing import LabelEncoder
            from sklearn.ensemble import VotingClassifier
            import numpy as np
            ML_AVAILABLE = True
            ML_ENGINE = "sklearn"
            logger.info("✅ ML Training: sklearn DecisionTree (fallback, consider installing xgboost)")
        except ImportError:
            logger.info("ℹ️ ML Training not available (install xgboost or scikit-learn)")


class TradeSnapshot:
    """Captures ALL conditions at trade entry for later analysis."""

    @staticmethod
    def capture(symbol: str, direction: str, score: int, confidence: int,
                h1_trend: str, h4_trend: str, rsi: float, adx: float,
                macd_label: str, bb_state: str, amd_phase: str,
                news_sentiment: str, session_hour: int,
                institutional_direction: str = "NEUTRAL",
                institutional_confidence: int = 50,
                killzone: str = "NONE",
                volume_signal: str = "NORMAL",
                agents_involved: List[str] = None) -> Dict:
        """Create a snapshot of all conditions at trade entry."""
        return {
            "symbol": symbol,
            "direction": direction,
            "score": score,
            "confidence": confidence,
            "h1_trend": h1_trend,
            "h4_trend": h4_trend,
            "h4_h1_aligned": h4_trend == h1_trend and h4_trend != "SIDEWAYS",
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
            "macd": macd_label,
            "bb_state": bb_state,
            "amd_phase": amd_phase,
            "news": news_sentiment,
            "hour_utc": session_hour,
            "institutional_dir": institutional_direction,
            "institutional_conf": institutional_confidence,
            "killzone": killzone,
            "volume_signal": volume_signal,
            "agents": agents_involved or [],
            "entry_time": datetime.utcnow().isoformat(),
            # Filled after trade closes:
            "outcome": None,  # "WIN" or "LOSS"
            "pnl": 0.0,
            "close_time": None,
        }


class TrainingEngine:
    """
    Advanced self-learning engine with ML pattern recognition.
    """

    _data: Dict = {
        "trades": [],
        "patterns": {},
        "agent_accuracy": {},
        "symbol_stats": {},
        "session_stats": {},
        "combo_stats": {},
        "regime_stats": {},
        "adaptive_thresholds": {},
        "blacklisted_symbols": [],
        "blacklisted_hours": {},
        "ml_model_accuracy": 0,
        "last_trained": None,
        "total_pnl": 0,
    }
    _loaded = False
    _MAX_TRADES = 2000
    _ml_model = None
    _ml_encoders: Dict = {}

    # ── LOAD / SAVE ───────────────────────────────────────────────────
    @classmethod
    def load(cls):
        if cls._loaded:
            return
        try:
            if os.path.exists(TRAINING_FILE):
                with open(TRAINING_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # VALIDATION: Only merge if file has correct format (trades key)
                    if "trades" in loaded:
                        for k, v in loaded.items():
                            cls._data[k] = v
                        logger.info(f"📚 Training loaded: {len(cls._data.get('trades', []))} trades, "
                                    f"P&L: ${cls._data.get('total_pnl', 0):.2f}")
                    else:
                        logger.warning(f"⚠️ Training file has wrong format (no 'trades' key) — starting fresh. "
                                       f"Keys found: {list(loaded.keys())[:5]}")
                        # Don't merge corrupted data — keep defaults
            cls._loaded = True
            # Train ML model if enough data
            cls._train_ml_model()
        except Exception as e:
            logger.warning(f"Training load error: {e}")
            cls._loaded = True

    @classmethod
    def save(cls):
        try:
            cls._data["trades"] = cls._data["trades"][-cls._MAX_TRADES:]
            # Atomic write: write to temp file first, then rename
            # Prevents data corruption if process crashes mid-write
            dir_path = os.path.dirname(TRAINING_FILE)
            with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                              suffix='.tmp', encoding='utf-8') as tmp:
                json.dump(cls._data, tmp, indent=2, default=str)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp.name, TRAINING_FILE)  # Atomic on all OSes
        except Exception as e:
            logger.warning(f"Training save error: {e}")
            # Clean up temp file if rename failed
            try:
                if 'tmp' in dir() and os.path.exists(tmp.name):
                    os.unlink(tmp.name)
            except Exception:
                pass

    # ── RECORD ENTRY ──────────────────────────────────────────────────
    @classmethod
    def record_entry(cls, snapshot: Dict) -> str:
        cls.load()
        trade_id = f"{snapshot['symbol']}_{snapshot['entry_time']}"
        snapshot["trade_id"] = trade_id
        cls._data["trades"].append(snapshot)
        if len(cls._data["trades"]) % 10 == 0:
            cls.save()
        return trade_id

    # ── RECORD OUTCOME ────────────────────────────────────────────────
    @classmethod
    def record_outcome(cls, symbol: str, direction: str, is_win: bool, pnl: float):
        cls.load()
        for trade in reversed(cls._data["trades"]):
            if (trade["symbol"] == symbol
                    and trade["direction"] == direction
                    and trade.get("outcome") is None):
                trade["outcome"] = "WIN" if is_win else "LOSS"
                trade["pnl"] = round(pnl, 2)
                trade["close_time"] = datetime.utcnow().isoformat()
                cls._data["total_pnl"] = cls._data.get("total_pnl", 0) + pnl
                cls.save()
                cls._learn()  # Statistical learning
                cls._train_ml_model()  # ML learning (if enough data)
                return
        logger.debug(f"No matching entry for {direction} {symbol}")

    # ═══════════════════════════════════════════════════════════════════
    # LEVEL 1: STATISTICAL LEARNING
    # ═══════════════════════════════════════════════════════════════════
    @classmethod
    def _learn(cls):
        resolved = [t for t in cls._data["trades"] if t.get("outcome")]
        if len(resolved) < 2:  # FIXED: was 5 — now learns faster after just 2 trades
            return

        logger.info(f"🎓 LEARNING: Analyzing {len(resolved)} resolved trades for pattern recognition...")

        # 1. SYMBOL STATS
        symbol_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0.0})
        for t in resolved:
            s = symbol_stats[t["symbol"]]
            if t["outcome"] == "WIN":
                s["wins"] += 1
            else:
                s["losses"] += 1
            s["total_pnl"] += t.get("pnl", 0)

        for sym, s in symbol_stats.items():
            total = s["wins"] + s["losses"]
            s["win_rate"] = round(s["wins"] / total * 100, 1) if total > 0 else 50
            s["total"] = total
            s["avg_pnl"] = round(s["total_pnl"] / total, 2) if total > 0 else 0
        cls._data["symbol_stats"] = dict(symbol_stats)

        # 2. SESSION STATS
        session_stats = defaultdict(lambda: defaultdict(lambda: {"w": 0, "l": 0}))
        for t in resolved:
            h = str(t.get("hour_utc", 12))
            sym = t["symbol"]
            session_stats[sym][h]["w" if t["outcome"] == "WIN" else "l"] += 1
        cls._data["session_stats"] = {s: dict(h) for s, h in session_stats.items()}

        # 3. PATTERN ANALYSIS
        patterns = defaultdict(lambda: {"w": 0, "l": 0})
        for t in resolved:
            w = t["outcome"] == "WIN"
            key = "w" if w else "l"

            if t.get("h4_h1_aligned"):
                patterns["h4_aligned"][key] += 1
            else:
                patterns["h4_not_aligned"][key] += 1

            if t.get("killzone", "NONE") != "NONE":
                patterns["killzone"][key] += 1

            if abs(t.get("score", 0)) >= 10:
                patterns["high_score"][key] += 1
            elif abs(t.get("score", 0)) >= 8:
                patterns["mid_score"][key] += 1

            if t.get("institutional_dir") == t.get("direction"):
                patterns["inst_confirm"][key] += 1

            if t.get("amd_phase") == "DISTRIBUTION":
                patterns["amd_dist"][key] += 1

            if t.get("volume_signal", "NORMAL") in ("MASSIVE_INSTITUTIONAL", "HIGH_INSTITUTIONAL"):
                patterns["vol_spike"][key] += 1

            # RSI zones
            rsi = t.get("rsi", 50)
            if rsi < 35:
                patterns["rsi_oversold"][key] += 1
            elif rsi > 65:
                patterns["rsi_overbought"][key] += 1

            # ADX zones
            adx = t.get("adx", 20)
            if adx > 30:
                patterns["strong_trend"][key] += 1
            elif adx < 20:
                patterns["weak_trend"][key] += 1

        cls._data["patterns"] = {k: dict(v) for k, v in patterns.items()}

        # 4. INDICATOR COMBO ANALYSIS — which combos win?
        combo_stats = defaultdict(lambda: {"w": 0, "l": 0})
        for t in resolved:
            w = t["outcome"] == "WIN"
            key = "w" if w else "l"
            # Build combo key from conditions
            parts = []
            if t.get("h4_h1_aligned"):
                parts.append("H4_ALIGNED")
            if t.get("killzone", "NONE") != "NONE":
                parts.append("KILLZONE")
            if t.get("institutional_dir") == t.get("direction"):
                parts.append("INST_CONFIRM")
            if t.get("amd_phase") == "DISTRIBUTION":
                parts.append("AMD_DIST")
            rsi = t.get("rsi", 50)
            if rsi < 35 or rsi > 65:
                parts.append("RSI_EXTREME")
            adx = t.get("adx", 20)
            if adx > 25:
                parts.append("TRENDING")
            if t.get("volume_signal", "NORMAL") != "NORMAL":
                parts.append("VOL_SPIKE")

            if parts:
                combo_key = "+".join(sorted(parts))
                combo_stats[combo_key][key] += 1

        cls._data["combo_stats"] = {k: dict(v) for k, v in combo_stats.items()}

        # 5. AGENT ACCURACY
        agent_stats = defaultdict(lambda: {"correct": 0, "wrong": 0})
        for t in resolved:
            for agent in t.get("agents", []):
                if t["outcome"] == "WIN":
                    agent_stats[agent]["correct"] += 1
                else:
                    agent_stats[agent]["wrong"] += 1
        for a, s in agent_stats.items():
            total = s["correct"] + s["wrong"]
            s["accuracy"] = round(s["correct"] / total * 100, 1) if total > 0 else 50
            s["total"] = total
        cls._data["agent_accuracy"] = dict(agent_stats)

        # 6. ADAPTIVE THRESHOLDS — auto-adjust per symbol
        for sym, s in symbol_stats.items():
            if s["total"] >= 10:
                wr = s["win_rate"]
                if wr < 40:
                    # Losing symbol → raise score threshold
                    cls._data["adaptive_thresholds"][sym] = {
                        "min_score_adj": +3,  # Need 3 more score points
                        "min_conf_adj": +10,  # Need 10% more confidence
                        "reason": f"WR {wr}% < 40% → stricter filters",
                    }
                elif wr > 65:
                    # Winning symbol → can slightly lower threshold
                    cls._data["adaptive_thresholds"][sym] = {
                        "min_score_adj": -1,
                        "min_conf_adj": -5,
                        "reason": f"WR {wr}% > 65% → slightly relaxed",
                    }
                else:
                    cls._data["adaptive_thresholds"][sym] = {
                        "min_score_adj": 0,
                        "min_conf_adj": 0,
                        "reason": f"WR {wr}% normal",
                    }

        # 7. AUTO-DISABLE losing symbols
        blacklist = []
        for sym, s in symbol_stats.items():
            if s["total"] >= 10 and s["win_rate"] < 35:
                blacklist.append(sym)
                logger.warning(f"⛔ AUTO-DISABLE: {sym} blacklisted — {s['win_rate']}% WR after {s['total']} trades")

        # 7b. AUTO-REHABILITATION of previously blacklisted symbols
        # Check if blacklisted symbols have improved to >45% accuracy on last 20 predictions
        current_blacklist = cls._data.get("blacklisted_symbols", [])
        rehabilitated = []
        for sym in current_blacklist:
            if sym not in blacklist:  # Already unblacklisted in this cycle
                continue
            sym_trades = [t for t in resolved if t["symbol"] == sym]
            if len(sym_trades) >= 20:
                recent_trades = sym_trades[-20:]  # Last 20 trades
                recent_wins = sum(1 for t in recent_trades if t.get("outcome") == "WIN")
                recent_wr = round(recent_wins / 20 * 100, 1)
                if recent_wr >= 45:  # Rehabilitation threshold (lowered from 55 for faster recovery)
                    blacklist.remove(sym)
                    rehabilitated.append(sym)
                    logger.warning(f"✅ AUTO-REHABILITATE: {sym} unblacklisted — {recent_wr}% WR on last 20 trades (recovered from <35%)")

        cls._data["blacklisted_symbols"] = blacklist
        cls._data["rehabilitated_symbols"] = rehabilitated

        # 8. BLACKLIST bad session hours
        bad_hours = {}
        for sym, hours in session_stats.items():
            for h, stats in hours.items():
                total = stats["w"] + stats["l"]
                if total >= 5:
                    wr = stats["w"] / total * 100
                    if wr < 30:
                        if sym not in bad_hours:
                            bad_hours[sym] = []
                        bad_hours[sym].append(int(h))
        cls._data["blacklisted_hours"] = bad_hours

        # 9. MARKET REGIME detection per symbol
        regime_stats = {}
        for sym, s in symbol_stats.items():
            sym_trades = [t for t in resolved if t["symbol"] == sym]
            if len(sym_trades) >= 5:
                trending_wins = sum(1 for t in sym_trades if t.get("adx", 0) > 25 and t["outcome"] == "WIN")
                trending_total = sum(1 for t in sym_trades if t.get("adx", 0) > 25)
                ranging_wins = sum(1 for t in sym_trades if t.get("adx", 0) <= 25 and t["outcome"] == "WIN")
                ranging_total = sum(1 for t in sym_trades if t.get("adx", 0) <= 25)

                regime_stats[sym] = {
                    "trending_wr": round(trending_wins / trending_total * 100, 1) if trending_total > 0 else 50,
                    "trending_count": trending_total,
                    "ranging_wr": round(ranging_wins / ranging_total * 100, 1) if ranging_total > 0 else 50,
                    "ranging_count": ranging_total,
                    "best_regime": "TRENDING" if (trending_wins / max(trending_total, 1)) > (ranging_wins / max(ranging_total, 1)) else "RANGING",
                }
        cls._data["regime_stats"] = regime_stats

        cls._data["last_trained"] = datetime.utcnow().isoformat()
        cls.save()

        # Log summary
        total_w = sum(s["wins"] for s in symbol_stats.values())
        total_l = sum(s["losses"] for s in symbol_stats.values())
        total_all = total_w + total_l
        overall_wr = round(total_w / total_all * 100, 1) if total_all > 0 else 0
        logger.info(
            f"📚 TRAINING: {total_all} trades | {overall_wr}% WR | "
            f"Blacklisted: {blacklist or 'none'} | "
            f"ML model: {'active' if cls._ml_model else 'insufficient data'}"
        )

    # ═══════════════════════════════════════════════════════════════════
    # LEVEL 2: ML PATTERN RECOGNITION (XGBoost/LightGBM Ensemble)
    # ═══════════════════════════════════════════════════════════════════

    FEATURE_NAMES = [
        "score", "confidence", "rsi", "adx", "hour", "inst_conf",
        "h4_aligned", "killzone", "inst_confirm", "amd_dist",
        "vol_spike", "news_confirm", "is_buy",
    ]

    @classmethod
    def _extract_features(cls, t: Dict) -> list:
        """Extract ML features from a trade snapshot (shared by train + predict)."""
        news_match = t.get("news") == t.get("direction", "").replace("BUY", "BULLISH").replace("SELL", "BEARISH")
        return [
            t.get("score", 0),
            t.get("confidence", 50),
            t.get("rsi", 50),
            t.get("adx", 20),
            t.get("hour_utc", 12),
            t.get("institutional_conf", 50),
            1 if t.get("h4_h1_aligned") else 0,
            1 if t.get("killzone", "NONE") != "NONE" else 0,
            1 if t.get("institutional_dir") == t.get("direction") else 0,
            1 if t.get("amd_phase") == "DISTRIBUTION" else 0,
            1 if t.get("volume_signal", "NORMAL") != "NORMAL" else 0,
            1 if news_match else 0,
            1 if t.get("direction") == "BUY" else 0,
        ]

    @classmethod
    def _train_ml_model(cls):
        """
        Train ML ensemble model with CROSS-VALIDATION to prevent overfitting.
        Uses XGBoost > LightGBM > DecisionTree (fallback chain).
        Ensemble voting combines multiple models for robustness.
        """
        if not ML_AVAILABLE:
            return

        resolved = [t for t in cls._data.get("trades", []) if t.get("outcome")]
        if len(resolved) < 50:
            return  # Need 50+ trades for meaningful ML

        try:
            features = [cls._extract_features(t) for t in resolved]
            labels = [1 if t["outcome"] == "WIN" else 0 for t in resolved]

            X = np.array(features)
            y = np.array(labels)

            # Check class balance
            win_count = sum(y)
            loss_count = len(y) - win_count
            if win_count < 5 or loss_count < 5:
                logger.info(f"ML: Insufficient class balance (W:{win_count}/L:{loss_count})")
                return

            scale_pos_weight = loss_count / max(win_count, 1)

            # ── BUILD MODELS BASED ON AVAILABLE ENGINE ──
            models = []

            if ML_ENGINE == "xgboost":
                # XGBoost: Best gradient boosting, handles overfitting well
                model_xgb = XGBClassifier(
                    n_estimators=100,
                    max_depth=4,              # Shallow trees = less overfitting
                    learning_rate=0.1,
                    min_child_weight=5,       # Minimum samples per leaf
                    subsample=0.8,            # Row sampling (anti-overfit)
                    colsample_bytree=0.8,     # Feature sampling (anti-overfit)
                    reg_alpha=0.1,            # L1 regularization
                    reg_lambda=1.0,           # L2 regularization
                    scale_pos_weight=scale_pos_weight,
                    random_state=42,
                    use_label_encoder=False,
                    eval_metric='logloss',
                    verbosity=0,
                )
                models.append(("xgb", model_xgb))

            elif ML_ENGINE == "lightgbm":
                # LightGBM: Faster than XGBoost, similar quality
                model_lgbm = LGBMClassifier(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.1,
                    min_child_samples=5,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.1,
                    reg_lambda=1.0,
                    scale_pos_weight=scale_pos_weight,
                    random_state=42,
                    verbose=-1,
                )
                models.append(("lgbm", model_lgbm))

            # Always add DecisionTree as secondary model for ensemble
            model_dt = DecisionTreeClassifier(
                max_depth=5,
                min_samples_leaf=5,
                min_samples_split=10,
                random_state=42,
            )
            models.append(("dt", model_dt))

            # ── CROSS-VALIDATION (5-fold stratified) ──
            # This is the KEY fix for overfitting
            cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
            cv_scores = {}
            best_model = None
            best_cv_score = 0

            for name, model in models:
                try:
                    scores = cross_val_score(model, X, y, cv=cv, scoring='accuracy')
                    mean_score = round(np.mean(scores) * 100, 1)
                    std_score = round(np.std(scores) * 100, 1)
                    cv_scores[name] = {
                        "mean": mean_score,
                        "std": std_score,
                        "folds": [round(s * 100, 1) for s in scores],
                    }
                    logger.info(
                        f"  ML CV [{name}]: {mean_score}% +/- {std_score}% "
                        f"(folds: {cv_scores[name]['folds']})"
                    )
                    if mean_score > best_cv_score:
                        best_cv_score = mean_score
                        best_model = (name, model)
                except Exception as e:
                    logger.debug(f"  ML CV [{name}] error: {e}")

            if best_model is None:
                logger.warning("ML: All models failed cross-validation")
                return

            # ── ENSEMBLE VOTING (if 2+ models available) ──
            if len(models) >= 2:
                try:
                    ensemble = VotingClassifier(
                        estimators=models,
                        voting='soft',  # Probability-based voting
                    )
                    ensemble_scores = cross_val_score(ensemble, X, y, cv=cv, scoring='accuracy')
                    ensemble_mean = round(np.mean(ensemble_scores) * 100, 1)
                    ensemble_std = round(np.std(ensemble_scores) * 100, 1)
                    cv_scores["ensemble"] = {
                        "mean": ensemble_mean,
                        "std": ensemble_std,
                    }

                    # Use ensemble if it beats individual models
                    if ensemble_mean >= best_cv_score:
                        ensemble.fit(X, y)
                        cls._ml_model = ensemble
                        cls._data["ml_model_accuracy"] = ensemble_mean
                        cls._data["ml_cv_std"] = ensemble_std
                        cls._data["ml_engine"] = "ensemble"
                        logger.info(
                            f"🤖 ML ENSEMBLE TRAINED: {ensemble_mean}% +/- {ensemble_std}% CV "
                            f"(beat best individual: {best_cv_score}%)"
                        )
                    else:
                        # Use best individual model
                        best_name, best_m = best_model
                        best_m.fit(X, y)
                        cls._ml_model = best_m
                        cls._data["ml_model_accuracy"] = best_cv_score
                        cls._data["ml_cv_std"] = cv_scores.get(best_name, {}).get("std", 0)
                        cls._data["ml_engine"] = best_name
                except Exception:
                    # Fallback to best individual
                    best_name, best_m = best_model
                    best_m.fit(X, y)
                    cls._ml_model = best_m
                    cls._data["ml_model_accuracy"] = best_cv_score
                    cls._data["ml_engine"] = best_name
            else:
                best_name, best_m = best_model
                best_m.fit(X, y)
                cls._ml_model = best_m
                cls._data["ml_model_accuracy"] = best_cv_score
                cls._data["ml_engine"] = best_name

            # ── FEATURE IMPORTANCE (from best tree-based model) ──
            try:
                # Get feature importances from a tree-based model
                imp_model = None
                for name, m in models:
                    if hasattr(m, 'feature_importances_'):
                        m.fit(X, y)  # Ensure fitted
                        imp_model = m
                        break

                if imp_model is not None and hasattr(imp_model, 'feature_importances_'):
                    importances = imp_model.feature_importances_
                    top_features = sorted(
                        zip(cls.FEATURE_NAMES, importances),
                        key=lambda x: x[1], reverse=True
                    )[:5]
                    cls._data["ml_top_features"] = [
                        {"name": n, "importance": round(imp * 100, 1)}
                        for n, imp in top_features
                    ]
            except Exception:
                pass

            # Store CV scores for analysis
            cls._data["ml_cv_scores"] = cv_scores
            cls._data["ml_engine_used"] = cls._data.get("ml_engine", ML_ENGINE)

            logger.info(
                f"🤖 ML TRAINING COMPLETE: Engine={cls._data.get('ml_engine', '?')} | "
                f"CV={cls._data.get('ml_model_accuracy', 0)}% | "
                f"Trades={len(resolved)} | "
                f"Top: {', '.join(f['name'] for f in cls._data.get('ml_top_features', [])[:3])}"
            )

        except Exception as e:
            logger.warning(f"ML training error: {e}")
            cls._ml_model = None

    @classmethod
    def ml_predict(cls, snapshot: Dict) -> Dict:
        """
        Use ML ensemble model to predict WIN probability for a trade setup.
        Returns: {"win_prob": 0.0-1.0, "prediction": "WIN"/"LOSS", "confidence_adj": int,
                  "engine": str, "cv_accuracy": float}
        """
        if not ML_AVAILABLE or cls._ml_model is None:
            return {"win_prob": 0.5, "prediction": "UNKNOWN", "confidence_adj": 0, "available": False}

        try:
            f = np.array([cls._extract_features(snapshot)])

            win_prob = cls._ml_model.predict_proba(f)[0][1]  # Probability of class 1 (WIN)
            prediction = "WIN" if win_prob >= 0.55 else "LOSS"

            # Confidence adjustment based on prediction
            if win_prob >= 0.70:
                conf_adj = +8
            elif win_prob >= 0.60:
                conf_adj = +4
            elif win_prob <= 0.35:
                conf_adj = -10
            elif win_prob <= 0.45:
                conf_adj = -5
            else:
                conf_adj = 0

            return {
                "win_prob": round(win_prob, 3),
                "prediction": prediction,
                "confidence_adj": conf_adj,
                "available": True,
                "engine": cls._data.get("ml_engine", ML_ENGINE),
                "cv_accuracy": cls._data.get("ml_model_accuracy", 0),
            }

        except Exception as e:
            logger.debug(f"ML predict error: {e}")
            return {"win_prob": 0.5, "prediction": "UNKNOWN", "confidence_adj": 0, "available": False}

    # ═══════════════════════════════════════════════════════════════════
    # LEVEL 3: GET LEARNED ADJUSTMENTS (used by main.py)
    # ═══════════════════════════════════════════════════════════════════
    @classmethod
    def get_confidence_adjustment(cls, symbol: str, direction: str,
                                   hour_utc: int, h4_aligned: bool,
                                   score: int, killzone: str,
                                   institutional_match: bool) -> Dict:
        """Get confidence adjustments from all learning levels."""
        cls.load()
        adj = 0
        reasons = []

        # ── Check blacklisted symbol ──
        if symbol in cls._data.get("blacklisted_symbols", []):
            return {
                "adjustment": -50,  # Devastating penalty = effectively blocks trade
                "reasons": [f"⛔ {symbol} BLACKLISTED by training — <35% WR, avoid this pair"],
                "symbol_wr": cls._data.get("symbol_stats", {}).get(symbol, {}).get("win_rate", 0),
                "blocked": True,
            }

        # ── Check blacklisted hour ──
        bad_hours = cls._data.get("blacklisted_hours", {}).get(symbol, [])
        if hour_utc in bad_hours:
            adj -= 15
            reasons.append(f"📚 {symbol} at {hour_utc}:xx UTC has <30% WR — bad session (-15)")

        # ── Adaptive threshold ──
        thresh = cls._data.get("adaptive_thresholds", {}).get(symbol, {})
        if thresh.get("min_score_adj", 0) != 0:
            adj += thresh.get("min_conf_adj", 0)
            reasons.append(f"📚 Adaptive: {thresh.get('reason', '')}")

        # ── Symbol win rate ──
        sym_stats = cls._data.get("symbol_stats", {}).get(symbol, {})
        if sym_stats.get("total", 0) >= 5:
            wr = sym_stats.get("win_rate", 50)
            if wr >= 65:
                adj += 5
                reasons.append(f"📚 {symbol} strong: {wr}% WR (+5)")
            elif wr <= 40:
                adj -= 8
                reasons.append(f"📚 {symbol} weak: {wr}% WR (-8)")

        # ── Session hour ──
        sess = cls._data.get("session_stats", {}).get(symbol, {}).get(str(hour_utc), {})
        if sess:
            hw = sess.get("w", 0)
            hl = sess.get("l", 0)
            ht = hw + hl
            if ht >= 3:
                hwr = hw / ht * 100
                if hwr >= 70:
                    adj += 3
                    reasons.append(f"📚 {symbol} @{hour_utc}h: {hwr:.0f}% WR (+3)")
                elif hwr <= 30:
                    adj -= 5
                    reasons.append(f"📚 {symbol} @{hour_utc}h: {hwr:.0f}% WR (-5)")

        # ── Pattern bonuses ──
        patterns = cls._data.get("patterns", {})
        if h4_aligned:
            p = patterns.get("h4_aligned", {})
            pw = p.get("w", 0)
            pt = pw + p.get("l", 0)
            if pt >= 5:
                pwr = pw / pt * 100
                if pwr >= 60:
                    adj += 3
                    reasons.append(f"📚 H4-aligned: {pwr:.0f}% WR (+3)")

        if killzone != "NONE":
            p = patterns.get("killzone", {})
            pw = p.get("w", 0)
            pt = pw + p.get("l", 0)
            if pt >= 5 and (pw / pt * 100) >= 60:
                adj += 2
                reasons.append(f"📚 Killzone: {pw/pt*100:.0f}% WR (+2)")

        if institutional_match:
            p = patterns.get("inst_confirm", {})
            pw = p.get("w", 0)
            pt = pw + p.get("l", 0)
            if pt >= 5 and (pw / pt * 100) >= 55:
                adj += 3
                reasons.append(f"📚 Institutional match: {pw/pt*100:.0f}% WR (+3)")

        # ── Market regime check ──
        regime = cls._data.get("regime_stats", {}).get(symbol, {})
        if regime:
            best = regime.get("best_regime", "TRENDING")
            reasons.append(f"📚 {symbol} best in {best} markets")

        return {
            "adjustment": adj,
            "reasons": reasons,
            "symbol_wr": sym_stats.get("win_rate", 50),
            "blocked": False,
        }

    # ── Check if symbol is tradeable ──────────────────────────────────
    @classmethod
    def is_symbol_allowed(cls, symbol: str) -> bool:
        """Check if training system hasn't blacklisted this symbol."""
        cls.load()
        return symbol not in cls._data.get("blacklisted_symbols", [])

    @classmethod
    def is_hour_allowed(cls, symbol: str, hour_utc: int) -> bool:
        """Check if this hour isn't blacklisted for this symbol."""
        cls.load()
        bad = cls._data.get("blacklisted_hours", {}).get(symbol, [])
        return hour_utc not in bad

    @classmethod
    def get_best_combos(cls, top_n: int = 5) -> List[Dict]:
        """Return the best performing indicator combos."""
        cls.load()
        combos = cls._data.get("combo_stats", {})
        results = []
        for combo, stats in combos.items():
            total = stats.get("w", 0) + stats.get("l", 0)
            if total >= 3:
                wr = stats["w"] / total * 100
                results.append({"combo": combo, "wr": round(wr, 1), "total": total})
        results.sort(key=lambda x: x["wr"], reverse=True)
        return results[:top_n]

    # ── REPORTING ─────────────────────────────────────────────────────
    @classmethod
    def report(cls) -> str:
        cls.load()
        resolved = [t for t in cls._data.get("trades", []) if t.get("outcome")]
        if not resolved:
            return "📚 No training data yet"

        wins = sum(1 for t in resolved if t["outcome"] == "WIN")
        total = len(resolved)
        wr = wins / total * 100 if total > 0 else 0
        pnl = cls._data.get("total_pnl", 0)

        lines = [
            f"📚 TRAINING: {total} trades | {wr:.1f}% WR | P&L: ${pnl:.2f}",
            "",
        ]

        # Symbol breakdown
        sym_stats = cls._data.get("symbol_stats", {})
        if sym_stats:
            lines.append("PER-SYMBOL:")
            for sym, s in sorted(sym_stats.items(), key=lambda x: x[1].get("win_rate", 0), reverse=True):
                icon = "🟢" if s.get("win_rate", 0) >= 55 else "🔴" if s.get("win_rate", 0) < 45 else "🟡"
                bl = " ⛔DISABLED" if sym in cls._data.get("blacklisted_symbols", []) else ""
                lines.append(
                    f"  {icon} {sym}: {s.get('win_rate', 0)}% "
                    f"({s.get('wins', 0)}W/{s.get('losses', 0)}L) ${s.get('total_pnl', 0):.2f}{bl}"
                )

        # Best combos
        combos = cls.get_best_combos(3)
        if combos:
            lines.append("")
            lines.append("BEST COMBOS:")
            for c in combos:
                lines.append(f"  🏆 {c['combo']}: {c['wr']}% WR ({c['total']} trades)")

        # ML model
        if cls._ml_model:
            lines.append("")
            lines.append(f"ML MODEL: {cls._data.get('ml_model_accuracy', 0)}% accuracy")
            for f in cls._data.get("ml_top_features", [])[:3]:
                lines.append(f"  📊 {f['name']}: {f['importance']}% importance")

        # Blacklists
        bl = cls._data.get("blacklisted_symbols", [])
        if bl:
            lines.append(f"\n⛔ DISABLED SYMBOLS: {', '.join(bl)}")

        return "\n".join(lines)


    # ═══════════════════════════════════════════════════════════════════
    # CONTINUOUS TRAINING — Periodic re-analysis (called from main loop)
    # ═══════════════════════════════════════════════════════════════════
    @classmethod
    def run_continuous_learning(cls) -> dict:
        """
        Periodic re-analysis of all training data. Call every 15-30 min.
        Unlike record_outcome (which learns after each trade), this:
          1. Re-runs _learn() on ALL resolved trades (finds new patterns)
          2. Re-trains ML model (benefits from accumulated data)
          3. Updates adaptive thresholds
          4. Prunes stale blacklists (symbol improving? un-blacklist it)
        Returns summary dict for dashboard display.
        """
        cls.load()
        resolved = [t for t in cls._data.get("trades", []) if t.get("outcome")]
        if len(resolved) < 2:
            return {"status": "insufficient_data", "trades": 0}

        logger.info(f"🔄 CONTINUOUS LEARNING: Re-analyzing {len(resolved)} trades...")

        # Re-run all learning
        cls._learn()
        cls._train_ml_model()

        # ── Prune stale blacklists ──
        # If a blacklisted symbol's recent 5 trades show >45% WR, un-blacklist it
        blacklisted = cls._data.get("blacklisted_symbols", [])
        un_blacklisted = []
        for sym in list(blacklisted):
            sym_trades = [t for t in resolved if t["symbol"] == sym]
            recent = sym_trades[-5:] if len(sym_trades) >= 5 else sym_trades
            if len(recent) >= 3:
                recent_wr = sum(1 for t in recent if t["outcome"] == "WIN") / len(recent) * 100
                if recent_wr >= 45:
                    blacklisted.remove(sym)
                    un_blacklisted.append(sym)
                    logger.info(f"🟢 UN-BLACKLISTED: {sym} — recent WR {recent_wr:.0f}% (improved)")
        cls._data["blacklisted_symbols"] = blacklisted

        # ── Update regime detection ──
        # Check if market conditions have shifted
        for sym in set(t["symbol"] for t in resolved):
            sym_trades = [t for t in resolved if t["symbol"] == sym]
            recent_10 = sym_trades[-10:] if len(sym_trades) >= 10 else sym_trades
            if len(recent_10) >= 5:
                # Trending: H4-aligned trades dominate
                aligned_count = sum(1 for t in recent_10 if t.get("h4_h1_aligned"))
                regime = "TRENDING" if aligned_count / len(recent_10) > 0.6 else "RANGING"
                if "regime_stats" not in cls._data:
                    cls._data["regime_stats"] = {}
                cls._data["regime_stats"][sym] = {
                    "current_regime": regime,
                    "aligned_pct": round(aligned_count / len(recent_10) * 100, 1),
                    "best_regime": regime,
                    "updated": datetime.utcnow().isoformat(),
                }

        cls.save()

        total = len(resolved)
        wins = sum(1 for t in resolved if t["outcome"] == "WIN")
        wr = round(wins / total * 100, 1) if total > 0 else 0

        result = {
            "status": "success",
            "trades": total,
            "win_rate": wr,
            "ml_active": cls._ml_model is not None,
            "ml_accuracy": cls._data.get("ml_model_accuracy", 0),
            "blacklisted": cls._data.get("blacklisted_symbols", []),
            "un_blacklisted": un_blacklisted,
            "regimes": {s: r.get("current_regime", "?") for s, r in cls._data.get("regime_stats", {}).items()},
        }

        logger.info(
            f"🔄 CONTINUOUS LEARNING DONE: {total} trades, {wr}% WR, "
            f"ML: {'active' if cls._ml_model else 'inactive'}, "
            f"Un-blacklisted: {un_blacklisted or 'none'}"
        )
        return result


def _wr(patterns: dict, prefix: str) -> float:
    p = patterns.get(prefix, {})
    w = p.get("w", 0)
    l = p.get("l", 0)
    total = w + l
    return (w / total * 100) if total > 0 else 50.0
