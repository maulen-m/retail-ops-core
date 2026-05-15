#!/usr/bin/env python3
"""Additive C3 policy/source registry schema migration.

Dry-run is the default. Apply requires ENABLE_POLICY_REGISTRY_WRITE=1 and
--apply, and records a DB backup path in policy_change_event.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_registry_c3 import (  # noqa: E402
    DEFAULT_DB_PATH,
    apply_policy_registry_schema_migration,
    migrate_policy_registry_c3,
    validate_policy_registry_schema,
)


def migrate(db_path: Path) -> None:
    migrate_policy_registry_c3(db_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate additive C3 policy registry schema")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=PROJECT_ROOT / "runtime" / "backups")
    parser.add_argument("--actor", type=str, default="agent7")
    args = parser.parse_args()

    if not args.apply:
        errors = validate_policy_registry_schema(args.db) if args.db.exists() else ["DB missing"]
        if errors:
            print("DRY RUN: C3 policy registry migration required:")
            for err in errors:
                print(f"  - {err}")
            print("Use ENABLE_POLICY_REGISTRY_WRITE=1 and --apply to run migration.")
        else:
            print("DRY RUN: C3 policy registry schema already valid.")
        return 0

    if os.environ.get("ENABLE_POLICY_REGISTRY_WRITE") != "1":
        print("ERROR: ENABLE_POLICY_REGISTRY_WRITE=1 is required to apply C3 migration.")
        return 1

    report = apply_policy_registry_schema_migration(
        db_path=args.db,
        backup_dir=args.backup_dir,
        actor=args.actor,
    )
    if report["schema_errors"]:
        print("ERROR: C3 policy registry migration incomplete:")
        for err in report["schema_errors"]:
            print(f"  - {err}")
        print(f"db_backup_path={report['backup_path']}")
        return 1

    print("C3 policy registry schema migrated.")
    print(f"db_backup_path={report['backup_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
