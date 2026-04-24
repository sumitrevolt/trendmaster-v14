# Monitoring stack — TrendMaster v14

One-command Prometheus + Grafana side-stack. Runs alongside the Windows brain process (which stays native for MT5 compatibility).

## Start

```bash
docker compose -f monitoring/docker-compose.monitoring.yml up -d
```

Grafana → http://localhost:3000 (admin/admin, change on first login)
Prometheus → http://localhost:9090

## Stop

```bash
docker compose -f monitoring/docker-compose.monitoring.yml down
```

Persisted data (retained across restarts): named docker volumes `prometheus_data` and `grafana_data`.

## Prereq — brain must expose /metrics

Flip `METRICS.enabled=True` in `config/settings.py` and restart the brain. Verify:

```bash
curl http://localhost:8000/metrics
```

Should return a body starting with `# HELP trendmaster_uptime_seconds`. If you see `# metrics disabled`, the settings flag hasn't been flipped or the brain hasn't been restarted.

## Dashboard layout

The provisioned `TrendMaster v14 — Live Ops` dashboard has four row groups:

- **Row 1 (KPIs)** — uptime, restart count, account equity, signal-write retries.
- **Row 2 (Loop health)** — tick latency p95 per symbol, signals-written-per-minute split by direction.
- **Row 3 (Gates)** — top-10 veto reasons (last 15 min), open positions by team.
- **Row 4 (MT5 + Equity)** — reconnect rate, equity curve live.

Every panel auto-refreshes every 10 s.

## Why host.docker.internal?

The brain runs as a native Windows process (MT5 bridge is Windows-only). Prometheus runs in a Linux container. `host.docker.internal` + the `host-gateway` mapping lets the container scrape the host's `:8000` port on Linux and macOS hosts. On Windows Docker Desktop this already resolves natively.

## Next steps

- Wire Alertmanager: add `rule_files` to `prometheus.yml` and a receiver config to push pager alerts to Telegram.
- Record-rules for p99 tick latency over 1h/24h/7d windows.
- Second dashboard for ML models (drift count, feature importance over time).
