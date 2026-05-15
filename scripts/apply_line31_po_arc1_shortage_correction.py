#!/usr/bin/env python3
"""
Persist the LINE31 PO-ARC-1 shortage correction into audit_decisions.

Default: DRY RUN. Apply requires ENABLE_INVENTORY_CORRECTION_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.po.receipt_corrections import (
    CORRECTION_DECISION_TYPE,
    LINE31_PO_ARC1_CORRECTION_KEY,
    LINE31_PO_ARC1_DECISION_DATE,
    LINE31_PO_ARC1_STORE_CODE,
    build_line31_po_arc1_input_snapshot,
    build_line31_po_arc1_payload,
)


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups" / "line31_po_arc1_shortage_correction"
DEFAULT_REPORT = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "line31_po_arc1_shortage_correction"
    / "2026-04-24"
    / "apply_report.md"
)
WRITE_ENV_GATE = "ENABLE_INVENTORY_CORRECTION_WRITE"
EXPECTED_RAW_BASELINE = {
    "po_line_row_count": 36,
    "raw_po_line_units_total_sets": 265,
    "raw_po_line_units_received_sets": 265,
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _load_po_arc1_raw_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    po_row = conn.execute(
        """
        SELECT
            COUNT(*) AS po_line_row_count,
            COALESCE(SUM(order_qty), 0) AS raw_po_line_units_total_sets,
            COALESCE(SUM(received_qty), 0) AS raw_po_line_units_received_sets
        FROM po_line
        WHERE po_id = 'PO_ARC-1'
        """,
    ).fetchone()
    if po_row is None:
        raise RuntimeError("PO_ARC-1 not found in po_line; refusing to write correction blind.")
    return {
        "po_line_row_count": int(po_row["po_line_row_count"] or 0),
        "raw_po_line_units_total_sets": int(po_row["raw_po_line_units_total_sets"] or 0),
        "raw_po_line_units_received_sets": int(po_row["raw_po_line_units_received_sets"] or 0),
    }


def _assert_expected_raw_baseline(raw_snapshot: dict[str, Any]) -> None:
    row_count = int(raw_snapshot.get("po_line_row_count") or 0)
    if row_count == 0:
        raise RuntimeError("PO-ARC-1 has zero po_line rows; refusing to write correction against an empty baseline.")

    mismatches = []
    for key, expected in EXPECTED_RAW_BASELINE.items():
        actual = int(raw_snapshot.get(key) or 0)
        if actual != expected:
            mismatches.append(f"{key} expected={expected} actual={actual}")

    if mismatches:
        mismatch_text = ", ".join(mismatches)
        raise RuntimeError(f"Unexpected PO-ARC-1 raw baseline; refusing to write correction. {mismatch_text}")


def _load_existing_correction_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM audit_decisions
        WHERE decision_type = ?
          AND store_code = ?
          AND sku_key = ?
        """,
        (CORRECTION_DECISION_TYPE, LINE31_PO_ARC1_STORE_CODE, LINE31_PO_ARC1_CORRECTION_KEY),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def apply_correction(
    *,
    db_path: Path,
    backup_root: Path,
    report_path: Path,
    apply: bool,
) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    backup_path: Path | None = None
    payload = build_line31_po_arc1_payload()

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "audit_decisions"):
            raise RuntimeError("audit_decisions table missing; no safe existing correction surface found.")
        if not _table_exists(conn, "po_line"):
            raise RuntimeError("po_line table missing; cannot verify PO_ARC-1 baseline.")

        raw_snapshot = _load_po_arc1_raw_snapshot(conn)
        _assert_expected_raw_baseline(raw_snapshot)
        input_snapshot = build_line31_po_arc1_input_snapshot(**raw_snapshot)
        before_count = _load_existing_correction_count(conn)

        lines = [
            "# LINE31 PO-ARC-1 Shortage Correction Apply Report",
            "",
            f"- db_path: `{db_path}`",
            f"- apply: `{apply}`",
            f"- env_gate: `{WRITE_ENV_GATE}`",
            f"- existing_correction_rows_before: `{before_count}`",
            f"- raw_po_line_units_total_sets: `{raw_snapshot['raw_po_line_units_total_sets']}`",
            f"- raw_po_line_units_received_sets: `{raw_snapshot['raw_po_line_units_received_sets']}`",
            f"- raw_po_line_row_count: `{raw_snapshot['po_line_row_count']}`",
            f"- payload_ordered_pieces: `{payload['ordered_pieces']}`",
            f"- payload_received_pieces: `{payload['received_pieces']}`",
            f"- payload_net_shortage_pieces: `{payload['net_shortage_pieces']}`",
            f"- payload_compensation_claim_pieces: `{payload['compensation_claim_pieces']}`",
            "",
            "## Source Paths",
        ]
        for source_path in payload["source_evidence_paths"]:
            lines.append(f"- `{source_path}`")

        if apply:
            if str(os.environ.get(WRITE_ENV_GATE) or "").strip() != "1":
                raise RuntimeError(f"{WRITE_ENV_GATE}=1 is required with --apply")
            backup_root.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_root / f"app_db_pre_line31_po_arc1_shortage_correction_{timestamp}.db"
            shutil.copy2(db_path, backup_path)

            conn.execute(
                """
                DELETE FROM audit_decisions
                WHERE decision_type = ?
                  AND store_code = ?
                  AND sku_key = ?
                """,
                (CORRECTION_DECISION_TYPE, LINE31_PO_ARC1_STORE_CODE, LINE31_PO_ARC1_CORRECTION_KEY),
            )
            conn.execute(
                """
                INSERT INTO audit_decisions (
                    decision_date,
                    decision_type,
                    store_code,
                    sku_key,
                    input_snapshot,
                    output_snapshot,
                    human_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    LINE31_PO_ARC1_DECISION_DATE,
                    CORRECTION_DECISION_TYPE,
                    LINE31_PO_ARC1_STORE_CODE,
                    LINE31_PO_ARC1_CORRECTION_KEY,
                    json.dumps(input_snapshot, ensure_ascii=True, sort_keys=True),
                    json.dumps(payload, ensure_ascii=True, sort_keys=True),
                    "APPROVED",
                ),
            )
            conn.commit()

        after_count = _load_existing_correction_count(conn)
        lines.extend(
            [
                "",
                "## Result",
                f"- existing_correction_rows_after: `{after_count}`",
                f"- backup_path: `{backup_path}`" if backup_path else "- backup_path: `not_created_dry_run`",
                (
                    "- rollback_command: "
                    f"`cp '{backup_path}' '{db_path}'`"
                    if backup_path
                    else "- rollback_command: `not_applicable_dry_run`"
                ),
                "- status: `APPLIED`" if apply else "- status: `DRY_RUN_NO_WRITE`",
            ]
        )
        _write_report(report_path, lines)
        return {
            "applied": apply,
            "backup_path": str(backup_path) if backup_path else None,
            "report_path": str(report_path),
            "before_count": before_count,
            "after_count": after_count,
            "raw_snapshot": raw_snapshot,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist the LINE31 PO-ARC-1 shortage correction into audit_decisions")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--apply", action="store_true", help="Apply DB write (default: dry-run)")
    args = parser.parse_args()

    result = apply_correction(
        db_path=args.db.resolve(),
        backup_root=args.backup_root.resolve(),
        report_path=args.report_path.resolve(),
        apply=args.apply,
    )
    print(f"report_path={result['report_path']}")
    print(f"backup_path={result['backup_path'] or 'not_created_dry_run'}")
    print(f"correction_rows_before={result['before_count']}")
    print(f"correction_rows_after={result['after_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
