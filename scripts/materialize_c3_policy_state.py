#!/usr/bin/env python3
"""Materialize Agent 8 C3 source freshness, gates, and exception metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_materialization_c3 import materialize_c3_policy_state  # noqa: E402
from core.ops.policy_registry_c3 import DEFAULT_DB_PATH, DEFAULT_POLICY_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize Agent 8 C3 policy state")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--source-id",
        action="append",
        default=None,
        help="Limit source-freshness materialization to one C3 policy source id; repeat for multiple ids.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = materialize_c3_policy_state(
        db_path=args.db,
        policy_path=args.policy,
        as_of=args.as_of,
        run_id=args.run_id,
        apply=args.apply,
        backup_dir=args.backup_dir,
        source_ids=set(args.source_id) if args.source_id else None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"applied={report['applied']}")
        print(f"run_id={report['run_id']}")
        print(f"backup_path={report.get('backup_path')}")
        print(f"sections={','.join(report['sections'])}")
        if "source_status_counts" in report:
            print(f"source_status_counts={report['source_status_counts']}")
        if "gate_status_counts" in report:
            print(f"gate_status_counts={report['gate_status_counts']}")
        if "updated_exception_count" in report:
            print(f"updated_exception_count={report['updated_exception_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
