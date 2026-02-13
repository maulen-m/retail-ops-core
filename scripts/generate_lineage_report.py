#!/usr/bin/env python3
"""
Generate per-run lineage artifact (read-only).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _view_exists(conn: sqlite3.Connection, view: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name=?",
        (view,),
    ).fetchone()
    return row is not None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sales_truth_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if _view_exists(conn, "view_sales_line_truth"):
        row = conn.execute(
            """
            SELECT COUNT(*) AS line_count, MIN(sale_date) AS min_date, MAX(sale_date) AS max_date
            FROM view_sales_line_truth
            """
        ).fetchone()
        return {
            "source": "view_sales_line_truth",
            "line_count": int(row[0] or 0),
            "min_date": row[1],
            "max_date": row[2],
        }

    if _table_exists(conn, "sales_fact_v2"):
        row = conn.execute(
            """
            SELECT COUNT(*) AS line_count, MIN(order_date) AS min_date, MAX(order_date) AS max_date
            FROM sales_fact_v2
            WHERE COALESCE(return_flag, 0) = 0
            """
        ).fetchone()
        return {
            "source": "sales_fact_v2",
            "line_count": int(row[0] or 0),
            "min_date": row[1],
            "max_date": row[2],
        }

    return {"source": None, "line_count": 0, "min_date": None, "max_date": None}


def _cashflow_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return {"event_count": 0, "min_date": None, "max_date": None}
    row = conn.execute(
        """
        SELECT COUNT(*) AS event_count, MIN(event_date) AS min_date, MAX(event_date) AS max_date
        FROM fact_cashflow_events
        """
    ).fetchone()
    return {
        "event_count": int(row[0] or 0),
        "min_date": row[1],
        "max_date": row[2],
    }


def generate_lineage_report(
    *,
    db_path: Path = DEFAULT_DB,
    workbook_path: Path | None = None,
    output_path: Path | None = None,
    strict_exit_code: int | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    workbook = workbook_path.expanduser() if workbook_path is not None else None
    workbook_info = {
        "path": str(workbook) if workbook is not None else None,
        "sha256": _sha256(workbook) if workbook is not None and workbook.exists() else None,
    }

    conn = sqlite3.connect(str(db_path))
    try:
        user_version = int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)
        report = {
            "generated_at": ts,
            "db_path": str(db_path),
            "schema_user_version": user_version,
            "strict_exit_code": strict_exit_code,
            "workbook": workbook_info,
            "sales_truth": _sales_truth_summary(conn),
            "cashflow": _cashflow_summary(conn),
        }
    finally:
        conn.close()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate lineage report artifact")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict-exit-code", type=int, default=None)
    args = parser.parse_args()

    report = generate_lineage_report(
        db_path=args.db,
        workbook_path=args.workbook,
        output_path=args.output,
        strict_exit_code=args.strict_exit_code,
    )
    print(
        "lineage_report:",
        f"output={args.output}",
        f"sales_source={report['sales_truth']['source']}",
        f"sales_lines={report['sales_truth']['line_count']}",
        f"cashflow_events={report['cashflow']['event_count']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
