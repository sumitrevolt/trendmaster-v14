# Dockerfile — TrendMaster v14 headless image
#
# NOTE: The MT5 terminal + EA must run on the user's Windows host; this
# container only runs the Python brain + dashboard. On Linux the brain
# won't be able to import MetaTrader5 (Windows-only), so it runs in its
# offline/CSV mode — useful for CI, dispatcher scans, backtests, and
# retraining. For live trading, run this image on Windows/WSL2 with the
# MT5 terminal mounted, or skip Docker on the production machine.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for LightGBM wheel (libgomp)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
 && grep -v -E '^MetaTrader5' requirements.txt > /tmp/req.txt \
 && pip install -r /tmp/req.txt

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; \
import urllib.request as u; \
sys.exit(0 if u.urlopen('http://localhost:8000/healthz', timeout=3).status==200 else 1)"

# Default: supervisor (brain + dashboard with auto-restart).
CMD ["python", "main.py", "supervise"]
