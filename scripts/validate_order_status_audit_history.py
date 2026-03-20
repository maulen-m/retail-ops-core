#!/usr/bin/env python3
"""Validate DB-backed order status audit history after WebUI/API observation capture."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.migrate_027_order_status_observations import validate_order_status_observation_schema

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "webui_archive_single_truth"


class OrderStatusAuditHistoryError(RuntimeError):
    """Raised when strict audit history validation fails."""


def validate_order_status_audit_history(
    *,
    db_path: Path,
    as_of: str,
    output_root: Path,
    strict: bool,
) -> dict[str, Any]:
    schema_errors = validate_order_status_observation_schema(db_path)
    if schema_errors:
        raise OrderStatusAuditHistoryError("; ".join(schema_errors))

    conn = sqlite3.connect(str(db_path))
    try:
        counts = conn.execute(
            """
            SELECT source, COUNT(*) AS rows
            FROM fact_order_status_observations
            GROUP BY source
            ORDER BY source
            """
        ).fetchall()
        duplicate_rows = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT order_id, store_code, status_internal, observed_at, source, COUNT(*) AS c
                FROM fact_order_status_observations
                GROUP BY 1,2,3,4,5
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    finally:
        conn.close()

    counts_map = {str(row[0]): int(row[1]) for row in counts}
    ok = counts_map.get("WEBUI", 0) > 0 and counts_map.get("API", 0) > 0 and int(duplicate_rows) == 0
    output_dir = output_root.resolve() / as_of
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "strict": bool(strict),
        "as_of": as_of,
        "counts_by_source": counts_map,
        "duplicate_rows": int(duplicate_rows),
    }
    report_path = output_dir / "order_status_audit_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["order_status_audit_report_json"] = str(report_path)
    if strict and not ok:
        raise OrderStatusAuditHistoryError(
            f"order status audit history failed: counts_by_source={counts_map} duplicate_rows={duplicate_rows}"
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate order status audit history")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_order_status_audit_history(
            db_path=args.db,
            as_of=str(args.as_of),
            output_root=args.output_root,
            strict=bool(args.strict),
        )
    except OrderStatusAuditHistoryError as exc:
        print("status=FAIL")
        print("error_code=ORDER_STATUS_AUDIT_HISTORY_FAIL")
        print(f"message={exc}")
        return 1

    print(f"order_status_audit_report_json={report['order_status_audit_report_json']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
