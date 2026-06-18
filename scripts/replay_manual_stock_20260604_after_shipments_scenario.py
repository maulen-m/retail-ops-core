#!/usr/bin/env python3
"""Dry-run the 2026-06-04 manual stock count as after June 4 daily shipments."""

from __future__ import annotations

import argparse
import copy
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_manual_stock_20260604_pre_shipments_anchor as pre  # noqa: E402
from core.ops.manual_stock_count_manifest import (  # noqa: E402
    aggregate_manual_stock_counts,
    validate_manual_stock_manifest,
    write_manual_stock_aggregate_csv,
)


BATCH_ID = "ASTANA_WAREHOUSE_MANUAL_COUNT_2026_06_04_AFTER_DAILY_SHIPMENTS_SCENARIO"
ANCHOR_TIMESTAMP = "2026-06-04T23:59:59+05:00"
ANCHOR_SQLITE_TS = "2026-06-04 23:59:59"
PRE_SHIPMENT_SQLITE_TS = pre.ANCHOR_SQLITE_TS
TIMING_POLICY = "after_2026_06_04_daily_kaspi_shipments_scenario"
ALMATY = ZoneInfo("Asia/Almaty")


def build_scenario_manifest() -> dict[str, Any]:
    manifest = copy.deepcopy(pre.build_manifest())
    manifest["batch_id"] = BATCH_ID
    manifest["approval"]["approval_basis"] = (
        "Owner-requested read-only timing scenario: treat the 2026-06-04 count as after "
        "daily Kaspi shipment completion. This is not DB write authorization."
    )
    manifest["count_scope"]["method"] = (
        "manual_human_count_after_2026_06_04_daily_kaspi_shipments_scenario"
    )
    manifest["precedence"]["rule"] = (
        "Scenario only: for covered SKU-size or shared stock-pool rows, test the same "
        "manual quantities as if they were counted after the 2026-06-04 daily shipments."
    )
    manifest["precedence"]["post_count_motion_rule"] = (
        "After 2026-06-04T23:59:59+05:00, subtract trusted later Kaspi shipped/order "
        "movements exactly once. Do not subtract 2026-06-04 daily shipments in this scenario."
    )
    manifest["expected_totals"]["folder_totals"] = {
        pre.TIMESTAMP_FOLDER: sum(int(row["quantity"]) for row in manifest["rows"])
    }
    for row in manifest["rows"]:
        row["count_timestamp_at_almaty"] = ANCHOR_TIMESTAMP
        row["timing_policy"] = TIMING_POLICY

    validate_manual_stock_manifest(manifest)
    return manifest


