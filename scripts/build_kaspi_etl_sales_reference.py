#!/usr/bin/env python3
"""Build normalized Kaspi ETL sales reference artifacts and optionally sync into DB."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.kaspi_etl_reference import build_reference_from_archive_dir

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "reference" / "kaspi_etl_sales_ref"


def _parse_as_of(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return date.today()


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Kaspi ETL Sales Reference Build",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- include_as_of_day: `{str(report['include_as_of_day']).lower()}`",
        f"- status: `{report['status']}`",
        f"- rows: `{report['rows']}`",
        f"- unresolved_warehouses: `{len(report['unresolved_warehouses'])}`",
        f"- db_sync_status: `{report['db_sync_status']}`",
        "",
        "## Outputs",
        "",
        f"- lines_csv: `{report['lines_csv']}`",
        f"- daily_by_store_csv: `{report['daily_by_store_csv']}`",
        f"- daily_total_csv: `{report['daily_total_csv']}`",
        f"- manifest_json: `{report['manifest_json']}`",
    ]
    if report.get("db_backup_path"):
        lines.append(f"- db_backup_path: `{report['db_backup_path']}`")
    if report["unresolved_warehouses"]:
        lines.extend(["", "## Unresolved Warehouses", ""])
        for warehouse in report["unresolved_warehouses"]:
            lines.append(f"- `{warehouse}`")
    return "\n".join(lines) + "\n"


def _ensure_target_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fact_sales_external_ref (
            line_id TEXT PRIMARY KEY,
            sale_date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            kd_warehouse TEXT,
            order_id TEXT NOT NULL,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity REAL NOT NULL,
            net_rev_kzt REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'DELIVERED',
            return_flag INTEGER NOT NULL DEFAULT 0,
            source_file TEXT,
            source_hash TEXT,
            source_tag TEXT NOT NULL DEFAULT 'KASPI_ETL_ARCHIVE',
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fact_sales_external_ref_day_store "
        "ON fact_sales_external_ref(sale_date, store_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fact_sales_external_ref_order "
        "ON fact_sales_external_ref(order_id)"
    )


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_sales_ref_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def _sync_reference_to_db(*, db_path: Path, rows: list[dict[str, Any]], backup_root: Path) -> dict[str, Any]:
    backup_path = _backup_db(db_path, backup_root)
    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_target_table(conn)
        if rows:
            min_day = min(str(row["sale_date"]) for row in rows)
            max_day = max(str(row["sale_date"]) for row in rows)
            conn.execute(
                """
                DELETE FROM fact_sales_external_ref
                WHERE source_tag = 'KASPI_ETL_ARCHIVE'
                  AND sale_date BETWEEN ? AND ?
                """,
                (min_day, max_day),
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO fact_sales_external_ref (
                    line_id, sale_date, store_code, kd_warehouse, order_id,
                    sku_key, sku_id, my_size, quantity, net_rev_kzt,
                    status, return_flag, source_file, source_hash, source_tag, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DELIVERED', 0, ?, ?, 'KASPI_ETL_ARCHIVE', ?)
                """,
                [
                    (
                        str(row["line_id"]),
                        str(row["sale_date"]),
                        str(row["store_code"]),
                        str(row.get("kd_warehouse") or ""),
                        str(row["order_id"]),
                        str(row.get("resolved_sku_key") or row.get("article") or ""),
                        str(row.get("resolved_sku_id") or row.get("article") or ""),
                        str(row.get("resolved_my_size") or ""),
                        float(row["quantity"]),
                        float(row["gross_rev_kzt"]),
                        str(row.get("source_file") or ""),
                        str(row["line_id"]),
                        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    )
                    for row in rows
                ],
            )
        conn.commit()
    finally:
        conn.close()
    return {"backup_path": str(backup_path), "rows_applied": len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/sync Kaspi ETL ArchiveOrders sales reference")
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--include-as-of-day", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-root", type=Path, default=PROJECT_ROOT / "backups")
    args = parser.parse_args()

    as_of = _parse_as_of(args.as_of)
    output_dir = args.output_root.resolve() / as_of.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    reference = build_reference_from_archive_dir(
        archive_dir=args.archive_dir.resolve(),
        as_of=as_of,
        include_as_of_day=bool(args.include_as_of_day),
        db_path=args.db.resolve() if args.db else None,
    )
    if reference.get("status") != "available":
        raise RuntimeError(f"reference build failed: {reference.get('reason')}")

    unresolved = list(reference.get("unresolved_warehouses") or [])
    if args.strict and unresolved:
        raise RuntimeError(f"unresolved warehouses in strict mode: {', '.join(unresolved)}")

    lines_df = reference["lines"].copy()
    daily_by_store_df = reference["daily_by_store"].copy()
    daily_total_df = reference["daily_total"].copy()

    lines_csv = output_dir / "delivered_lines.csv"
    daily_by_store_csv = output_dir / "delivered_daily_by_store.csv"
    daily_total_csv = output_dir / "delivered_daily_total.csv"
    manifest_json = output_dir / "manifest.json"

    lines_df.to_csv(lines_csv, index=False, encoding="utf-8")
    daily_by_store_df.to_csv(daily_by_store_csv, index=False, encoding="utf-8")
    daily_total_df.to_csv(daily_total_csv, index=False, encoding="utf-8")
    manifest_payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "include_as_of_day": bool(args.include_as_of_day),
        "status": reference.get("status"),
        "reason": reference.get("reason"),
        "files": reference.get("files"),
        "manifest": reference.get("manifest"),
        "store_map": reference.get("store_map"),
        "unresolved_warehouses": reference.get("unresolved_warehouses"),
        "rows": int(len(lines_df)),
    }
    manifest_json.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    db_sync_status = "DRY_RUN"
    db_backup_path = None
    if args.apply:
        if str(os.environ.get("ENABLE_SALES_REFERENCE_APPLY") or "").strip() != "1":
            raise RuntimeError("apply requested, but ENABLE_SALES_REFERENCE_APPLY=1 is required")
        sync = _sync_reference_to_db(
            db_path=args.db.resolve(),
            rows=lines_df.to_dict("records"),
            backup_root=args.backup_root.resolve(),
        )
        db_sync_status = "APPLIED"
        db_backup_path = sync["backup_path"]

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "include_as_of_day": bool(args.include_as_of_day),
        "status": "PASS" if (not args.strict or not unresolved) else "FAIL",
        "rows": int(len(lines_df)),
        "unresolved_warehouses": unresolved,
        "db_sync_status": db_sync_status,
        "db_backup_path": db_backup_path,
        "lines_csv": str(lines_csv),
        "daily_by_store_csv": str(daily_by_store_csv),
        "daily_total_csv": str(daily_total_csv),
        "manifest_json": str(manifest_json),
    }
    report_json = output_dir / "reference_build_report.json"
    report_md = output_dir / "reference_build_report.md"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(_render_md(report), encoding="utf-8")

    print(f"reference_build_json={report_json}")
    print(f"reference_build_md={report_md}")
    print(f"db_sync_status={db_sync_status}")
    if db_backup_path:
        print(f"db_backup_path={db_backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
