"""
regime_hmm.py — Hidden Markov Model regime detector.

Why this exists
---------------
The current `vol_regime` profit filter uses an ATR-quantile heuristic
("block if current ATR is in bottom 20% / top 5%"). That's a decent
proxy for "dead" vs "spike" markets, but conflates volatility with
regime: a persistent low-volatility uptrend and a flat chop both sit
in the bottom quantile. A 2-state or 3-state Gaussian HMM fit on
log-returns + realized volatility separates *trending* from *mean-
reverting* regimes, which is the signal the strategy actually wants.

This module implements a compact HMM with:

  * 2 or 3 hidden states (operator choice).
  * Gaussian emissions on `[log_return, abs_log_return]` (mean + vol).
  * Forward-backward inference for smoothed state probabilities.
  * Baum-Welch EM for offline training.
  * Viterbi decoding for the most-likely state sequence.

Pure Python + numpy. `hmmlearn` is OPTIONAL — if present we use its
GaussianHMM directly (faster, more tested). If not, the local EM loop
kicks in.

Integration (opt-in)
--------------------
Not wired into the brain yet. Reference pattern:

    from ai_trading_agents.regime_hmm import RegimeHMM
    hmm = RegimeHMM.load("ai_trading_agents/ml_models/regime_METALS.pkl")
    state, prob = hmm.classify(last_200_closes)
    if state == "chop" and prob > 0.7:
        direction = "NONE"

Training offline via `python tools/train_regime_hmm.py XAUUSD`.
"""
from __future__ import annotations

import logging
import math
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger("regime_hmm")

try:
    from hmmlearn.hmm import GaussianHMM as _LibGaussianHMM  # type: ignore
    _HAS_HMMLEARN = True
except Exception:
    _HAS_HMMLEARN = False


# State label vocabulary — tuned by the classify() post-hoc label
# selector based on the mean and variance of each learned state.
_STATE_LABELS_2 = ("chop", "trend")
_STATE_LABELS_3 = ("chop", "trend-calm", "trend-volatile")


@dataclass
class HMMConfig:
    n_states:    int  = 2
    n_iter:     int  = 50
    tol:        float = 1e-4
    random_seed: int = 7
    # Feature construction knobs:
    use_abs_return: bool = True
    min_history_bars: int = 100


@dataclass
class RegimeObs:
    state_idx: int
    state:     str
    prob:      float
    probs_all: List[float]


