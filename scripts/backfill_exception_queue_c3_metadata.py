#!/usr/bin/env python3
"""Backfill deterministic C3 owner/action/evidence metadata for open exceptions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_materialization_c3 import backfill_exception_queue_metadata  # noqa: E402
from core.ops.policy_registry_c3 import DEFAULT_DB_PATH, DEFAULT_POLICY_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill C3 exception queue metadata")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = backfill_exception_queue_metadata(
        db_path=args.db,
        policy_path=args.policy,
        as_of=args.as_of,
        run_id=args.run_id,
        apply=args.apply,
        backup_dir=args.backup_dir,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"applied={report['applied']}")
        print(f"backup_path={report.get('backup_path')}")
        print(f"updated_exception_count={report.get('updated_exception_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
