#!/usr/bin/env python3
"""Resolve a raw Kaspi order ID for customer-size UI work at action time only.

The raw order ID may be printed to stdout for immediate clipboard/browser use,
but it is never written to the redacted audit file.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import private_hash


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_row(db_path: Path, *, db_row_id: int | None, order_ref: str | None) -> dict[str, Any] | None:
    uri = f"file:{db_path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return None
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()}
        desired = [
            "id",
            "order_id",
            "store_code",
            "sku_key",
            "sku_id",
            "internal_status",
            "kaspi_status",
            "planned_shipment_date",
            "created_at",
        ]
        selected = [column for column in desired if column in columns]
        if "order_id" not in selected:
            return None
        if db_row_id is not None and "id" in selected:
            row = conn.execute(
                f"SELECT {', '.join(selected)} FROM fact_orders_kaspi WHERE id = ?",
                (db_row_id,),
            ).fetchone()
            return dict(row) if row else None
        if order_ref:
            rows = conn.execute(
                f"SELECT {', '.join(selected)} FROM fact_orders_kaspi ORDER BY id DESC"
            ).fetchall()
            for row in rows:
                raw_order_id = str(row["order_id"] or "").strip()
                if raw_order_id and private_hash("kaspi_order_id", raw_order_id) == order_ref:
                    return dict(row)
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--db-row-id", type=int)
    parser.add_argument("--order-ref")
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument(
        "--print-raw-order-id",
        action="store_true",
        help="Print raw order ID to stdout only for immediate runtime use.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = args.db.resolve()
    order_ref = str(args.order_ref or "").strip() or None
    row = _load_row(db_path, db_row_id=args.db_row_id, order_ref=order_ref)
    audit: dict[str, Any] = {
        "gate": "RED_RUNTIME_SECRET_ORDER_NOT_FOUND",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "db_row_id": args.db_row_id,
        "order_ref": order_ref or "",
        "raw_order_id_printed_to_stdout": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
    }
    if not row:
        audit["blockers"] = ["order_not_found"]
        _write_json(args.audit_json, audit)
        return 2

    raw_order_id = str(row.get("order_id") or "").strip()
    computed_ref = private_hash("kaspi_order_id", raw_order_id)
    audit.update(
        {
            "resolved_order_ref": computed_ref,
            "resolved_db_row_id": row.get("id"),
            "store_code": row.get("store_code"),
            "sku_key": row.get("sku_key"),
            "sku_id": row.get("sku_id"),
            "internal_status": row.get("internal_status"),
            "kaspi_status": row.get("kaspi_status"),
        }
    )
    if order_ref and computed_ref != order_ref:
        audit["gate"] = "RED_RUNTIME_SECRET_ORDER_HASH_MISMATCH"
        audit["blockers"] = ["order_ref_mismatch"]
        _write_json(args.audit_json, audit)
        return 2

    audit["gate"] = "GREEN_RUNTIME_SECRET_RESOLVED_REDACTED_AUDIT"
    audit["raw_order_id_printed_to_stdout"] = bool(args.print_raw_order_id)
    _write_json(args.audit_json, audit)
    if args.print_raw_order_id:
        print(raw_order_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
