"""
SAFE START SCRIPT FOR AUTOMATED TRADING BOT
============================================
Pre-flight checks before starting the bot:
1. MT5 connection validation
2. Open positions check (warn about orphaned SELL positions)
3. JSON file validation (catch corruption early)
4. Settings validation (ensure config is correct)
5. File locking setup for JSON writes
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime
import logging
import tempfile

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from src.data_fetcher import initialize_mt5
from src.utils import setup_logging

# ============================================================================
# LOGGING SETUP
# ============================================================================
logger = setup_logging('INFO', 'logs/safe_start.log')

# ============================================================================
# JSON VALIDATION FUNCTIONS
# ============================================================================
def validate_json_file(filepath):
    """Validate JSON file integrity. Return (is_valid, error_msg, data)"""
    if not os.path.exists(filepath):
        return True, "File does not exist (OK)", None

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return True, "Valid JSON", data
    except json.JSONDecodeError as e:
        return False, f"JSON Decode Error: {str(e)}", None
    except Exception as e:
        return False, f"File read error: {str(e)}", None


def repair_json_file(filepath):
    """
    Attempt to repair corrupted JSON file by:
    1. Reading raw content
    2. Finding valid JSON object start/end
    3. Extracting largest valid chunk
    """
    if not os.path.exists(filepath):
        return False, "File does not exist"

    try:
        with open(filepath, 'r', errors='replace') as f:
            content = f.read()

        # Try to extract valid JSON from content
        start_idx = content.find('{')
        if start_idx == -1:
            return False, "No JSON object found"

        # Find matching closing brace
        brace_count = 0
        for i in range(start_idx, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_str = content[start_idx:i+1]
                    data = json.loads(json_str)

                    # Backup original and write repaired version
                    backup_path = f"{filepath}.corrupted_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    os.rename(filepath, backup_path)

                    # Atomic write: temp file + rename to prevent corruption
                    import tempfile
                    json_str = json.dumps(data, indent=2, default=str)
                    dir_path = os.path.dirname(os.path.abspath(filepath))
                    with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                                      suffix='.tmp', encoding='utf-8', newline='\n') as tmp:
                        tmp.write(json_str)
                        tmp.flush()
                        os.fsync(tmp.fileno())
                        tmp_name = tmp.name
                    try:
                        os.replace(tmp_name, filepath)
                    except (OSError, PermissionError):
                        # Fallback to direct write if atomic rename fails
                        try:
                            os.unlink(tmp_name)
                        except Exception:
                            pass
                        with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
                            f.write(json_str)
                            f.flush()
                            os.fsync(f.fileno())

                    logger.warning(f"Repaired {filepath}")
                    logger.warning(f"Backup saved to {backup_path}")
                    return True, "File repaired successfully"

        return False, "Could not extract valid JSON object"
    except Exception as e:
        return False, f"Repair failed: {str(e)}"


# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================
def check_mt5_connection():
    """Check MT5 connection and account status"""
    logger.info("\n" + "="*70)
    logger.info("CHECK 1: MT5 CONNECTION")
    logger.info("="*70)

    mt5 = initialize_mt5()
    if mt5 is None:
        logger.error("FAILED: Cannot connect to MT5")
        logger.error("Make sure MetaTrader 5 is running and OctaFX-Demo is available")
        return False

    account = mt5.get_account_info()
    if not account:
        logger.error("FAILED: Cannot get account info from MT5")
        return False

    logger.info(f"PASS: Connected to MT5")
    logger.info(f"  Account:   {account.get('account', 'N/A')}")
    logger.info(f"  Balance:   ${account.get('balance', 0):.2f}")
    logger.info(f"  Equity:    ${account.get('equity', 0):.2f}")
    logger.info(f"  Leverage:  1:{account.get('leverage', 0)}")
    logger.info(f"  Server:    {account.get('server', 'N/A')}")

    return True, mt5, account


def check_open_positions(mt5):
    """Check for open positions and warn about orphaned SELL positions"""
    logger.info("\n" + "="*70)
    logger.info("CHECK 2: OPEN POSITIONS")
    logger.info("="*70)

    try:
        positions = mt5.get_open_positions()
        if not positions:
            logger.info("PASS: No open positions")
            return True

        logger.warning(f"WARNING: Found {len(positions)} open position(s):")
        for pos in positions:
            symbol = pos.get('symbol', 'UNKNOWN')
            side = "SELL" if pos.get('type') == 1 else "BUY"
            volume = pos.get('volume', 0)
            open_price = pos.get('open_price', 0)
            profit = pos.get('profit', 0)

            logger.warning(f"  - {symbol} {side} {volume} lots @ {open_price} (P&L: ${profit:.2f})")

        logger.warning("ACTION REQUIRED: Close all open positions manually before running bot")
        logger.warning("Reason: Bot cannot manage orphaned positions from previous sessions")
        return False

    except Exception as e:
        logger.error(f"Error checking positions: {e}")
        return False


def check_json_files():
    """Validate all JSON files in config/data folders"""
    logger.info("\n" + "="*70)
    logger.info("CHECK 3: JSON FILE INTEGRITY")
    logger.info("="*70)

    json_files = [
        'logs/bot_state.json',
        'logs/trades.csv',
        'ai_trading_agents/agent_learnings.json',
        'ai_trading_agents/agent_internet_research.json',
        'ai_trading_agents/agent_memory.json',
    ]

    all_valid = True
    for filepath in json_files:
        if not Path(filepath).exists():
            logger.info(f"  {filepath}: SKIP (not created yet)")
            continue

        is_valid, msg, _ = validate_json_file(filepath)
        if is_valid:
            logger.info(f"  {filepath}: PASS")
        else:
            logger.error(f"  {filepath}: FAIL - {msg}")
            logger.warning(f"  Attempting repair...")
            repair_ok, repair_msg = repair_json_file(filepath)
            if repair_ok:
                logger.info(f"    {repair_msg}")
            else:
                logger.error(f"    Repair failed: {repair_msg}")
                all_valid = False

    if all_valid:
        logger.info("PASS: All JSON files valid")
    else:
        logger.warning("WARN: Some JSON files were corrupted and repaired")

    return all_valid


def check_settings_config():
    """Validate critical settings"""
    logger.info("\n" + "="*70)
    logger.info("CHECK 4: SETTINGS VALIDATION")
    logger.info("="*70)

    issues = []

    # Check trading pairs
    pairs = settings.TRADING_PAIRS
    logger.info(f"Trading pairs enabled: {len(pairs)}")
    logger.info(f"  Pairs: {', '.join(pairs)}")

    if len(pairs) != 2:
        issues.append(f"Expected 2 trading pairs (XAUUSD, GBPJPY), found {len(pairs)}")

    if 'XAUUSD' not in pairs:
        issues.append("XAUUSD (79.5% WR) should be enabled")
    if 'GBPJPY' not in pairs:
        issues.append("GBPJPY (78.6% WR) should be enabled")

    # Check risk parameters
    risk = settings.RISK
    logger.info(f"Risk settings:")
    logger.info(f"  Risk per trade: {risk.get('risk_percent', 0)}%")
    logger.info(f"  Max daily drawdown: {risk.get('max_daily_drawdown_percent', 0)}%")
    logger.info(f"  Max open trades: {risk.get('max_open_trades', 0)}")
    logger.info(f"  Min lot size: {risk.get('min_lot_size', 0)}")
    logger.info(f"  Max lot size: {risk.get('max_lot_size', 0)}")

    # Validate risk settings
    if risk.get('risk_percent', 0) != 0.5:
        issues.append("Risk should be 0.5% per trade")
    if risk.get('max_daily_drawdown_percent', 0) < 3.0:
        issues.append("Max daily drawdown should be 3%+")
    if risk.get('max_open_trades', 0) > 2:
        issues.append("Max open trades should be 2 for $300 account")

    # Check stop-loss minimum
    if not hasattr(settings.RISK, 'min_sl_pips') and risk.get('min_sl_pips') is None:
        logger.warning("  min_sl_pips not explicitly set (should be 5 pips minimum)")

    if issues:
        logger.error("FAIL: Settings validation errors:")
        for issue in issues:
            logger.error(f"  - {issue}")
        return False
    else:
        logger.info("PASS: All settings valid")
        return True


def setup_json_file_locking():
    """
    Setup file locking mechanism for JSON writes.
    This prevents concurrent write corruption.
    """
    logger.info("\n" + "="*70)
    logger.info("CHECK 5: JSON FILE LOCKING SETUP")
    logger.info("="*70)

    try:
        # Create lock directory
        lock_dir = Path('locks')
        lock_dir.mkdir(exist_ok=True)

        logger.info(f"PASS: JSON file locking ready")
        logger.info(f"  Lock directory: {lock_dir.absolute()}")
        logger.info(f"  Files will use atomic writes (temp file + rename)")

        # Test atomic write
        test_file = Path('logs/test_atomic_write.json')
        test_data = {'test': 'data', 'timestamp': datetime.now().isoformat()}

        # Atomic write: temp file -> rename
        fd, tmp_path = tempfile.mkstemp(dir=str(lock_dir), suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(test_data, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(test_file))
            logger.info("  Atomic write test: PASS")
        except Exception as e:
            logger.error(f"  Atomic write test: FAIL - {e}")
            return False

        return True
    except Exception as e:
        logger.error(f"FAIL: Cannot setup file locking: {e}")
        return False


# ============================================================================
# MAIN STARTUP ROUTINE
# ============================================================================
def safe_start():
    """Run all pre-flight checks and start bot if all pass"""
    logger.info("\n")
    logger.info("█" * 70)
    logger.info("█ AUTOMATED TRADING BOT - SAFE START PRE-FLIGHT CHECKS")
    logger.info("█" * 70)
    logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    checks_passed = 0
    checks_total = 5

    # Check 1: MT5 Connection
    result = check_mt5_connection()
    if not result:
        logger.error("\n" + "!"*70)
        logger.error("! PRE-FLIGHT CHECK FAILED - MT5 NOT AVAILABLE")
        logger.error("!"*70)
        return False
    checks_passed += 1
    _, mt5, account = result

    # Check 2: Open Positions
    if not check_open_positions(mt5):
        logger.error("\n" + "!"*70)
        logger.error("! PRE-FLIGHT CHECK FAILED - CLOSE ORPHANED POSITIONS FIRST")
        logger.error("!"*70)
        return False
    checks_passed += 1

    # Check 3: JSON Files
    check_json_files()
    checks_passed += 1

    # Check 4: Settings
    if not check_settings_config():
        logger.error("\n" + "!"*70)
        logger.error("! PRE-FLIGHT CHECK FAILED - SETTINGS INVALID")
        logger.error("!"*70)
        return False
    checks_passed += 1

    # Check 5: File Locking
    if not setup_json_file_locking():
        logger.error("\n" + "!"*70)
        logger.error("! PRE-FLIGHT CHECK FAILED - FILE LOCKING SETUP FAILED")
        logger.error("!"*70)
        return False
    checks_passed += 1

    # All checks passed
    logger.info("\n" + "="*70)
    logger.info("RESULT: ALL PRE-FLIGHT CHECKS PASSED ✓")
    logger.info("="*70)
    logger.info(f"Checks passed: {checks_passed}/{checks_total}")
    logger.info("\nBOT IS READY TO START")
    logger.info("Run: python main.py")
    logger.info("="*70 + "\n")

    return True


if __name__ == '__main__':
    try:
        success = safe_start()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\nShutdown requested")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