def latest_june4_trusted_shipments_excluded(
    conn: sqlite3.Connection,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    original_anchor = pre.ANCHOR_SQLITE_TS
    try:
        pre.ANCHOR_SQLITE_TS = PRE_SHIPMENT_SQLITE_TS
        trusted, _excluded, _deductions = pre.shipment_replay(conn, manifest, as_of_date="2026-06-04")
    finally:
        pre.ANCHOR_SQLITE_TS = original_anchor
    return {
        "trusted_rows": len(trusted),
        "trusted_quantity": sum(int(row["quantity"] or 0) for row in trusted),
        "first_ship_datetime": min((row["ship_datetime"] for row in trusted if row["ship_datetime"]), default=""),
        "last_ship_datetime": max((row["ship_datetime"] for row in trusted if row["ship_datetime"]), default=""),
    }


def write_summary_json(path: Path, payload: Any) -> None:
    pre.write_json(path, payload)


def render_closeout(summary: dict[str, Any]) -> str:
    stock_mismatch_lines = [
        f"- Negative dry-run stock rows: `{summary['stock_mismatches']['negative_rows']}`.",
        f"- Shipment size-conflict rows: `{summary['shipments']['trusted_size_conflict_rows']}`.",
    ]
    if summary["stock_mismatches"]["samples"]:
        sample = summary["stock_mismatches"]["samples"][0]
        stock_mismatch_lines.append("- First mismatch sample:")
        stock_mismatch_lines.append(
            f"  `{sample['sku_id']}` anchor `{sample['pre_shipment_anchor_qty']}`, "
            f"trusted shipped `{sample['trusted_post_anchor_shipped_qty']}`, "
            f"dry-run estimate `{sample['estimated_current_stock_dry_run']}`."
        )

    return "\n".join(
        [
            "# 2026-06-04 Manual Stock After-Daily-Shipments Scenario Dry-Run Closeout",
            "",
            f"Gate: {summary['gate']}",
            "",
            f"Reason: {summary['gate_reason']}",
            "",
            "## Scenario",
            "",
            f"- Scenario anchor timestamp: `{summary['anchor_timestamp']}`.",
            "- The same 2026-06-04 manual counted quantities are treated as after that day's daily Kaspi shipments.",
            "- Trusted 2026-06-04 shipments are not subtracted again in this scenario.",
            f"- June 4 trusted rows excluded by timing: `{summary['timing_adjustment']['trusted_rows']}`, quantity `{summary['timing_adjustment']['trusted_quantity']}`.",
            "",
            "## Artifacts",
            "",
            f"- Scenario manifest: `{summary['manifest_path']}`",
            f"- Scenario aggregate CSV: `{summary['aggregate_csv_path']}`",
            f"- Quarantine sidecar: `{summary['quarantine_path']}`",
            f"- Dry-run replay CSV: `{summary['replay_csv_path']}`",
            f"- Trusted shipments CSV: `{summary['trusted_shipments_csv_path']}`",
            f"- Mapping evidence CSV: `{summary['mapping_csv_path']}`",
            "",
            "## Handling Proof",
            "",
            f"- `3_in_1_men_sets`: quarantined rows `{summary['quarantine']['rows']}`, units `{summary['quarantine']['units']}`.",
            f"- LINE51 S row materialized: `{str(summary['line51_s']['manifest_row_present']).lower()}`.",
            f"- LINE51 S latest DB snapshot value preserved/read-only: `{summary['line51_s']['latest_db_current_stock']}` on `{summary['latest_snapshot_date']}`.",
            f"- Rombik shared S stock pool row count: `{summary['shared_pool']['rombik_s_rows']}`.",
            "",
            "## Shipment Replay",
            "",
            f"- Query window: `{summary['shipments']['query_window']}`.",
            f"- Trusted shipment rows: `{summary['shipments']['trusted_rows']}`.",
            f"- Trusted shipped quantity: `{summary['shipments']['trusted_quantity']}`.",
            f"- Excluded non-shipped/cancelled rows: `{summary['shipments']['excluded_rows']}`.",
            f"- Existing DB stock_anchor rows for this scenario batch: `{summary['db_anchor_existing_rows']}`.",
            "",
            "## Stoplines",
            "",
            *stock_mismatch_lines,
            "",
            "## DB Boundary",
            "",
            "- No `db/app.db` mutation was performed.",
            "- No DB backup was created because there was no apply attempt.",
            "- Rollback for this dry-run is file-level removal of this scenario evidence folder only.",
            "",
            "## Commands",
            "",
            "Command outputs are recorded in `.claude/SESSION_LOG.md` by the execution agent.",
        ]
    ) + "\n"


def build(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id or f"manual_stock_20260604_after_shipments_dryrun_{datetime.now(ALMATY).strftime('%Y%m%d_%H%M%S')}"
    run_dir = PROJECT_ROOT / "exports/validation" / run_id
    manifest_path = run_dir / "astana_warehouse_manual_stock_count_2026_06_04_after_daily_shipments.scenario.json"
    aggregate_csv_path = run_dir / "astana_warehouse_manual_stock_count_2026_06_04_after_daily_shipments.scenario_aggregate.csv"
    quarantine_path = run_dir / "3_in_1_men_sets_quarantine.csv"
    mapping_path = run_dir / "canonical_mapping_check.csv"
    trusted_path = run_dir / "trusted_post_anchor_shipments.csv"
    excluded_path = run_dir / "excluded_post_anchor_order_movements.csv"
    replay_path = run_dir / "current_stock_replay_dry_run.csv"

    manifest = build_scenario_manifest()
    pre.write_json(manifest_path, manifest)
    write_manual_stock_aggregate_csv(manifest, aggregate_csv_path)
    pre.write_csv(
        quarantine_path,
        pre.quarantine_rows(),
        ["source_label", "source_image", "source_sku_key", "canonical_size", "quantity", "quarantine_reason", "status"],
    )

    conn = sqlite3.connect(pre.DB_PATH)
    conn.row_factory = sqlite3.Row
    original_anchor = pre.ANCHOR_SQLITE_TS
    try:
        mapping = pre.validate_mapping(conn, manifest)
        pre.write_csv(
            mapping_path,
            mapping,
            [
                "row_id",
                "relation",
                "expected_sku_key",
                "expected_sku_id",
                "expected_size",
                "actual_sku_key",
                "actual_size",
                "dim_sku_size_active",
                "dim_sku_active",
                "article_map_active_rows",
                "status",
                "reason",
            ],
        )

        timing_adjustment = latest_june4_trusted_shipments_excluded(conn, manifest)
        pre.ANCHOR_SQLITE_TS = ANCHOR_SQLITE_TS
        trusted, excluded, deductions = pre.shipment_replay(conn, manifest, as_of_date=args.as_of_date)
        shipment_fields = [
            "stock_pool_id",
            "anchor_sku_id",
            "anchor_sku_key",
            "anchor_size",
            "order_id",
            "store_code",
            "order_sku_key",
            "order_sku_id",
            "order_size",
            "quantity",
            "ship_datetime",
            "ship_datetime_source",
            "planned_shipment_date",
            "kaspi_status",
            "internal_status",
            "kaspi_status_detail",
            "kaspi_offer_name",
            "source",
            "source_file",
            "mapping_blocker",
            "exclude_reason",
        ]
        pre.write_csv(trusted_path, trusted, shipment_fields)
        pre.write_csv(excluded_path, excluded, shipment_fields)
        latest_snapshot_date, snapshot = pre.latest_snapshot_by_pool(conn, manifest)
        replay_rows = pre.build_replay_rows(manifest, deductions, snapshot)
        pre.write_csv(
            replay_path,
            replay_rows,
            [
                "stock_pool_id",
                "sku_key",
                "sku_id",
                "applies_to_sku_ids",
                "canonical_size",
                "anchor_timestamp_at_almaty",
                "pre_shipment_anchor_qty",
                "trusted_post_anchor_shipped_qty",
                "estimated_current_stock_dry_run",
                "negative_stock_flag",
                "latest_db_snapshot_date",
                "latest_db_current_stock",
                "dry_run_delta_vs_latest_db_snapshot",
                "source_event_type",
                "source_delta",
                "source_images",
                "alias_snapshot_values_json",
            ],
        )
        db_anchor_existing_rows = conn.execute(
            "SELECT COUNT(*) FROM stock_anchor WHERE anchor_id = ? OR source_path = ?",
            (BATCH_ID, str(manifest_path)),
        ).fetchone()[0]
        line51_s = conn.execute(
            """
            SELECT current_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ? AND sku_id = 'CL_OC_MEN_LINE51_WHITE_S'
            """,
            (latest_snapshot_date,),
        ).fetchone()
    finally:
        pre.ANCHOR_SQLITE_TS = original_anchor
        conn.close()

    mapping_failures = [row for row in mapping if row["status"] != "PASS"]
    size_conflicts = [row for row in trusted if row.get("mapping_blocker")]
    negative_rows = [row for row in replay_rows if row["negative_stock_flag"] == "true"]

    gate = "GREEN"
    gate_reasons: list[str] = []
    if mapping_failures:
        gate = "RED"
        gate_reasons.append("canonical dim_sku_size mapping failures")
    if size_conflicts:
        gate = "RED"
        gate_reasons.append("post-anchor shipment size conflicts")
    if negative_rows:
        gate = "RED"
        gate_reasons.append("negative dry-run current stock rows")
    if gate != "RED":
        gate = "YELLOW"
        gate_reasons.append("scenario only; DB apply not authorized and 3_in_1_men_sets quarantined")

    summary = {
        "generated_at": datetime.now(ALMATY).isoformat(timespec="seconds"),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "scenario": "after_2026_06_04_daily_shipments",
        "anchor_timestamp": ANCHOR_TIMESTAMP,
        "anchor_sqlite_timestamp": ANCHOR_SQLITE_TS,
        "manifest_path": str(manifest_path),
        "aggregate_csv_path": str(aggregate_csv_path),
        "quarantine_path": str(quarantine_path),
        "mapping_csv_path": str(mapping_path),
        "trusted_shipments_csv_path": str(trusted_path),
        "excluded_shipments_csv_path": str(excluded_path),
        "replay_csv_path": str(replay_path),
        "source_evidence": {
            "primary_ocr_report": pre.file_evidence(pre.SOURCE_REPORT),
            "merged_total_append": pre.file_evidence(pre.TOTAL_REPORT),
            "db_app": pre.file_evidence(pre.DB_PATH),
        },
        "manifest": {
            "batch_id": BATCH_ID,
            "rows": len(manifest["rows"]),
            "aggregate_rows": len(aggregate_manual_stock_counts(manifest)),
            "units": manifest["expected_totals"]["total_units"],
        },
        "mapping": {
            "rows_checked": len(mapping),
            "failures": len(mapping_failures),
        },
        "quarantine": {
            "rows": len(pre.quarantine_rows()),
            "units": sum(row["quantity"] for row in pre.quarantine_rows()),
            "reason": "canonical SKU/card mapping pending",
        },
        "line51_s": {
            "manifest_row_present": any(row["sku_id"] == "CL_OC_MEN_LINE51_WHITE_S" for row in manifest["rows"]),
            "latest_db_current_stock": "" if line51_s is None else int(line51_s["current_stock"] or 0),
        },
        "shared_pool": {
            "rombik_s_rows": sum(1 for row in manifest["rows"] if row["stock_pool_id"] == "SHARED_ROMBIK_BLACK_S_MEN_KIDS"),
        },
        "timing_adjustment": timing_adjustment,
        "shipments": {
            "query_window": f"{ANCHOR_TIMESTAMP} < ship_datetime <= {args.as_of_date} 23:59:59 Asia/Almaty",
            "trusted_rows": len(trusted),
            "trusted_quantity": sum(int(row["quantity"] or 0) for row in trusted),
            "trusted_size_conflict_rows": len(size_conflicts),
            "excluded_rows": len(excluded),
        },
        "stock_mismatches": {
            "negative_rows": len(negative_rows),
            "samples": negative_rows[:5],
        },
        "latest_snapshot_date": latest_snapshot_date,
        "db_anchor_existing_rows": int(db_anchor_existing_rows),
        "db_write": {
            "performed": False,
            "backup_path": "",
            "rollback": "No DB write performed. Remove generated scenario artifacts only if this dry-run should be discarded.",
        },
        "gate": gate,
        "gate_reason": "; ".join(gate_reasons),
    }
    closeout_path = run_dir / "closeout.md"
    closeout_path.write_text(render_closeout(summary), encoding="utf-8")
    summary["closeout_path"] = str(closeout_path)
    write_summary_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of-date", default="2026-06-12", help="Replay through this date, inclusive")
    parser.add_argument("--run-id", default="", help="Optional deterministic validation run id")
    args = parser.parse_args()
    summary = build(args)
    if summary["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
