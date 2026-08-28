"""Daily maintenance — rotate logs + backup config/state.

Runs once per day via schtask (~ 00:30 IST). Performs:
  1. Compress logs older than 1 day to logs/archive/YYYY-MM-DD.gz
  2. Delete archives older than 30 days
  3. Backup critical config + state files to backup/YYYY-MM-DD.zip
  4. Keep last 14 days of backups
"""
from __future__ import annotations

import gzip
import logging
import shutil
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
ARCHIVE_DIR = LOG_DIR / "archive"
BACKUP_DIR = ROOT / "backup"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "daily_maintenance.log", encoding="utf-8")],
)
log = logging.getLogger("maint")

KEEP_LOG_DAYS = 30
KEEP_BACKUP_DAYS = 14
MAX_LIVE_LOG_SIZE_MB = 50  # rotate any log over this size


def rotate_logs():
    """Compress + truncate large logs.

    2026-05-07: extended to handle .jsonl files (brain_shadow_predictions.jsonl,
    tv_signals.jsonl, events.jsonl, etc) — these were unbounded before.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    rotated = 0
    # Sweep both .log and .jsonl glob patterns
    for pattern in ("*.log", "*.jsonl"):
        for log_file in LOG_DIR.glob(pattern):
            if log_file.parent != LOG_DIR:
                continue
            size_mb = log_file.stat().st_size / 1024 / 1024
            if size_mb < MAX_LIVE_LOG_SIZE_MB:
                continue
            # Rotate (suffix-aware archive name)
            archive_name = f"{log_file.stem}_{today}{log_file.suffix}.gz"
            archive_path = ARCHIVE_DIR / archive_name
            try:
                with log_file.open("rb") as src, gzip.open(archive_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                log_file.write_text("", encoding="utf-8")  # truncate
                rotated += 1
                log.info("rotated %s (%.1f MB) -> %s", log_file.name, size_mb, archive_name)
            except Exception as e:
                log.error("rotate failed for %s: %s", log_file.name, e)
    return rotated


def cleanup_old_archives():
    """Delete archives older than KEEP_LOG_DAYS."""
    cutoff = datetime.now() - timedelta(days=KEEP_LOG_DAYS)
    deleted = 0
    for f in ARCHIVE_DIR.glob("*.gz"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                deleted += 1
        except Exception:
            pass
    if deleted:
        log.info("deleted %d old archive(s)", deleted)
    return deleted


def backup_critical():
    """Zip critical config + state."""
    today = datetime.now().strftime("%Y-%m-%d")
    backup_path = BACKUP_DIR / f"trendmaster_{today}.zip"
    if backup_path.exists():
        log.info("backup for today already exists: %s", backup_path.name)
        return False

    items = [
        # Config
        ROOT / "config" / ".env",
        ROOT / "config" / "settings.py",
        ROOT / "config" / "news_calendar.json",
        # State
        LOG_DIR / "executor_cooldown.json",
        LOG_DIR / "dd_state.json",
        LOG_DIR / "signal_outcomes.jsonl",
        # TV alert browser profile (cookies for TV API access)
        # Note: this can be 100+ MB so we only backup the cookies/state
        ROOT / "tools" / "tv_alert_setup" / "_browser_profile" / "Default" / "Cookies",
        # Critical scripts (so we can restore if disk fails)
        ROOT / "tools" / "python_signal_executor.py",
        ROOT / "tools" / "trailing_stop_manager.py",
        ROOT / "tools" / "process_watchdog.py",
        ROOT / "tools" / "safeguards.py",
        ROOT / "tools" / "daily_telegram_summary.py",
        ROOT / "ai_trading_agents" / "tv_webhook_receiver.py",
        ROOT / "ai_trading_agents" / "tv_executor.py",
        ROOT / "ai_trading_agents" / "telegram_notifier.py",
        # EA source
        Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
        / "D0E8209F77C8CF37AD8BF550E51FF075" / "MQL5" / "Experts"
        / "AI_SUPERBB_v14_TrendMaster.mq5",
    ]

    added = 0
    skipped = 0
    try:
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for src in items:
                if src.exists() and src.is_file():
                    try:
                        rel = src.name
                        zf.write(src, arcname=rel)
                        added += 1
                    except Exception as e:
                        log.warning("backup item failed %s: %s", src.name, e)
                        skipped += 1
                else:
                    skipped += 1
        size_kb = backup_path.stat().st_size / 1024
        log.info("backup created: %s (%.0f KB, %d files, %d skipped)",
                 backup_path.name, size_kb, added, skipped)
        return True
    except Exception as e:
        log.error("backup failed: %s", e)
        if backup_path.exists():
            backup_path.unlink(missing_ok=True)
        return False


def cleanup_old_backups():
    cutoff = datetime.now() - timedelta(days=KEEP_BACKUP_DAYS)
    deleted = 0
    for f in BACKUP_DIR.glob("*.zip"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                deleted += 1
        except Exception:
            pass
    if deleted:
        log.info("deleted %d old backup(s)", deleted)
    return deleted


def main():
    log.info("=== daily maintenance ===")
    rotated = rotate_logs()
    cleanup_old_archives()
    backed = backup_critical()
    cleanup_old_backups()
    log.info("=== done. rotated=%d backed_up=%s ===", rotated, backed)
    # Telegram notify if backup succeeded
    if backed:
        try:
            sys.path.insert(0, str(ROOT))
            from ai_trading_agents.telegram_notifier import get_notifier
            tg = get_notifier()
            if tg and tg.enabled:
                tg.send(f"<b>🗄 Daily backup OK</b>\nLogs rotated: {rotated}  Backups kept: 14d")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
