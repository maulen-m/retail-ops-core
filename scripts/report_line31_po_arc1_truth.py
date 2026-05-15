#!/usr/bin/env python3
"""Report LINE31 PO-ARC-1 correction status and current LINE31 live stock from Autonomous Business truth only."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.po.receipt_corrections import get_receipt_correction


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "line31_po_arc1_shortage_correction"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def parse_as_of(value: str | None) -> date:
    text = str(value or "").strip()
    if not text:
        return date.today()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO date: {value!r}") from exc


def resolve_output_dir(output_dir: Path | None, *, as_of_date: date) -> Path:
    if output_dir is not None:
        return output_dir
    return DEFAULT_OUTPUT_ROOT / as_of_date.isoformat()


def build_truth_report(db_path: Path, *, as_of_date: date) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        correction = get_receipt_correction(conn, "PO_ARC-1")
        if not correction:
            raise RuntimeError("LINE31 PO-ARC-1 correction missing from audit_decisions.")

        raw_po = conn.execute(
            """
            SELECT
                COUNT(*) AS po_line_row_count,
                COALESCE(SUM(order_qty), 0) AS raw_ordered_sets,
                COALESCE(SUM(received_qty), 0) AS raw_received_sets
            FROM po_line
            WHERE po_id = 'PO_ARC-1'
            """
        ).fetchone()

        sales_row = conn.execute(
            """
            SELECT
                COUNT(*) AS sales_rows,
                COALESCE(SUM(quantity), 0) AS sold_sets
            FROM sales_fact_v2
            WHERE sku_key LIKE 'CL_OF_ARC_WM_LINE31%'
              AND status NOT IN ('CANCELLED', 'RETURNED')
            """
        ).fetchone() if _table_exists(conn, "sales_fact_v2") else None

        ledger_rows = conn.execute(
            """
            SELECT event_type, COUNT(*) AS row_count, COALESCE(SUM(qty_change), 0) AS qty_change
            FROM stock_ledger
            WHERE sku_key LIKE 'CL_OF_ARC_WM_LINE31%'
            GROUP BY event_type
            ORDER BY event_type
            """
        ).fetchall() if _table_exists(conn, "stock_ledger") else []

        current_row = conn.execute(
            """
            SELECT COALESCE(SUM(qty_change), 0) AS current_sets
            FROM stock_ledger
            WHERE sku_key LIKE 'CL_OF_ARC_WM_LINE31%'
            """
        ).fetchone() if _table_exists(conn, "stock_ledger") else None

        inbound_row = conn.execute(
            """
            SELECT COALESCE(SUM(order_qty - COALESCE(received_qty, 0)), 0) AS pending_sets
            FROM po_line
            WHERE sku_key LIKE 'CL_OF_ARC_WM_LINE31%'
              AND status IN ('PENDING', 'PARTIAL', 'IN_TRANSIT')
            """
        ).fetchone() if _table_exists(conn, "po_line") else None

        latest_snapshot = conn.execute(
            """
            SELECT snapshot_date,
                   COALESCE(SUM(current_stock), 0) AS current_sets,
                   COALESCE(SUM(inbound_stock), 0) AS inbound_sets
            FROM fact_inventory_snapshot_size
            WHERE sku_key LIKE 'CL_OF_ARC_WM_LINE31%'
            GROUP BY snapshot_date
            ORDER BY snapshot_date DESC
            LIMIT 1
            """
        ).fetchone() if _table_exists(conn, "fact_inventory_snapshot_size") else None

    return {
        "as_of_date": as_of_date.isoformat(),
        "db_path": str(db_path),
        "correction": correction,
        "historical_raw_po_line_sets": {
            "po_line_row_count": int(raw_po["po_line_row_count"] or 0) if raw_po else 0,
            "ordered_sets": int(raw_po["raw_ordered_sets"] or 0) if raw_po else 0,
            "received_sets": int(raw_po["raw_received_sets"] or 0) if raw_po else 0,
        },
        "current_line31_truth": {
            "basis": "complete_set_skus_from_autonomous_business_db_only",
            "current_live_sets": int(current_row["current_sets"] or 0) if current_row else 0,
            "pending_inbound_sets": int(inbound_row["pending_sets"] or 0) if inbound_row else 0,
            "sales_fact_sets": int(sales_row["sold_sets"] or 0) if sales_row else 0,
            "sales_fact_rows": int(sales_row["sales_rows"] or 0) if sales_row else 0,
            "movement_classes_used": [dict(row) for row in ledger_rows],
            "movement_date_window_note": "Current stock derived from stock_ledger cumulative balance as of report time.",
            "guardrails": [
                "No Sourcing current-stock import used.",
                "177 compensation claim preserved separately from 157 net shortage.",
                "Current live LINE31 was recomputed from Autonomous Business DB inventory/sales surfaces only.",
            ],
        },
        "latest_snapshot_context": (
            {
                "snapshot_date": latest_snapshot["snapshot_date"],
                "snapshot_current_sets": int(latest_snapshot["current_sets"] or 0),
                "snapshot_inbound_sets": int(latest_snapshot["inbound_sets"] or 0),
            }
            if latest_snapshot
            else None
        ),
    }


def write_report(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "line31_po_arc1_truth_report.json"
    md_path = output_dir / "line31_po_arc1_truth_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    correction_payload = report["correction"]["payload"]
    current_truth = report["current_line31_truth"]
    raw_po = report["historical_raw_po_line_sets"]
    lines = [
        "# LINE31 PO-ARC-1 Truth Report",
        "",
        f"- as_of_date: `{report['as_of_date']}`",
        f"- db_path: `{report['db_path']}`",
        "",
        "## Historical Correction",
        f"- po_id: `{correction_payload['po_id']}`",
        f"- unit_basis: `{correction_payload['unit_basis']}`",
        f"- ordered_pieces: `{correction_payload['ordered_pieces']}`",
        f"- received_pieces: `{correction_payload['received_pieces']}`",
        f"- net_shortage_pieces: `{correction_payload['net_shortage_pieces']}`",
        f"- compensation_claim_pieces: `{correction_payload['compensation_claim_pieces']}`",
        f"- compensation_claim_by_model: `{correction_payload['compensation_claim_by_model']}`",
        f"- compensation_value_cny: `{correction_payload['compensation_value_cny']}`",
        "",
        "## Raw PO Line Context",
        f"- raw_ordered_sets: `{raw_po['ordered_sets']}`",
        f"- raw_received_sets: `{raw_po['received_sets']}`",
        f"- po_line_row_count: `{raw_po['po_line_row_count']}`",
        "",
        "## Current LINE31 Live Truth",
        f"- basis: `{current_truth['basis']}`",
        f"- current_live_sets: `{current_truth['current_live_sets']}`",
        f"- pending_inbound_sets: `{current_truth['pending_inbound_sets']}`",
        f"- sales_fact_sets: `{current_truth['sales_fact_sets']}`",
        f"- sales_fact_rows: `{current_truth['sales_fact_rows']}`",
        "",
        "## Movement Classes Used",
    ]
    for row in current_truth["movement_classes_used"]:
        lines.append(
            f"- `{row['event_type']}`: rows=`{row['row_count']}`, qty_change=`{row['qty_change']}`"
        )
    if report["latest_snapshot_context"]:
        snapshot = report["latest_snapshot_context"]
        lines.extend(
            [
                "",
                "## Latest Snapshot Context",
                f"- snapshot_date: `{snapshot['snapshot_date']}`",
                f"- snapshot_current_sets: `{snapshot['snapshot_current_sets']}`",
                f"- snapshot_inbound_sets: `{snapshot['snapshot_inbound_sets']}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Guardrails",
        ]
    )
    for note in current_truth["guardrails"]:
        lines.append(f"- {note}")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Report LINE31 PO-ARC-1 correction and current Autonomous Business LINE31 truth")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--as-of", type=parse_as_of, default=date.today(), help="Report metadata/output date in YYYY-MM-DD")
    parser.add_argument("--strict", action="store_true", help="Return non-zero if the correction is missing")
    args = parser.parse_args()

    try:
        report = build_truth_report(args.db.resolve(), as_of_date=args.as_of)
    except Exception:
        if args.strict:
            raise
        raise

    output_dir = resolve_output_dir(args.output_dir.resolve() if args.output_dir else None, as_of_date=args.as_of)
    paths = write_report(report, output_dir)
    print(f"json_path={paths['json_path']}")
    print(f"md_path={paths['md_path']}")
    print(f"current_live_sets={report['current_line31_truth']['current_live_sets']}")
    print(f"pending_inbound_sets={report['current_line31_truth']['pending_inbound_sets']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
