#!/usr/bin/env python3
"""
TASK-043: System Health Check

Verify system health before/after pipeline runs.
Exit code 0 = healthy, 1 = issues found.

Usage:
    python scripts/health_check.py [--verbose] [--alert-on-fail]
"""

import argparse
import os
import sqlite3
import yaml
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_database_exists(db_path: Path) -> tuple[bool, str]:
    """Check if database exists and is readable."""
    if not db_path.exists():
        return False, f"Database not found at {db_path}"

    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("SELECT 1")
        conn.close()
        return True, "Database exists and is readable"
    except Exception as e:
        return False, f"Database error: {e}"


def check_required_tables(db_path: Path) -> tuple[bool, str]:
    """Check if all required tables exist."""
    required_tables = [
        'dim_store', 'dim_sku', 'dim_sku_size', 'dim_params',
        'dim_seasonality', 'dim_sku_lifecycle',
        'fact_sales', 'fact_sales_daily', 'fact_sales_daily_size',
        'fact_inventory_snapshot', 'fact_inventory_snapshot_size',
        'fact_demand_forecast', 'fact_forecast_accuracy',
        'fact_stockout_events', 'fact_system_metrics',
        'fact_po_draft', 'fact_po_draft_lines',
        'fact_alert_log'
    ]

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name FROM sqlite_master WHERE type='table'
    """)
    existing = {row[0] for row in cursor.fetchall()}
    conn.close()

    missing = [t for t in required_tables if t not in existing]

    if missing:
        return False, f"Missing tables: {', '.join(missing)}"

    return True, f"All {len(required_tables)} required tables exist"


def check_data_freshness(db_path: Path, max_days: int = 7) -> tuple[bool, str]:
    """Check if fact_sales_daily has recent data."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT MAX(sale_date) FROM fact_sales_daily
    """)
    result = cursor.fetchone()
    conn.close()

    if not result or not result[0]:
        return False, "No data in fact_sales_daily"

    last_date = date.fromisoformat(result[0])
    days_old = (date.today() - last_date).days

    if days_old > max_days:
        return False, f"fact_sales_daily stale: last update {days_old} days ago ({result[0]})"

    return True, f"Data fresh: last sale date {result[0]} ({days_old} days ago)"


def check_active_skus(db_path: Path, min_skus: int = 10) -> tuple[bool, str]:
    """Check if we have enough active SKUs."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM dim_sku WHERE active_flag = 1
    """)
    count = cursor.fetchone()[0]
    conn.close()

    if count < min_skus:
        return False, f"Only {count} active SKUs (minimum: {min_skus})"

    return True, f"{count} active SKUs"


def check_config_files() -> tuple[bool, str]:
    """Check if config files exist and are valid YAML."""
    config_files = [
        'config/stores.yaml',
        'config/alerts.yaml',
        'config/paths.yaml'
    ]

    issues = []
    for config_file in config_files:
        path = project_root / config_file
        if not path.exists():
            issues.append(f"Missing: {config_file}")
            continue

        try:
            with open(path) as f:
                yaml.safe_load(f)
        except Exception as e:
            issues.append(f"Invalid YAML in {config_file}: {e}")

    if issues:
        return False, "; ".join(issues)

    return True, f"All {len(config_files)} config files valid"


def check_telegram_config() -> tuple[bool, str]:
    """Check if Telegram credentials are configured."""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not token:
        return False, "TELEGRAM_BOT_TOKEN not set"

    if not chat_id:
        return False, "TELEGRAM_CHAT_ID not set"

    return True, "Telegram credentials configured"


def check_export_directory() -> tuple[bool, str]:
    """Check if exports directory is writable."""
    exports_dir = project_root / 'exports'

    if not exports_dir.exists():
        try:
            exports_dir.mkdir(parents=True)
        except Exception as e:
            return False, f"Cannot create exports directory: {e}"

    # Test write
    test_file = exports_dir / '.write_test'
    try:
        test_file.write_text('test')
        test_file.unlink()
        return True, "Exports directory writable"
    except Exception as e:
        return False, f"Exports directory not writable: {e}"


def check_logs_directory() -> tuple[bool, str]:
    """Check if logs directory exists and is writable."""
    logs_dir = project_root / 'logs'

    if not logs_dir.exists():
        try:
            logs_dir.mkdir(parents=True)
        except Exception as e:
            return False, f"Cannot create logs directory: {e}"

    return True, "Logs directory ready"


def check_disk_space(min_gb: float = 1.0) -> tuple[bool, str]:
    """Check available disk space."""
    import shutil

    try:
        usage = shutil.disk_usage(project_root)
        free_gb = usage.free / (1024 ** 3)

        if free_gb < min_gb:
            return False, f"Low disk space: {free_gb:.1f} GB free"

        return True, f"Disk space OK: {free_gb:.1f} GB free"
    except Exception as e:
        return False, f"Cannot check disk space: {e}"


def send_failure_alert(failed_checks: list[tuple[str, str]]) -> None:
    """Send Telegram alert on health check failure."""
    try:
        from core.alerts.telegram import send_message

        message = "<b>Health Check Failed</b>\n\n"
        for check_name, error_msg in failed_checks:
            message += f"<b>{check_name}:</b> {error_msg}\n"

        send_message(message)
    except Exception as e:
        print(f"Failed to send alert: {e}")


def main():
    parser = argparse.ArgumentParser(description='System health check')
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output'
    )
    parser.add_argument(
        '--alert-on-fail',
        action='store_true',
        help='Send Telegram alert on failure'
    )
    parser.add_argument(
        '--db',
        default='db/app.db',
        help='Path to database (default: db/app.db)'
    )
    args = parser.parse_args()

    # Resolve database path
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = project_root / db_path

    print("=== System Health Check ===\n")

    checks = [
        ("Database exists", lambda: check_database_exists(db_path)),
        ("Required tables", lambda: check_required_tables(db_path)),
        ("Data freshness", lambda: check_data_freshness(db_path)),
        ("Active SKUs", lambda: check_active_skus(db_path)),
        ("Config files", check_config_files),
        ("Telegram config", check_telegram_config),
        ("Exports directory", check_export_directory),
        ("Logs directory", check_logs_directory),
        ("Disk space", check_disk_space),
    ]

    passed = 0
    failed = 0
    failed_checks = []

    for check_name, check_func in checks:
        try:
            success, message = check_func()
            status = "PASS" if success else "FAIL"

            if success:
                passed += 1
            else:
                failed += 1
                failed_checks.append((check_name, message))

            if args.verbose or not success:
                print(f"[{status}] {check_name}: {message}")
            else:
                print(f"[{status}] {check_name}")

        except Exception as e:
            failed += 1
            failed_checks.append((check_name, str(e)))
            print(f"[FAIL] {check_name}: Exception - {e}")

    print(f"\n=== Summary ===")
    print(f"Passed: {passed}/{len(checks)}")
    print(f"Failed: {failed}/{len(checks)}")

    if failed > 0:
        print(f"\n HEALTH CHECK FAILED")

        if args.alert_on_fail:
            send_failure_alert(failed_checks)
            print("Alert sent to Telegram")

        return 1

    print(f"\n HEALTH CHECK PASSED")
    return 0


if __name__ == '__main__':
    exit(main())