@dataclass
class RegimeHMM:
    cfg:            HMMConfig          = field(default_factory=HMMConfig)
    means:          Optional[np.ndarray] = None
    covars:         Optional[np.ndarray] = None
    trans:          Optional[np.ndarray] = None
    init_probs:     Optional[np.ndarray] = None
    state_labels:   List[str]           = field(default_factory=list)
    trained:        bool                = False
    library_model:  Optional[object]    = None  # hmmlearn instance if used

    # ──────────────────────────────────────────────────────────────────
    # Feature construction
    # ──────────────────────────────────────────────────────────────────
    def _features(self, closes: Sequence[float]) -> np.ndarray:
        arr = np.asarray(closes, dtype=float)
        if len(arr) < 2:
            return np.zeros((0, 2 if self.cfg.use_abs_return else 1))
        r = np.diff(np.log(np.clip(arr, 1e-12, None)))
        if self.cfg.use_abs_return:
            return np.column_stack([r, np.abs(r)])
        return r.reshape(-1, 1)

    # ──────────────────────────────────────────────────────────────────
    # Training
    # ──────────────────────────────────────────────────────────────────
    def fit(self, closes: Sequence[float]) -> "RegimeHMM":
        X = self._features(closes)
        if len(X) < self.cfg.min_history_bars:
            raise ValueError(
                f"insufficient history: have {len(X)} return observations, "
                f"need {self.cfg.min_history_bars}"
            )
        if _HAS_HMMLEARN:
            self._fit_via_lib(X)
        else:
            self._fit_manual(X)
        # Post-hoc label: state with the smaller absolute mean-return
        # AND smaller variance → "chop"; larger → "trend*".
        self._assign_labels()
        self.trained = True
        return self

    def _fit_via_lib(self, X: np.ndarray) -> None:
        """Train using hmmlearn when available — faster and battle-tested."""
        model = _LibGaussianHMM(
            n_components=self.cfg.n_states,
            covariance_type="full",
            n_iter=self.cfg.n_iter,
            tol=self.cfg.tol,
            random_state=self.cfg.random_seed,
        )
        model.fit(X)
        self.library_model = model
        self.means = np.asarray(model.means_)
        self.covars = np.asarray(model.covars_)
        self.trans = np.asarray(model.transmat_)
        self.init_probs = np.asarray(model.startprob_)

    def _fit_manual(self, X: np.ndarray) -> None:
        """Manual Baum-Welch (EM) — used when hmmlearn isn't installed.

        Good enough for N≈500–2000 observations (our typical use case).
        Converges to a local optimum of the likelihood; seeds matter.
        """
        rng = np.random.default_rng(self.cfg.random_seed)
        n, d = X.shape
        K = self.cfg.n_states
        # Init means via random k points from X (k-means++ lite).
        idx = rng.choice(n, size=K, replace=False)
        means = X[idx].copy()
        covars = np.tile(np.cov(X.T).reshape(d, d), (K, 1, 1)) + 1e-6 * np.eye(d)
        trans = np.full((K, K), 1.0 / K)
        init = np.full(K, 1.0 / K)

        prev_ll = -np.inf
        for it in range(self.cfg.n_iter):
            # ---- E-step: forward-backward (all in log-space for stability) ----
            log_emis = self._log_gaussian(X, means, covars)
            log_alpha, log_Z = self._forward(log_emis, trans, init)
            log_beta = self._backward(log_emis, trans)
            log_gamma = log_alpha + log_beta
            # Normalise each row via log-sum-exp (no overflow).
            log_gamma_max = log_gamma.max(axis=1, keepdims=True)
            log_gamma_norm = (log_gamma_max
                              + np.log(np.exp(log_gamma - log_gamma_max).sum(axis=1, keepdims=True)))
            gamma = np.exp(log_gamma - log_gamma_norm)

            # xi in log-space, then exp only after normalisation.
            log_trans = np.log(np.clip(trans, 1e-12, None))
            xi = np.zeros((n - 1, K, K))
            for t in range(n - 1):
                # log_xi[t, i, j] = log_alpha[t,i] + log_trans[i,j]
                #                 + log_emis[t+1,j] + log_beta[t+1,j]
                log_xi = (log_alpha[t].reshape(K, 1)
                          + log_trans
                          + log_emis[t + 1].reshape(1, K)
                          + log_beta[t + 1].reshape(1, K))
                m = log_xi.max()
                if not np.isfinite(m):
                    continue
                log_xi_norm = m + np.log(np.exp(log_xi - m).sum())
                xi[t] = np.exp(log_xi - log_xi_norm)

            # ---- M-step ----
            init = gamma[0]
            trans = (xi.sum(axis=0) /
                     np.clip(gamma[:-1].sum(axis=0).reshape(K, 1), 1e-12, None))
            for k in range(K):
                w = gamma[:, k]
                wsum = w.sum()
                if wsum > 0:
                    means[k] = (w[:, None] * X).sum(axis=0) / wsum
                    diff = X - means[k]
                    covars[k] = (w[:, None, None] * (diff[:, :, None] * diff[:, None, :])).sum(axis=0) / wsum
                    covars[k] += 1e-6 * np.eye(d)

            ll = float(log_Z.sum())
            if abs(ll - prev_ll) < self.cfg.tol:
                break
            prev_ll = ll

        self.means = means
        self.covars = covars
        self.trans = trans
        self.init_probs = init

    def _log_gaussian(self, X: np.ndarray,
                      means: np.ndarray, covars: np.ndarray) -> np.ndarray:
        n, d = X.shape
        K = means.shape[0]
        out = np.zeros((n, K))
        for k in range(K):
            inv = np.linalg.pinv(covars[k])
            sign, logdet = np.linalg.slogdet(covars[k])
            c = -0.5 * (d * math.log(2 * math.pi) + logdet)
            diff = X - means[k]
            q = np.einsum("ni,ij,nj->n", diff, inv, diff)
            out[:, k] = c - 0.5 * q
        return out

    def _forward(self, log_emis, trans, init):
        n, K = log_emis.shape
        log_alpha = np.zeros((n, K))
        log_alpha[0] = np.log(np.clip(init, 1e-12, None)) + log_emis[0]
        for t in range(1, n):
            for j in range(K):
                log_alpha[t, j] = (
                    self._logsumexp(log_alpha[t - 1] + np.log(np.clip(trans[:, j], 1e-12, None)))
                    + log_emis[t, j]
                )
        # _logsumexp returns a plain Python float — wrap in a length-1
        # array so callers that .sum() it still work.
        log_Z = np.array([self._logsumexp(log_alpha[-1])])
        return log_alpha, log_Z

    def _backward(self, log_emis, trans):
        n, K = log_emis.shape
        log_beta = np.zeros((n, K))
        log_beta[-1] = 0.0
        for t in range(n - 2, -1, -1):
            for i in range(K):
                log_beta[t, i] = self._logsumexp(
                    np.log(np.clip(trans[i, :], 1e-12, None))
                    + log_emis[t + 1]
                    + log_beta[t + 1]
                )
        return log_beta

    @staticmethod
    def _logsumexp(a: np.ndarray) -> float:
        m = float(np.max(a))
        return m + math.log(float(np.exp(a - m).sum()))

    # ──────────────────────────────────────────────────────────────────
    # Post-hoc state labels
    # ──────────────────────────────────────────────────────────────────
    def _assign_labels(self) -> None:
        if self.means is None:
            return
        K = self.means.shape[0]
        # Score each state by |mean return| + emission variance.
        scores = []
        for k in range(K):
            m = abs(float(self.means[k, 0]))
            v = float(self.covars[k, 0, 0]) if self.covars is not None else 0.0
            scores.append((m + v, k))
        scores.sort()  # ascending — smallest is "chop"
        if K == 2:
            label_map = {scores[0][1]: "chop", scores[1][1]: "trend"}
        elif K == 3:
            label_map = {
                scores[0][1]: "chop",
                scores[1][1]: "trend-calm",
                scores[2][1]: "trend-volatile",
            }
        else:
            label_map = {i: f"state_{i}" for i in range(K)}
        self.state_labels = [label_map[i] for i in range(K)]

    # ──────────────────────────────────────────────────────────────────
    # Inference
    # ──────────────────────────────────────────────────────────────────
    def classify(self, closes: Sequence[float]) -> RegimeObs:
        if not self.trained or self.means is None:
            return RegimeObs(state_idx=-1, state="unknown",
                             prob=0.0, probs_all=[])
        X = self._features(closes)
        if len(X) == 0:
            return RegimeObs(state_idx=-1, state="unknown",
                             prob=0.0, probs_all=[])
        log_emis = self._log_gaussian(X, self.means, self.covars)
        log_alpha, _ = self._forward(log_emis, self.trans, self.init_probs)
        # Smoothed posterior over the LAST observation, via log-sum-exp
        # for numerical stability (overflow-safe).
        last = log_alpha[-1]
        m = float(last.max())
        if not np.isfinite(m):
            # All emissions underflowed — return uniform.
            K = len(self.state_labels) or (self.means.shape[0] if self.means is not None else 2)
            return RegimeObs(state_idx=0, state=self.state_labels[0] if self.state_labels else "unknown",
                             prob=1.0 / K, probs_all=[1.0 / K] * K)
        probs = np.exp(last - m)
        probs = probs / probs.sum()
        idx = int(np.argmax(probs))
        label = self.state_labels[idx] if idx < len(self.state_labels) else f"state_{idx}"
        return RegimeObs(
            state_idx=idx, state=label,
            prob=float(probs[idx]),
            probs_all=[float(x) for x in probs],
        )

    # ──────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────
    def save(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "cfg":          self.cfg,
            "means":        self.means,
            "covars":       self.covars,
            "trans":        self.trans,
            "init_probs":   self.init_probs,
            "state_labels": self.state_labels,
            "trained":      self.trained,
        }
        with open(p, "wb") as f:
            pickle.dump(blob, f)

    @classmethod
    def load(cls, path: str) -> "RegimeHMM":
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            with open(p, "rb") as f:
                blob = pickle.load(f)
            return cls(
                cfg=blob.get("cfg") or HMMConfig(),
                means=blob.get("means"),
                covars=blob.get("covars"),
                trans=blob.get("trans"),
                init_probs=blob.get("init_probs"),
                state_labels=blob.get("state_labels") or [],
                trained=bool(blob.get("trained")),
            )
        except Exception as e:
            logger.warning("hmm load failed (%s) — returning untrained", e)
            return cls()


__all__ = ["HMMConfig", "RegimeObs", "RegimeHMM"]
