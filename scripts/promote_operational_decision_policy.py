#!/usr/bin/env python3
"""Promote operational_decision_policy.yaml into the C3 DB registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_registry_c3 import (  # noqa: E402
    DEFAULT_DB_PATH,
    DEFAULT_POLICY_PATH,
    promote_operational_decision_policy,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote operational decision policy YAML to DB")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=PROJECT_ROOT / "runtime" / "backups")
    parser.add_argument("--actor", type=str, default="agent7")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        report = promote_operational_decision_policy(
            db_path=args.db,
            policy_path=args.policy,
            apply=args.apply,
            backup_dir=args.backup_dir,
            actor=args.actor,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        mode = "APPLY" if args.apply else "DRY RUN"
        print(f"{mode}: policy_version_id={report['policy_version_id']}")
        print(f"policy_leaf_count={report['policy_leaf_count']}")
        print(f"source_yaml_sha256={report['source_yaml_sha256']}")
        if report.get("backup_path"):
            print(f"db_backup_path={report['backup_path']}")
        if args.apply:
            print(f"inserted_policy_values={report['inserted_policy_values']}")
            print(f"inserted_sources={report['inserted_sources']}")
            print(f"inserted_source_pointers={report['inserted_source_pointers']}")
            print(f"policy_version_reused={report['policy_version_reused']}")
        else:
            print("No DB writes performed. Use ENABLE_POLICY_REGISTRY_WRITE=1 and --apply to promote.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
