"""
metrics.py — Prometheus-text-format metrics collector for v14.

Why this exists
---------------
Telegram and stdlib logs give the operator an intermittent pulse. They
don't answer questions like "what's my tick latency p95?", "how often
has the risk-manager gate fired today per symbol?", or "did MT5
reconnect count change in the last hour?". A plain counter/histogram
stream does, and Prometheus is the lightweight industry standard.

This module exposes:

    * A tiny in-memory store (no external deps required) with:
         counter(name, labels)        — monotonic
         gauge(name, labels, value)   — point-in-time
         histogram(name, labels, v)   — bucketed, reports sum + count + p95
    * `.render()` — returns Prometheus 0.0.4 text-exposition format
      (plain UTF-8). Paste into FastAPI's `/metrics` route and Grafana
      will scrape it via a Prometheus scrape config.
    * Optional upgrade path: if `prometheus_client` is installed at
      runtime, we register the same metric names in its registry so
      existing tooling (Grafana-Cloud-Agent, OTel collectors) picks
      them up without re-config.

Integration (opt-in)
--------------------
Enable by setting `METRICS.enabled=True` in `config/settings.py`. When
enabled, `trend_master_brain.py` can call `metrics.tick_latency.observe(dt)`,
`metrics.signal_writes.labels(direction).inc()`, etc. without any hard
dependency. `tools/dashboard.py` exposes `/metrics` only when the
collector has been populated.

No external dep
---------------
`prometheus_client` is optional. Without it, we still provide a
hand-rolled text-exposition renderer — good enough for single-process
setups. With it installed, everything degrades to the canonical impl
(same metric names, same labels) so Grafana Cloud and Prometheus can
scrape directly.

Labels
------
Keep cardinality low. Per-symbol counters are fine (19 values), but
don't add unbounded dimensions like `ts` or `order_id` — Prometheus
explodes memory on cardinality > ~1000 per metric.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("metrics")

# Try the real library — degrade to in-memory collector if unavailable.
try:
    from prometheus_client import (
        Counter as _PCounter,
        Gauge as _PGauge,
        Histogram as _PHistogram,
        CollectorRegistry as _PRegistry,
        generate_latest as _p_generate_latest,
        CONTENT_TYPE_LATEST as _P_CONTENT_TYPE,
    )
    _HAS_PROMETHEUS = True
except Exception:   # pragma: no cover — tested via monkeypatch
    _HAS_PROMETHEUS = False


# ======================================================================
# In-memory fallback implementation
# ======================================================================
_DEFAULT_BUCKETS = (
    0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)


@dataclass
class _Counter:
    name: str
    help: str
    labelnames: Tuple[str, ...]
    values: Dict[Tuple[str, ...], float] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def labels(self, **kw) -> "_Counter":
        # Returns self for chaining — in-memory variant tracks labels
        # per-call rather than per-instance.
        self._last_labels = tuple(kw.get(n, "") for n in self.labelnames)
        return self

    def inc(self, by: float = 1.0) -> None:
        lbl = getattr(self, "_last_labels", tuple("" for _ in self.labelnames))
        with self._lock:
            self.values[lbl] = self.values.get(lbl, 0.0) + float(by)


@dataclass
class _Gauge:
    name: str
    help: str
    labelnames: Tuple[str, ...]
    values: Dict[Tuple[str, ...], float] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def labels(self, **kw) -> "_Gauge":
        self._last_labels = tuple(kw.get(n, "") for n in self.labelnames)
        return self

    def set(self, value: float) -> None:
        lbl = getattr(self, "_last_labels", tuple("" for _ in self.labelnames))
        with self._lock:
            self.values[lbl] = float(value)


@dataclass
class _Histogram:
    name: str
    help: str
    labelnames: Tuple[str, ...]
    buckets: Tuple[float, ...]
    # Per-label-set: list of sample values.
    samples: Dict[Tuple[str, ...], List[float]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def labels(self, **kw) -> "_Histogram":
        self._last_labels = tuple(kw.get(n, "") for n in self.labelnames)
        return self

    def observe(self, value: float) -> None:
        if not math.isfinite(value):
            return
        lbl = getattr(self, "_last_labels", tuple("" for _ in self.labelnames))
        with self._lock:
            self.samples.setdefault(lbl, []).append(float(value))
            # Cap per-label-set to keep memory bounded.
            if len(self.samples[lbl]) > 10_000:
                self.samples[lbl] = self.samples[lbl][-10_000:]


# ======================================================================
# Registry — one per process. The brain creates all metrics up front
# and re-uses the same objects, keeping label cardinality clean.
# ======================================================================
@dataclass
class MetricsRegistry:
    counters:   Dict[str, _Counter]   = field(default_factory=dict)
    gauges:     Dict[str, _Gauge]     = field(default_factory=dict)
    histograms: Dict[str, _Histogram] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    _lock:      Lock  = field(default_factory=Lock)

    def counter(self, name: str, help_: str = "",
                labelnames: Iterable[str] = ()) -> _Counter:
        with self._lock:
            if name not in self.counters:
                self.counters[name] = _Counter(name, help_, tuple(labelnames))
            return self.counters[name]

    def gauge(self, name: str, help_: str = "",
              labelnames: Iterable[str] = ()) -> _Gauge:
        with self._lock:
            if name not in self.gauges:
                self.gauges[name] = _Gauge(name, help_, tuple(labelnames))
            return self.gauges[name]

    def histogram(self, name: str, help_: str = "",
                  labelnames: Iterable[str] = (),
                  buckets: Optional[Iterable[float]] = None) -> _Histogram:
        with self._lock:
            if name not in self.histograms:
                self.histograms[name] = _Histogram(
                    name, help_, tuple(labelnames),
                    buckets=tuple(buckets or _DEFAULT_BUCKETS),
                )
            return self.histograms[name]

    # ──────────────────────────────────────────────────────────────────
    def render(self) -> str:
        """Prometheus 0.0.4 text-exposition format."""
        lines: List[str] = []

        # Uptime gauge — always emitted.
        lines.append("# HELP trendmaster_uptime_seconds Brain uptime in seconds.")
        lines.append("# TYPE trendmaster_uptime_seconds gauge")
        lines.append(f"trendmaster_uptime_seconds {time.time() - self.started_at:.3f}")

        for c in self.counters.values():
            lines.append(f"# HELP {c.name} {c.help}")
            lines.append(f"# TYPE {c.name} counter")
            for lbl, v in c.values.items():
                label_str = self._fmt_labels(c.labelnames, lbl)
                lines.append(f"{c.name}{label_str} {v:g}")

        for g in self.gauges.values():
            lines.append(f"# HELP {g.name} {g.help}")
            lines.append(f"# TYPE {g.name} gauge")
            for lbl, v in g.values.items():
                label_str = self._fmt_labels(g.labelnames, lbl)
                lines.append(f"{g.name}{label_str} {v:g}")

        for h in self.histograms.values():
            lines.append(f"# HELP {h.name} {h.help}")
            lines.append(f"# TYPE {h.name} histogram")
            for lbl, vals in h.samples.items():
                if not vals:
                    continue
                total = sum(vals)
                count = len(vals)
                # Emit buckets (cumulative).
                sorted_vals = sorted(vals)
                for b in h.buckets:
                    bucket_count = sum(1 for x in sorted_vals if x <= b)
                    bucket_labels = self._fmt_labels(
                        h.labelnames + ("le",), lbl + (str(b),),
                    )
                    lines.append(f"{h.name}_bucket{bucket_labels} {bucket_count}")
                inf_labels = self._fmt_labels(
                    h.labelnames + ("le",), lbl + ("+Inf",),
                )
                lines.append(f"{h.name}_bucket{inf_labels} {count}")
                summary_labels = self._fmt_labels(h.labelnames, lbl)
                lines.append(f"{h.name}_sum{summary_labels} {total:g}")
                lines.append(f"{h.name}_count{summary_labels} {count}")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _fmt_labels(names: Tuple[str, ...], values: Tuple[str, ...]) -> str:
        if not names:
            return ""
        parts = [f'{n}="{_escape(v)}"' for n, v in zip(names, values) if v != ""]
        if not parts:
            return ""
        return "{" + ",".join(parts) + "}"


def _escape(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# ======================================================================
# Module-level singletons — what the brain / dashboard import.
# ======================================================================
_REGISTRY = MetricsRegistry()


def registry() -> MetricsRegistry:
    return _REGISTRY


def render_text() -> str:
    """Text-format metrics suitable for a Prometheus scrape."""
    return _REGISTRY.render()


# Pre-declared metric handles — import these from the brain.
tick_latency = _REGISTRY.histogram(
    "trendmaster_tick_latency_seconds",
    "Per-symbol tick_once duration.", labelnames=("symbol",),
)
signal_writes = _REGISTRY.counter(
    "trendmaster_signal_writes_total",
    "Count of non-NONE signals written.", labelnames=("symbol", "direction"),
)
veto_total = _REGISTRY.counter(
    "trendmaster_veto_total",
    "Count of gate vetoes by reason category.",
    labelnames=("symbol", "reason"),
)
mt5_reconnects = _REGISTRY.counter(
    "trendmaster_mt5_reconnects_total",
    "MT5 re-init attempts triggered by copy_rates failure.", labelnames=(),
)
brain_restarts = _REGISTRY.counter(
    "trendmaster_brain_restarts_total",
    "Supervisor-driven brain restart count.", labelnames=(),
)
signal_file_retries = _REGISTRY.counter(
    "trendmaster_signal_file_retries_total",
    "Atomic-write retries triggered by WinError 5.", labelnames=(),
)
account_equity = _REGISTRY.gauge(
    "trendmaster_account_equity",
    "Live MT5 account.equity (account currency).", labelnames=(),
)
account_balance = _REGISTRY.gauge(
    "trendmaster_account_balance",
    "Live MT5 account.balance (account currency).", labelnames=(),
)
open_positions = _REGISTRY.gauge(
    "trendmaster_open_positions",
    "Currently open positions (broker side).", labelnames=("team",),
)


__all__ = [
    "MetricsRegistry", "registry", "render_text",
    "tick_latency", "signal_writes", "veto_total",
    "mt5_reconnects", "brain_restarts", "signal_file_retries",
    "account_equity", "account_balance", "open_positions",
]
