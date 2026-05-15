#!/usr/bin/env python3
"""Repair D1 cashflow residue from prior verified line-evidence artifacts.

Default: DRY RUN. Apply requires ENABLE_D1_RESIDUE_REPAIR_WRITE=1 and --apply.
Production db/app.db apply additionally requires ENABLE_D1_RESIDUE_REPAIR_PRODUCTION_WRITE=1.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_SOURCE_CSV = (
    PROJECT_ROOT
    / "exports"
    / "validation"
    / "sales_ocean_drop_parity"
    / "2026-02-26"
    / "ocean_drop_reference_snapshot_delivered.csv"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "d1_cashflow_agent7_20260503"
DELIVERED_STAGE_CODES = {"COMPLETED", "DELIVERED", "ISSUED_COMPLETED"}
UNKNOWN_STORE_CODES = {"", "UNKNOWN"}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _is_unknown_store(value: Any) -> bool:
    return _upper(value) in UNKNOWN_STORE_CODES


def _date_part(value: Any) -> str:
    return str(value or "").strip()[:10]


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_source_rows(source_csv: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not source_csv.exists():
        raise FileNotFoundError(f"source CSV not found: {source_csv}")
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    with source_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            order_id = str(row.get("order_id") or "").strip()
            store_code = _upper(row.get("store_code"))
            sku_key = str(row.get("sku_key") or "").strip()
            sku_id = str(row.get("sku_id") or "").strip()
            qty = _as_float(row.get("quantity"))
            gross = _as_float(row.get("gross_rev_kzt"))
            if not order_id or not store_code or not sku_key or not sku_id or qty <= 0 or gross <= 0:
                continue
            if _upper(row.get("status_internal")) not in {"DELIVERED", "COMPLETED"}:
                continue
            if _as_float(row.get("return_flag")) != 0:
                continue
            out.setdefault((order_id, store_code), []).append(dict(row))
    return out


def _has_source_line(conn: sqlite3.Connection, order_id: str, store_code: str) -> bool:
    checks = []
    if _table_exists(conn, "fact_order_entries_kaspi"):
        checks.append(
            (
                """
                SELECT 1
                FROM fact_order_entries_kaspi
                WHERE order_id=? AND UPPER(COALESCE(store_code, 'UNIVERSAL'))=?
                LIMIT 1
                """,
                (order_id, store_code),
            )
        )
    if _table_exists(conn, "sales_fact_v2"):
        checks.append(
            (
                """
                SELECT 1
                FROM sales_fact_v2
                WHERE order_id=? AND UPPER(COALESCE(store_code, 'UNIVERSAL'))=?
                LIMIT 1
                """,
                (order_id, store_code),
            )
        )
    if _table_exists(conn, "fact_orders_kaspi"):
        checks.append(
            (
                """
                SELECT 1
                FROM fact_orders_kaspi
                WHERE order_id=?
                  AND UPPER(COALESCE(store_code, 'UNIVERSAL'))=?
                  AND COALESCE(sku_key, '') <> ''
                  AND COALESCE(sku_id, '') <> ''
                LIMIT 1
                """,
                (order_id, store_code),
            )
        )
    return any(conn.execute(sql, params).fetchone() is not None for sql, params in checks)


def _order_header_amount_evidence(
    conn: sqlite3.Connection, order_id: str, store_code: str
) -> dict[str, Any] | None:
    if not _table_exists(conn, "fact_orders_kaspi"):
        return None
    cols = _columns(conn, "fact_orders_kaspi")
    if not {"order_id", "store_code", "quantity", "unit_price_kzt"}.issubset(cols):
        return None
    select_cols = [
        col
        for col in (
            "order_id",
            "store_code",
            "quantity",
            "unit_price_kzt",
            "delivery_cost_for_seller",
            "delivery_cost",
            "kaspi_status",
            "kaspi_status_detail",
            "source",
        )
        if col in cols
    ]
    order_col = "id" if "id" in cols else "order_id"
    row = conn.execute(
        f"""
        SELECT {', '.join(select_cols)}
        FROM fact_orders_kaspi
        WHERE order_id=?
          AND UPPER(COALESCE(store_code, 'UNIVERSAL'))=?
          AND COALESCE(quantity, 0) > 0
          AND COALESCE(unit_price_kzt, 0) > 0
        ORDER BY {order_col}
        LIMIT 1
        """,
        (order_id, store_code),
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    delivery_cost = item.get("delivery_cost_for_seller")
    if delivery_cost is None:
        delivery_cost = item.get("delivery_cost")
    return {
        "quantity": _as_float(item.get("quantity")),
        "unit_price_kzt": _as_float(item.get("unit_price_kzt")),
        "delivery_cost_kzt": _as_float(delivery_cost),
        "kaspi_status": item.get("kaspi_status"),
        "kaspi_status_detail": item.get("kaspi_status_detail"),
        "source": item.get("source"),
    }


def _delivered_missing_line_targets(conn: sqlite3.Connection, *, as_of: str) -> list[dict[str, Any]]:
    if not _table_exists(conn, "order_status_event"):
        return []
    delivered_sql = ",".join("?" * len(DELIVERED_STAGE_CODES))
    rows = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT UPPER(COALESCE(store_code, 'UNIVERSAL')) AS store_code,
                   order_id,
                   MIN(event_ts) AS delivered_ts
            FROM order_status_event
            WHERE UPPER(COALESCE(stage_code, '')) IN ({delivered_sql})
              AND date(event_ts) <= date(?)
            GROUP BY UPPER(COALESCE(store_code, 'UNIVERSAL')), order_id
            """,
            (*sorted(DELIVERED_STAGE_CODES), as_of),
        ).fetchall()
    ]
    non_unknown_orders = {
        str(row.get("order_id") or "").strip()
        for row in rows
        if str(row.get("order_id") or "").strip() and not _is_unknown_store(row.get("store_code"))
    }
    targets = []
    for row in rows:
        order_id = str(row.get("order_id") or "").strip()
        store_code = _upper(row.get("store_code"))
        if not order_id or not store_code:
            continue
        if order_id in non_unknown_orders and _is_unknown_store(store_code):
            continue
        if _has_source_line(conn, order_id, store_code):
            continue
        targets.append(
            {
                "order_id": order_id,
                "store_code": store_code,
                "delivered_date": _date_part(row.get("delivered_ts")),
            }
        )
    return targets


