#!/usr/bin/env python3
"""Materialize C3 policy_gate_result rows from source, validator, and exception state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_materialization_c3 import materialize_policy_gate_results  # noqa: E402
from core.ops.policy_registry_c3 import DEFAULT_DB_PATH, DEFAULT_POLICY_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize C3 policy gate results")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = materialize_policy_gate_results(
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
        print(f"gate_status_counts={report.get('gate_status_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
