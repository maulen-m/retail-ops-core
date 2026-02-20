#!/usr/bin/env python3
"""Validate offer->stock mapping quality for pricelist sync."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, get_db

DEFAULT_TABLE = "fact_offer_stock_mapper_current"
DEFAULT_STORES = ("UNIVERSAL", "STOREB")


def _safe_table_name(table_name: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table_name):
        raise ValueError(f"Unsafe table name: {table_name}")
    return table_name


def _normalize_stores(stores: list[str] | tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for raw in stores:
        value = str(raw or "").strip().upper()
        if value and value not in out:
            out.append(value)
    return out


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row)


def validate_offer_stock_sync(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    stores: list[str] | tuple[str, ...] = DEFAULT_STORES,
    table_name: str = DEFAULT_TABLE,
    max_unresolved: int = 0,
    min_confident_rate: float = 0.95,
    require_snapshot_coverage: bool = True,
) -> dict[str, Any]:
    selected_stores = _normalize_stores(stores)
    if not selected_stores:
        raise ValueError("stores list is empty")

    mapper_table = _safe_table_name(table_name)
    errors: list[str] = []

    with get_db(db_path) as conn:
        if not _table_exists(conn, mapper_table):
            raise RuntimeError(f"{mapper_table} does not exist; run build_offer_stock_mapper first")

        placeholders = ",".join("?" for _ in selected_stores)
        rows = conn.execute(
            f"""
            SELECT
                store_code,
                COUNT(*) AS total_rows,
                SUM(
                    CASE
                        WHEN mapping_method != 'unresolved'
                         AND COALESCE(is_ambiguous, 0) = 0
                         AND mapping_confidence IN ('HIGH', 'MEDIUM')
                        THEN 1 ELSE 0
                    END
                ) AS confident_rows,
                SUM(CASE WHEN mapping_method = 'unresolved' THEN 1 ELSE 0 END) AS unresolved_rows,
                SUM(CASE WHEN COALESCE(is_ambiguous, 0) = 1 THEN 1 ELSE 0 END) AS ambiguous_rows
            FROM {mapper_table}
            WHERE store_code IN ({placeholders})
            GROUP BY store_code
            ORDER BY store_code
            """,
            tuple(selected_stores),
        ).fetchall()

        metrics_by_store: dict[str, dict[str, Any]] = {}
        for row in rows:
            total = int(row["total_rows"] or 0)
            confident = int(row["confident_rows"] or 0)
            unresolved = int(row["unresolved_rows"] or 0)
            ambiguous = int(row["ambiguous_rows"] or 0)
            confident_rate = float(confident / total) if total > 0 else 0.0
            metrics_by_store[str(row["store_code"]).upper()] = {
                "total_rows": total,
                "confident_rows": confident,
                "unresolved_rows": unresolved,
                "ambiguous_rows": ambiguous,
                "confident_rate": confident_rate,
                "missing_snapshot_rows": 0,
            }

        for store_code in selected_stores:
            if store_code not in metrics_by_store:
                errors.append(f"{store_code}: no mapper rows found")
                metrics_by_store[store_code] = {
                    "total_rows": 0,
                    "confident_rows": 0,
                    "unresolved_rows": 0,
                    "ambiguous_rows": 0,
                    "confident_rate": 0.0,
                    "missing_snapshot_rows": 0,
                }

        if require_snapshot_coverage and _table_exists(conn, "fact_inventory_snapshot_size"):
            latest_snapshot = conn.execute(
                "SELECT MAX(snapshot_date) AS snapshot_date FROM fact_inventory_snapshot_size"
            ).fetchone()["snapshot_date"]
            if not latest_snapshot:
                errors.append("fact_inventory_snapshot_size has no rows")
            else:
                missing_rows = conn.execute(
                    f"""
                    SELECT
                        m.store_code,
                        COUNT(*) AS missing_snapshot_rows
                    FROM {mapper_table} m
                    LEFT JOIN fact_inventory_snapshot_size s
                      ON s.snapshot_date = ?
                     AND s.sku_id = m.sku_id
                    WHERE m.store_code IN ({placeholders})
                      AND m.mapping_method != 'unresolved'
                      AND COALESCE(m.is_ambiguous, 0) = 0
                      AND COALESCE(TRIM(m.sku_id), '') != ''
                      AND s.sku_id IS NULL
                    GROUP BY m.store_code
                    """,
                    (latest_snapshot, *selected_stores),
                ).fetchall()
                missing_by_store = {
                    str(row["store_code"]).upper(): int(row["missing_snapshot_rows"] or 0)
                    for row in missing_rows
                }
                for store_code in selected_stores:
                    metrics_by_store[store_code]["missing_snapshot_rows"] = missing_by_store.get(store_code, 0)
        elif require_snapshot_coverage:
            errors.append("fact_inventory_snapshot_size table missing")

    for store_code in selected_stores:
        metric = metrics_by_store[store_code]
        if metric["unresolved_rows"] > max_unresolved:
            errors.append(
                f"{store_code}: unresolved_rows={metric['unresolved_rows']} > max_unresolved={max_unresolved}"
            )
        if metric["confident_rate"] < min_confident_rate:
            errors.append(
                f"{store_code}: confident_rate={metric['confident_rate']:.3f} < min_confident_rate={min_confident_rate:.3f}"
            )
        if require_snapshot_coverage and metric["missing_snapshot_rows"] > 0:
            errors.append(
                f"{store_code}: missing_snapshot_rows={metric['missing_snapshot_rows']} (latest snapshot missing for mapped sku_id)"
            )

    return {
        "db_path": str(db_path),
        "table_name": mapper_table,
        "stores": selected_stores,
        "max_unresolved": int(max_unresolved),
        "min_confident_rate": float(min_confident_rate),
        "require_snapshot_coverage": bool(require_snapshot_coverage),
        "metrics_by_store": metrics_by_store,
        "ok": len(errors) == 0,
        "errors": errors,
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"Mapper table: {report['table_name']}")
    print("store_code | total | confident | unresolved | ambiguous | confident_rate | missing_snapshot")
    for store_code in report["stores"]:
        metric = report["metrics_by_store"][store_code]
        print(
            f"{store_code} | {metric['total_rows']} | {metric['confident_rows']} | "
            f"{metric['unresolved_rows']} | {metric['ambiguous_rows']} | "
            f"{metric['confident_rate']:.3f} | {metric['missing_snapshot_rows']}"
        )
    if report["errors"]:
        print("Errors:")
        for error in report["errors"]:
            print(f"  - {error}")
    else:
        print("OK: validation passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate offer->stock mapping readiness")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--store",
        action="append",
        dest="stores",
        help="Store code (repeatable). Default: UNIVERSAL + STOREB",
    )
    parser.add_argument("--table-name", default=DEFAULT_TABLE)
    parser.add_argument("--max-unresolved", type=int, default=0)
    parser.add_argument("--min-confident-rate", type=float, default=0.95)
    parser.add_argument(
        "--no-snapshot-coverage-check",
        action="store_true",
        help="Skip latest snapshot coverage check",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stores = args.stores if args.stores else list(DEFAULT_STORES)
    report = validate_offer_stock_sync(
        db_path=args.db,
        stores=stores,
        table_name=args.table_name,
        max_unresolved=args.max_unresolved,
        min_confident_rate=args.min_confident_rate,
        require_snapshot_coverage=not args.no_snapshot_coverage_check,
    )
    _print_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