def _candidate_entry(row: dict[str, Any], *, source_csv: Path) -> dict[str, Any]:
    line_id = str(row.get("line_id") or "").strip()
    order_id = str(row.get("order_id") or "").strip()
    store_code = _upper(row.get("store_code"))
    qty = _as_float(row.get("quantity"))
    gross = _as_float(row.get("gross_rev_kzt"))
    entry_id = f"D1RES-OCEAN-{line_id or _sha256_text(json.dumps(row, sort_keys=True))[:24]}"
    unit_price = round(gross / qty, 4) if qty else gross
    raw_json = json.dumps(
        {
            "recovery_source": "OCEAN_DROP_REFERENCE_SNAPSHOT_DELIVERED",
            "source_csv": str(source_csv),
            "line_id": line_id,
            "date_source": row.get("date_source"),
            "sku_source": row.get("sku_source"),
            "size_source": row.get("size_source"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "entry_id": entry_id,
        "order_id": order_id,
        "store_code": store_code,
        "offer_id": str(row.get("article") or "").strip(),
        "quantity": qty,
        "unit_price_kzt": unit_price,
        "total_price_kzt": gross,
        "raw_json": raw_json,
        "delivery_cost_kzt": _as_float(row.get("net_delivery_fee_kzt")),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def repair_d1_residue_from_evidence(
    *,
    db_path: Path,
    source_csv: Path = DEFAULT_SOURCE_CSV,
    as_of: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    apply: bool = False,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    source_csv = source_csv.resolve()
    output_root = output_root.resolve()
    source_rows = _load_source_rows(source_csv)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_order_entries_kaspi"):
            raise RuntimeError("fact_order_entries_kaspi missing")
        targets = _delivered_missing_line_targets(conn, as_of=as_of)
        repair_rows: list[dict[str, Any]] = []
        deterministic_exceptions: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for target in targets:
            matches = source_rows.get((target["order_id"], target["store_code"]), [])
            if matches:
                for row in matches:
                    repair_rows.append(_candidate_entry(row, source_csv=source_csv))
            elif header := _order_header_amount_evidence(conn, target["order_id"], target["store_code"]):
                deterministic_exceptions.append(
                    {
                        **target,
                        "classification": "deterministic_exception",
                        "reason": "ORDER_HEADER_AMOUNT_WITHOUT_LINE_IDENTITY",
                        "evidence": header,
                    }
                )
            else:
                blocked.append(
                    {
                        **target,
                        "classification": "still_blocked_source_missing",
                        "reason": "NO_LINE_EVIDENCE_IN_OCEAN_DROP_REFERENCE_SNAPSHOT",
                    }
                )

        existing_ids = {
            row[0]
            for row in conn.execute(
                "SELECT entry_id FROM fact_order_entries_kaspi WHERE entry_id IN ({})".format(
                    ",".join("?" * len(repair_rows)) or "NULL"
                ),
                [row["entry_id"] for row in repair_rows],
            ).fetchall()
        }
        insert_rows = [row for row in repair_rows if row["entry_id"] not in existing_ids]

        inserted = 0
        if apply and insert_rows:
            if os.environ.get("ENABLE_D1_RESIDUE_REPAIR_WRITE") != "1":
                raise RuntimeError("ENABLE_D1_RESIDUE_REPAIR_WRITE=1 is required to apply D1 residue repair.")
            if db_path == DEFAULT_DB.resolve() and os.environ.get("ENABLE_D1_RESIDUE_REPAIR_PRODUCTION_WRITE") != "1":
                raise RuntimeError(
                    "Production db/app.db D1 residue repair requires "
                    "ENABLE_D1_RESIDUE_REPAIR_PRODUCTION_WRITE=1."
                )
            cols = _columns(conn, "fact_order_entries_kaspi")
            insert_cols = [
                col
                for col in (
                    "entry_id",
                    "order_id",
                    "store_code",
                    "offer_id",
                    "quantity",
                    "unit_price_kzt",
                    "total_price_kzt",
                    "raw_json",
                    "delivery_cost_kzt",
                )
                if col in cols
            ]
            placeholders = ",".join("?" * len(insert_cols))
            for row in insert_rows:
                conn.execute(
                    f"""
                    INSERT OR IGNORE INTO fact_order_entries_kaspi (
                        {', '.join(insert_cols)}
                    ) VALUES ({placeholders})
                    """,
                    [row.get(col) for col in insert_cols],
                )
                inserted += int(conn.total_changes > inserted)
            conn.commit()

    summary = {
        "status": "PASS" if not blocked else "YELLOW",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "source_csv": str(source_csv),
        "as_of": as_of,
        "apply": bool(apply),
        "target_missing_line_orders": len(targets),
        "source_backed_repair_count": len(repair_rows),
        "deterministic_exception_count": len(deterministic_exceptions),
        "would_insert_entry_rows": len(insert_rows),
        "inserted_entry_rows": inserted if apply else 0,
        "already_present_entry_rows": len(repair_rows) - len(insert_rows),
        "still_blocked_source_missing_count": len(blocked),
        "deterministic_exception_rows": deterministic_exceptions,
        "blocked_rows": blocked,
    }
    _write_json(output_root / "d1_residue_repair_summary.json", summary)
    _write_jsonl(output_root / "d1_residue_repair_entries.jsonl", repair_rows)
    _write_jsonl(output_root / "d1_residue_deterministic_exceptions.jsonl", deterministic_exceptions)
    _write_jsonl(output_root / "d1_residue_still_blocked.jsonl", blocked)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair D1 cashflow residue from source evidence")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--source-csv", type=Path, default=DEFAULT_SOURCE_CSV)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    summary = repair_d1_residue_from_evidence(
        db_path=args.db,
        source_csv=args.source_csv,
        as_of=args.as_of,
        output_root=args.output_root,
        apply=args.apply,
    )
    print(f"status={summary['status']}")
    print(f"target_missing_line_orders={summary['target_missing_line_orders']}")
    print(f"source_backed_repair_count={summary['source_backed_repair_count']}")
    print(f"deterministic_exception_count={summary['deterministic_exception_count']}")
    print(f"would_insert_entry_rows={summary['would_insert_entry_rows']}")
    print(f"inserted_entry_rows={summary['inserted_entry_rows']}")
    print(f"still_blocked_source_missing_count={summary['still_blocked_source_missing_count']}")
    print(f"summary_json={args.output_root / 'd1_residue_repair_summary.json'}")
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
