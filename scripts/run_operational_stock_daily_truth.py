#!/usr/bin/env python3
"""Run Agent 8 strict operational-stock daily truth gates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.operational_stock_daily_truth_runner import (  # noqa: E402
    run_operational_stock_daily_truth,
)


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "operational_stock_daily_truth"


def _default_almaty_date() -> str:
    almaty = timezone(timedelta(hours=5))
    return datetime.now(tz=almaty).date().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run strict operational-stock daily truth gates")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=_default_almaty_date())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--max-source-lag-days", type=int, default=1)
    parser.add_argument("--max-exception-items", type=int, default=500)
    parser.add_argument(
        "--require-c3-policy",
        action="store_true",
        help="Fail closed unless the C3 policy registry, sources, gates, exceptions, and approvals validate.",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=PROJECT_ROOT / "config" / "operational_decision_policy.yaml",
    )
    parser.add_argument(
        "--allow-green-owner-output",
        action="store_true",
        help="Permit green owner publication only if every strict gate is also green.",
    )
    parser.add_argument(
        "--record-db",
        action="store_true",
        help="Record run rows in DB; requires ENABLE_OPERATIONAL_STOCK_DAILY_DB_WRITE=1.",
    )
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_operational_stock_daily_truth(
        db_path=args.db,
        as_of=args.as_of,
        output_root=args.output_root,
        run_id=args.run_id,
        allow_green_owner_output=args.allow_green_owner_output,
        max_source_lag_days=args.max_source_lag_days,
        max_exception_items=args.max_exception_items,
        record_db=args.record_db,
        backup_dir=args.backup_dir,
        require_c3_policy=args.require_c3_policy,
        policy_path=args.policy,
    )

    if args.json:
        import json

        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"status={report.status}")
        print(f"owner_trust_status={report.owner_trust_status}")
        print(f"run_id={report.run_id}")
        print(f"owner_brief={report.owner_brief_path}")
        print(f"lineage_json={report.lineage_json_path}")
        print(f"exception_report_json={report.exception_report_json_path}")
        print(f"exception_count_total={report.exception_count_total}")
        if report.stock_snapshot_csv_path:
            print(f"stock_snapshot_csv={report.stock_snapshot_csv_path}")
        if report.db_backup_path:
            print(f"db_backup_path={report.db_backup_path}")

    return 0 if report.status == "GREEN" and report.owner_trust_status == "GREEN_DECISION_GRADE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
