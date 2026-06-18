#!/usr/bin/env python3
"""Materialize C3 source_freshness_result rows from local observations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.policy_materialization_c3 import (  # noqa: E402
    C3_MATERIALIZATION_ENV_GATE,
    materialize_source_freshness_results,
)
from core.ops.policy_registry_c3 import DEFAULT_DB_PATH, DEFAULT_POLICY_PATH  # noqa: E402


CLI_MANIFEST_ENV_GATE = "ENABLE_C3_POLICY_MATERIALIZATION_WRITE"


def main() -> int:
    if CLI_MANIFEST_ENV_GATE != C3_MATERIALIZATION_ENV_GATE:
        raise RuntimeError(
            f"CLI manifest env gate {CLI_MANIFEST_ENV_GATE} does not match core gate "
            f"{C3_MATERIALIZATION_ENV_GATE}"
        )

    parser = argparse.ArgumentParser(
        description="Materialize C3 source freshness results",
        epilog=f"Apply requires {CLI_MANIFEST_ENV_GATE}=1.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--source-id",
        action="append",
        default=None,
        help="Limit materialization to one C3 policy source id; repeat for multiple ids.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = materialize_source_freshness_results(
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
        print(f"backup_path={report.get('backup_path')}")
        print(f"source_status_counts={report.get('source_status_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
