#!/usr/bin/env python3
"""
TASK-045: Database Backup Script

Daily backup of SQLite database with compression.
Deletes backups older than 30 days.

Usage:
    python scripts/backup_db.py [--dest /path/to/backups] [--keep-days 30]

Cron example:
    0 2 * * * cd /path/to/project && python scripts/backup_db.py
"""

import argparse
import gzip
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_db_size(db_path: Path) -> int:
    """Get database file size in bytes."""
    if db_path.exists():
        return db_path.stat().st_size
    return 0


def backup_database(
    db_path: Path,
    backup_dir: Path,
    compress: bool = True
) -> Path:
    """
    Create a backup of the database.

    Args:
        db_path: Path to source database
        backup_dir: Directory for backups
        compress: Whether to gzip the backup

    Returns:
        Path to created backup file
    """
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    backup_name = f"app_{timestamp}.db"

    if compress:
        backup_name += ".gz"

    backup_path = backup_dir / backup_name

    # Create backup using SQLite's backup API for consistency
    source_conn = sqlite3.connect(str(db_path))
    temp_backup = backup_dir / f"temp_{timestamp}.db"

    backup_conn = sqlite3.connect(str(temp_backup))
    source_conn.backup(backup_conn)
    backup_conn.close()
    source_conn.close()

    if compress:
        # Compress the backup
        with open(temp_backup, 'rb') as f_in:
            with gzip.open(backup_path, 'wb', compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)
        temp_backup.unlink()
    else:
        temp_backup.rename(backup_path)

    return backup_path


def cleanup_old_backups(backup_dir: Path, keep_days: int = 30) -> int:
    """
    Delete backups older than keep_days.

    Args:
        backup_dir: Directory containing backups
        keep_days: Days to keep backups

    Returns:
        Number of files deleted
    """
    cutoff = datetime.now() - timedelta(days=keep_days)
    deleted = 0

    for backup_file in backup_dir.glob("app_*.db*"):
        # Extract date from filename
        try:
            name_parts = backup_file.stem.replace('.db', '').split('_')
            date_str = name_parts[1]  # app_YYYY-MM-DD_HHMMSS
            file_date = datetime.strptime(date_str, '%Y-%m-%d')

            if file_date < cutoff:
                backup_file.unlink()
                deleted += 1
                print(f"  Deleted old backup: {backup_file.name}")
        except (ValueError, IndexError):
            continue

    return deleted


def verify_backup(backup_path: Path) -> bool:
    """
    Verify backup integrity by attempting to open it.

    Args:
        backup_path: Path to backup file

    Returns:
        True if backup is valid
    """
    temp_path = backup_path.parent / "verify_temp.db"

    try:
        if backup_path.suffix == '.gz':
            # Decompress to temp file
            with gzip.open(backup_path, 'rb') as f_in:
                with open(temp_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy(backup_path, temp_path)

        # Try to open and query
        conn = sqlite3.connect(str(temp_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        conn.close()

        temp_path.unlink()
        return table_count > 0

    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        return False


def main():
    parser = argparse.ArgumentParser(description='Backup database')
    parser.add_argument(
        '--dest',
        default='backups',
        help='Backup destination directory (default: backups/)'
    )
    parser.add_argument(
        '--keep-days',
        type=int,
        default=30,
        help='Days to keep backups (default: 30)'
    )
    parser.add_argument(
        '--no-compress',
        action='store_true',
        help='Disable gzip compression'
    )
    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Skip cleanup of old backups'
    )
    parser.add_argument(
        '--db',
        default='db/app.db',
        help='Path to database (default: db/app.db)'
    )
    args = parser.parse_args()

    # Resolve paths
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = project_root / db_path

    backup_dir = Path(args.dest)
    if not backup_dir.is_absolute():
        backup_dir = project_root / backup_dir

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print(f"=== Database Backup ===")
    print(f"Source: {db_path}")
    print(f"Destination: {backup_dir}")
    print()

    # Get source size
    source_size = get_db_size(db_path)
    print(f"Source size: {source_size / (1024*1024):.2f} MB")

    # Create backup
    print(f"Creating backup...")
    backup_path = backup_database(
        db_path,
        backup_dir,
        compress=not args.no_compress
    )

    backup_size = get_db_size(backup_path)
    compression_ratio = (1 - backup_size / source_size) * 100 if source_size > 0 else 0

    print(f"Backup created: {backup_path.name}")
    print(f"Backup size: {backup_size / (1024*1024):.2f} MB")
    if not args.no_compress:
        print(f"Compression: {compression_ratio:.1f}% reduction")

    # Verify backup
    print(f"\nVerifying backup...")
    if verify_backup(backup_path):
        print(f"Backup verified successfully")
    else:
        print(f"WARNING: Backup verification failed!")
        return 1

    # Cleanup old backups
    if not args.no_cleanup:
        print(f"\nCleaning up backups older than {args.keep_days} days...")
        deleted = cleanup_old_backups(backup_dir, args.keep_days)
        print(f"Deleted {deleted} old backup(s)")

    # List current backups
    backups = sorted(backup_dir.glob("app_*.db*"))
    print(f"\nCurrent backups ({len(backups)}):")
    for b in backups[-5:]:  # Show last 5
        size = get_db_size(b) / (1024*1024)
        print(f"  {b.name} ({size:.2f} MB)")

    if len(backups) > 5:
        print(f"  ... and {len(backups) - 5} more")

    print(f"\nBackup complete.")
    return 0


if __name__ == '__main__':
    exit(main())
