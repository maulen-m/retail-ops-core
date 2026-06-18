#!/usr/bin/env python3
"""Apply exact owner-approved COGS overrides for retained LINE child rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
REQUIRED_ENV = "ENABLE_OWNER_APPROVED_LINE_CHILD_COGS_ROW_WRITE"
SOURCE = "OWNER_APPROVED_LINE51_PARENT_UNIT_COGS_20260601"
DEFAULT_OWNER_DECISION_REF = "THREAD_GOAL_OWNER_APPROVED_REQUIRED_ACTIONS_20260601"
NEW_EXACT_ROW_OWNER_DECISION_REF = "OWNER_COGS_OVERRIDE_2026_06_14_953395459"
FREEZE_COST_BASIS_OWNER_DECISION_REF = "OWNER_COGS_COST_BASIS_OVERRIDE_2026_06_14_956748585"

APPROVED_ROWS = [
    {
        "order_id": "929183530",
        "store_code": "ACMEWEAR",
        "sku_key": "LINE-31-LS",
        "sku_id": "LINE-31-LS_2XL",
        "unit_cogs_kzt": 6006.76,
        "owner_decision_ref": DEFAULT_OWNER_DECISION_REF,
        "expected_quantity": 1.0,
        "expected_net_rev": 8563.0,
        "notes": "Owner-approved LINE51 parent-unit landed COGS for exact retained child-bundle row.",
    },
    {
        "order_id": "934547752",
        "store_code": "ACMEWEAR",
        "sku_key": "LINE-21-TS",
        "sku_id": "LINE-21-TS_3XL",
        "unit_cogs_kzt": 6006.76,
        "owner_decision_ref": DEFAULT_OWNER_DECISION_REF,
        "expected_quantity": 1.0,
        "expected_net_rev": 6563.0,
        "notes": "Owner-approved LINE51 parent-unit landed COGS for exact retained child-bundle row.",
    },
    {
        "order_id": "953395459",
        "store_code": "ACMEWEAR",
        "sku_key": "LINE-31-LS",
        "sku_id": "LINE-31-LS_XL",
        "unit_cogs_kzt": 6006.76,
        "owner_decision_ref": NEW_EXACT_ROW_OWNER_DECISION_REF,
        "expected_quantity": 1.0,
        "expected_net_rev": 9215.0,
        "notes": "Owner-approved exact-row LINE51 parent-unit landed COGS for LINE-31-LS_XL.",
    },
    {
        "order_id": "956748585",
        "store_code": "ACMEWEAR",
        "sku_key": "LINE-21-TS",
        "sku_id": "LINE-21-TS_3XL",
        "unit_cogs_kzt": 6006.76,
        "owner_decision_ref": FREEZE_COST_BASIS_OWNER_DECISION_REF,
        "expected_quantity": 1.0,
        "expected_net_rev": 7563.0,
        "notes": "Owner-approved exact-row LINE51 parent-unit landed COGS/cost basis for LINE-21-TS_3XL.",
    },
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_backup(source_path: Path, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    src_uri = source_path.resolve().as_uri() + "?mode=ro"
    source = sqlite3.connect(src_uri, uri=True)
    dest = sqlite3.connect(str(backup_path))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()


def _dict_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _owner_decision_refs() -> list[str]:
    return sorted({str(row.get("owner_decision_ref") or DEFAULT_OWNER_DECISION_REF) for row in APPROVED_ROWS})


def _ensure_override_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fact_sales_owner_cogs_override (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            unit_cogs_kzt REAL NOT NULL,
            cogs_source TEXT NOT NULL,
            owner_decision_ref TEXT NOT NULL,
            notes TEXT,
            active_flag INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(order_id, store_code, sku_key, sku_id, owner_decision_ref)
        )
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(fact_sales_owner_cogs_override)").fetchall()}
    required = {
        "order_id",
        "store_code",
        "sku_key",
        "sku_id",
        "unit_cogs_kzt",
        "cogs_source",
        "owner_decision_ref",
        "active_flag",
    }
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError(
            "fact_sales_owner_cogs_override exists but is missing required columns: "
            + ", ".join(missing)
        )


def _validate_target_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    for row in APPROVED_ROWS:
        matches = _dict_rows(
            conn,
            """
            SELECT order_id, order_date, store_code, sku_key, sku_id, quantity, net_rev, cogs, profit, status, return_flag
            FROM sales_fact_v2
            WHERE order_id = ?
              AND UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) = ?
              AND sku_key = ?
              AND sku_id = ?
            """,
            (
                row["order_id"],
                row["store_code"],
                row["sku_key"],
                row["sku_id"],
            ),
        )
        if len(matches) != 1:
            raise RuntimeError(
                f"expected exactly one sales_fact_v2 row for {row['order_id']} / {row['sku_id']}, found {len(matches)}"
            )
        match = matches[0]
        if float(match["quantity"] or 0.0) != float(row["expected_quantity"]):
            raise RuntimeError(f"quantity mismatch for {row['order_id']} / {row['sku_id']}: {match['quantity']}")
        if round(float(match["net_rev"] or 0.0), 2) != round(float(row["expected_net_rev"]), 2):
            raise RuntimeError(f"net_rev mismatch for {row['order_id']} / {row['sku_id']}: {match['net_rev']}")
        observed.append(match)
    return observed


def _capture_truth(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_sales_truth_views(conn)
    target_pairs = [(row["order_id"], row["sku_id"]) for row in APPROVED_ROWS]
    target_rows: list[dict[str, Any]] = []
    for order_id, sku_id in target_pairs:
        target_rows.extend(
            _dict_rows(
                conn,
                """
                SELECT order_id, sale_date, store_code, sku_key, sku_id, units,
                       net_rev_kzt, cogs_kzt, profit_kzt, cogs_source,
                       source_cogs_kzt, source_profit_kzt
                FROM view_sales_line_truth
                WHERE order_id = ?
                  AND sku_id = ?
                ORDER BY order_id, sku_id
                """,
                (order_id, sku_id),
            )
        )
    unresolved_window = _dict_rows(
        conn,
        """
        SELECT order_id, sale_date, store_code, sku_key, sku_id, units,
               net_rev_kzt, cogs_kzt, profit_kzt, cogs_source
        FROM view_sales_line_truth
        WHERE date(sale_date) BETWEEN '2026-05-02' AND '2026-06-16'
          AND (
              cogs_source = 'unresolved'
              OR cogs_kzt IS NULL
              OR profit_kzt IS NULL
          )
        ORDER BY sale_date, order_id, sku_id
        """,
    )
    overrides = []
    if _table_exists(conn, "fact_sales_owner_cogs_override"):
        refs = _owner_decision_refs()
        placeholders = ", ".join("?" for _ in refs)
        overrides = _dict_rows(
            conn,
            f"""
            SELECT order_id, store_code, sku_key, sku_id, unit_cogs_kzt,
                   cogs_source, owner_decision_ref, active_flag, notes
            FROM fact_sales_owner_cogs_override
            WHERE owner_decision_ref IN ({placeholders})
            ORDER BY order_id, sku_id, owner_decision_ref
            """,
            tuple(refs),
        )
    return {
        "target_rows": target_rows,
        "unresolved_window_rows": unresolved_window,
        "unresolved_window_count": len(unresolved_window),
        "owner_cogs_overrides": overrides,
    }


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _apply(conn: sqlite3.Connection) -> None:
    _ensure_override_table(conn)
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    for row in APPROVED_ROWS:
        owner_decision_ref = str(row.get("owner_decision_ref") or DEFAULT_OWNER_DECISION_REF)
        conn.execute(
            """
            INSERT INTO fact_sales_owner_cogs_override (
                order_id, store_code, sku_key, sku_id, unit_cogs_kzt,
                cogs_source, owner_decision_ref, notes, active_flag, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(order_id, store_code, sku_key, sku_id, owner_decision_ref)
            DO UPDATE SET
                unit_cogs_kzt=excluded.unit_cogs_kzt,
                cogs_source=excluded.cogs_source,
                notes=excluded.notes,
                active_flag=1,
                updated_at=excluded.updated_at
            WHERE fact_sales_owner_cogs_override.unit_cogs_kzt IS NOT excluded.unit_cogs_kzt
               OR fact_sales_owner_cogs_override.cogs_source IS NOT excluded.cogs_source
               OR fact_sales_owner_cogs_override.notes IS NOT excluded.notes
               OR fact_sales_owner_cogs_override.active_flag IS NOT 1
            """,
            (
                row["order_id"],
                row["store_code"],
                row["sku_key"],
                row["sku_id"],
                float(row["unit_cogs_kzt"]),
                SOURCE,
                owner_decision_ref,
                row["notes"],
                now,
                now,
            ),
        )
    ensure_sales_truth_views(conn)


def run(*, db_path: Path, output_root: Path, apply: bool) -> dict[str, Any]:
    db_path = db_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    backup_dir = output_root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    if apply and os.environ.get(REQUIRED_ENV) != "1":
        raise RuntimeError(f"{REQUIRED_ENV}=1 is required with --apply")

    backup_path: str | None = None
    pre_sha = _sha256(db_path)
    if apply:
        backup = backup_dir / f"app_db_before_beli_child_cogs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite"
        _sqlite_backup(db_path, backup)
        backup_path = str(backup)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        target_sales_rows = _validate_target_rows(conn)
        before = _capture_truth(conn)
        conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        try:
            _apply(conn)
            simulated_after = _capture_truth(conn)
            if apply:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            conn.rollback()
            raise
        after = _capture_truth(conn)
    finally:
        conn.close()

    post_sha = _sha256(db_path)
    summary = {
        "ok": True,
        "apply_status": "APPLIED" if apply else "DRY_RUN",
        "db_path": str(db_path),
        "pre_sha256": pre_sha,
        "post_sha256": post_sha,
        "backup_path": backup_path,
        "required_env": REQUIRED_ENV,
        "source": SOURCE,
        "owner_decision_refs": _owner_decision_refs(),
        "approved_rows": APPROVED_ROWS,
        "target_sales_rows": target_sales_rows,
        "before": before,
        "simulated_after": simulated_after,
        "after": after,
    }
    report_path = output_root / "owner_approved_beli_child_cogs_rows_report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["report_path"] = str(report_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    summary = run(db_path=args.db, output_root=args.output_root, apply=args.apply)
    print(
        json.dumps(
            {
                "ok": True,
                "apply_status": summary["apply_status"],
                "report_path": summary["report_path"],
                "backup_path": summary["backup_path"],
                "unresolved_before": summary["before"]["unresolved_window_count"],
                "unresolved_simulated_after": summary["simulated_after"]["unresolved_window_count"],
                "unresolved_after": summary["after"]["unresolved_window_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
