#!/usr/bin/env python3
"""Run the approved Agent 6 stock anchor and one-time 20 percent workflow.

Default mode is dry-run. DB writes require:
1) ENABLE_STOCK_ANCHOR_20PCT_WRITE=1
2) --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.stock_anchor_20pct import (
    BASELINE_REFERENCE_TYPE,
    anchor_event_date_for,
    apply_anchor_and_adjustment_events,
    backup_db,
    build_anchor_lineage_snapshot,
    build_high_risk_exception_specs,
    build_offer_availability_rows,
    compute_adjustment_plan,
    count_adjustment_batch_duplicates,
    count_legacy_duplicate_groups,
    deterministic_anchor_id,
    deterministic_batch_id,
    insert_exception_specs,
    insert_pipeline_and_report,
    insert_source_manifest,
    load_anchor_rows_from_workbook,
    sha256_file,
    write_inventory_snapshot,
    write_lineage_json,
    write_offer_availability_snapshot,
    write_owner_report,
    write_snapshot_csv,
)


DEFAULT_HANDOFF_DIR = Path(
    "~/Docs/Autonomous_business_agent_handoffs/"
    "2026-05-03_operational-stock-truth-system"
)
DEFAULT_APPROVAL = DEFAULT_HANDOFF_DIR / "OWNER_APPROVAL_STOCK_ANCHOR_20PCT_20260503.md"
DEFAULT_ANCHOR = Path(
    "~/Docs/Oracle/Autonomous_business/2026-05-03/"
    "101657_TASK-000_operational-stock-orders-sales-system-review/"
    "stock_audit_2026-04-04.xlsx"
)
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_DIR = DEFAULT_HANDOFF_DIR / "agent6_stock_rebuild_20pct_outputs"
DEFAULT_BACKUP_DIR = DEFAULT_HANDOFF_DIR / "db_backups"


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _working_connection(db_path: Path, *, apply: bool) -> sqlite3.Connection:
    if apply:
        return _connect(db_path)
    source = _connect(db_path, readonly=True)
    target = sqlite3.connect(":memory:")
    target.row_factory = sqlite3.Row
    source.backup(target)
    source.close()
    return target


def _require_approval(approval_path: Path, anchor_path: Path) -> str:
    text = approval_path.read_text(encoding="utf-8")
    required = [
        "Gate: GREEN",
        str(anchor_path),
        "Do not double-reduce",
        "active sellable stock",
        "offer availability",
        BASELINE_REFERENCE_TYPE,
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"Owner approval artifact missing required approval text: {missing}")
    return text


def _strict_gate_blocker(project_root: Path) -> bool:
    return not (project_root / "exports" / "business_insides" / "BUSINESS_INSIDES_2026-05-02.md").exists()


def run(args: argparse.Namespace) -> dict:
    approval_path = Path(args.approval)
    anchor_path = Path(args.anchor)
    db_path = Path(args.db)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _require_approval(approval_path, anchor_path)

    source_sha256 = sha256_file(anchor_path)
    anchor_rows = load_anchor_rows_from_workbook(anchor_path, args.sheet)
    anchor_id = deterministic_anchor_id(args.anchor_date, source_sha256)
    batch_id = deterministic_batch_id(args.anchor_date, source_sha256)
    source_manifest_id = f"SOURCE_{anchor_id}"
    run_id = f"AGENT6_STOCK_REBUILD_20PCT_{args.snapshot_date.replace('-', '')}"

    adjustment_plan = compute_adjustment_plan(anchor_rows)
    anchor_event_date = args.anchor_event_date or anchor_event_date_for(args.anchor_date)
    dry_run_report_path = output_dir / f"{batch_id}_lineage.json"
    snapshot_csv_path = output_dir / f"{batch_id}_owner_stock_output.csv"
    owner_report_path = output_dir / f"{batch_id}_owner_report.md"

    backup_path: Path | None = None
    if args.apply:
        if os.environ.get("ENABLE_STOCK_ANCHOR_20PCT_WRITE") != "1":
            raise RuntimeError("ENABLE_STOCK_ANCHOR_20PCT_WRITE=1 is required with --apply")
        backup_path = backup_db(db_path, Path(args.backup_dir), "agent6_stock_anchor_20pct")

    conn = _working_connection(db_path, apply=args.apply)
    try:
        apply_result = apply_anchor_and_adjustment_events(
            conn,
            anchor_id=anchor_id,
            batch_id=batch_id,
            anchor_rows=anchor_rows,
            adjustment_plan=adjustment_plan,
            source_path=str(anchor_path),
            source_sha256=source_sha256,
            anchor_snapshot_date=args.anchor_date,
            anchor_event_date=anchor_event_date,
            adjustment_event_date=args.anchor_date,
            approved_by="owner",
            approved_at=args.approved_at,
            dry_run_report_path=str(dry_run_report_path),
        )

        snapshot = build_anchor_lineage_snapshot(
            conn,
            anchor_id=anchor_id,
            batch_id=batch_id,
            anchor_date=args.anchor_date,
            snapshot_date=args.snapshot_date,
            include_active_sizes=args.include_active_sizes,
        )
        exceptions = build_high_risk_exception_specs(anchor_rows, negative_rows=snapshot.negative_rows, run_id=run_id)
        availability = build_offer_availability_rows(
            snapshot.rows,
            exceptions,
            snapshot_date=args.snapshot_date,
            source_manifest_id=source_manifest_id,
        )
        adjustment_duplicate_groups = count_adjustment_batch_duplicates(conn, batch_id)
        legacy_duplicate_groups, legacy_duplicate_rows = count_legacy_duplicate_groups(conn)

        trust_status = "TRUSTED"
        if exceptions or snapshot.negative_rows or legacy_duplicate_groups or _strict_gate_blocker(PROJECT_ROOT):
            trust_status = "PROVISIONAL_BLOCKED"
        if adjustment_duplicate_groups:
            trust_status = "BLOCKED"

        write_lineage_json(
            dry_run_report_path,
            anchor_id=anchor_id,
            batch_id=batch_id,
            anchor_rows=anchor_rows,
            adjustment_plan=adjustment_plan,
            snapshot=snapshot,
            exceptions=exceptions,
            adjustment_duplicate_groups=adjustment_duplicate_groups,
            legacy_duplicate_groups=legacy_duplicate_groups,
            legacy_duplicate_rows=legacy_duplicate_rows,
            apply=args.apply,
        )
        write_snapshot_csv(snapshot_csv_path, snapshot, availability)
        write_owner_report(
            owner_report_path,
            trust_status=trust_status,
            anchor_id=anchor_id,
            batch_id=batch_id,
            snapshot=snapshot,
            exceptions=exceptions,
            adjustment_duplicate_groups=adjustment_duplicate_groups,
            legacy_duplicate_groups=legacy_duplicate_groups,
            legacy_duplicate_rows=legacy_duplicate_rows,
            csv_path=snapshot_csv_path,
            lineage_json_path=dry_run_report_path,
        )

        if args.apply:
            insert_source_manifest(
                conn,
                source_id=source_manifest_id,
                source_type="APPROVED_PHYSICAL_STOCK_ANCHOR",
                source_path=str(anchor_path),
                source_sha256=source_sha256,
                as_of_date=args.anchor_date,
                row_count=len(anchor_rows),
                notes=f"Owner-approved Agent 6 anchor. Approval: {approval_path}",
            )
            inserted_exceptions = insert_exception_specs(conn, exceptions, run_id=run_id)
            snapshot_rows_written = write_inventory_snapshot(conn, snapshot)
            availability_rows_written = write_offer_availability_snapshot(
                conn,
                availability,
                snapshot_date=args.snapshot_date,
                source_manifest_id=source_manifest_id,
            )
            validation_messages = [
                (
                    "adjustment_batch_duplicates",
                    "PASS" if adjustment_duplicate_groups == 0 else "FAIL",
                    "ERROR" if adjustment_duplicate_groups else "INFO",
                    f"duplicate_groups={adjustment_duplicate_groups}",
                ),
                (
                    "persisted_no_negative_stock",
                    "PASS",
                    "INFO",
                    "fact_inventory_snapshot_size current_stock is clamped non-negative; raw negatives are exception-queued.",
                ),
                (
                    "legacy_duplicate_groups",
                    "WARN" if legacy_duplicate_groups else "PASS",
                    "WARN" if legacy_duplicate_groups else "INFO",
                    f"legacy_duplicate_groups={legacy_duplicate_groups}; duplicate_rows={legacy_duplicate_rows}",
                ),
            ]
            insert_pipeline_and_report(
                conn,
                run_id=run_id,
                snapshot_date=args.snapshot_date,
                trust_status=trust_status,
                report_path=str(owner_report_path),
                source_manifest_json=json.dumps(
                    [{"source_id": source_manifest_id, "anchor_id": anchor_id, "batch_id": batch_id}],
                    sort_keys=True,
                ),
                exception_count=len(exceptions),
                validation_messages=validation_messages,
            )
            conn.commit()
        else:
            inserted_exceptions = 0
            snapshot_rows_written = 0
            availability_rows_written = 0

    finally:
        conn.close()

    summary = {
        "apply": args.apply,
        "backup_path": str(backup_path) if backup_path else None,
        "anchor_id": anchor_id,
        "batch_id": batch_id,
        "anchor_rows": len(anchor_rows),
        "anchor_total_units": sum(row.qty for row in anchor_rows),
        "eligible_units": adjustment_plan.eligible_units,
        "target_reduction_units": adjustment_plan.target_reduction_units,
        "generated_reduction_units": adjustment_plan.generated_reduction_units,
        "anchor_events_inserted": apply_result.anchor_events_inserted,
        "adjustment_events_inserted": apply_result.adjustment_events_inserted,
        "already_applied": apply_result.already_applied,
        "snapshot_date": args.snapshot_date,
        "snapshot_rows": len(snapshot.rows),
        "snapshot_current_stock_total": snapshot.current_stock_total,
        "snapshot_inbound_stock_total": snapshot.inbound_stock_total,
        "raw_negative_rows": len(snapshot.negative_rows),
        "exception_count": len(exceptions),
        "exceptions_inserted": inserted_exceptions,
        "offer_availability_rows_written": availability_rows_written,
        "snapshot_rows_written": snapshot_rows_written,
        "adjustment_duplicate_groups": adjustment_duplicate_groups,
        "legacy_duplicate_groups": legacy_duplicate_groups,
        "legacy_duplicate_rows": legacy_duplicate_rows,
        "trust_status": trust_status,
        "lineage_json": str(dry_run_report_path),
        "owner_stock_csv": str(snapshot_csv_path),
        "owner_report": str(owner_report_path),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval", default=str(DEFAULT_APPROVAL))
    parser.add_argument("--anchor", default=str(DEFAULT_ANCHOR))
    parser.add_argument("--sheet", default="Current_Stock_By_Size")
    parser.add_argument("--anchor-date", default="2026-04-04")
    parser.add_argument("--snapshot-date", default=date.today().isoformat())
    parser.add_argument("--approved-at", default="2026-05-03T13:53:47+05:00")
    parser.add_argument("--anchor-event-date", default=None)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--include-active-sizes", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    summary = run(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["adjustment_duplicate_groups"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
