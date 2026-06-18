#!/usr/bin/env python3
"""Resolve one Kaspi chat canary order ID at action time.

The live UI canary packet intentionally stores only redacted order references.
This helper is the narrow bridge for a browser/computer-use operator: it can
print the raw order ID to stdout only when explicitly requested, while every
persisted audit artifact remains redacted.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import (
    is_missing_size_candidate,
    private_hash,
    sha256_file,
    suggest_merchant_status_filter,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"


class ResolverError(RuntimeError):
    def __init__(self, gate: str, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.gate = gate
        self.exit_code = exit_code


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _available_columns(conn: sqlite3.Connection) -> list[str]:
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
    ).fetchone()
    if not table:
        raise ResolverError("RED_RUNTIME_SECRET_NO_FACT_ORDERS_TABLE", "fact_orders_kaspi not found")
    return [row["name"] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()]


def _load_order_row(db_path: Path, db_row_id: int) -> dict[str, Any]:
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        columns = _available_columns(conn)
        if "id" not in columns or "order_id" not in columns:
            raise ResolverError(
                "RED_RUNTIME_SECRET_REQUIRED_COLUMNS_MISSING",
                "fact_orders_kaspi requires id and order_id",
            )
        desired = [
            "id",
            "order_id",
            "store_code",
            "sku_key",
            "sku_id",
            "product_type",
            "my_size",
            "assigned_size",
            "customer_height_cm",
            "customer_weight_kg",
            "internal_status",
            "kaspi_status",
            "planned_shipment_date",
            "created_at",
            "updated_at",
            "status_updated_at",
        ]
        selected = [column for column in desired if column in columns]
        row = conn.execute(
            f"SELECT {', '.join(selected)} FROM fact_orders_kaspi WHERE id = ?",
            (db_row_id,),
        ).fetchone()
    if not row:
        raise ResolverError(
            "RED_RUNTIME_SECRET_DB_ROW_NOT_FOUND",
            f"fact_orders_kaspi row id {db_row_id} not found",
        )
    return dict(row)


def _load_packet_context(args: argparse.Namespace) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if args.packet_manifest:
        context.update(_read_json(args.packet_manifest))
        context["packet_manifest_path"] = str(args.packet_manifest.resolve())
    if args.db_row_id is not None:
        context["selected_db_row_id"] = args.db_row_id
    if "selected_db_row_id" not in context:
        raise ResolverError(
            "RED_RUNTIME_SECRET_NO_DB_ROW_ID",
            "Provide --packet-manifest with selected_db_row_id or --db-row-id",
        )
    return context


def _redacted_row(row: dict[str, Any], order_ref: str) -> dict[str, Any]:
    return {
        "db_row_id": row.get("id"),
        "order_ref": order_ref,
        "store_code": row.get("store_code"),
        "sku_key": row.get("sku_key"),
        "sku_id": row.get("sku_id"),
        "product_type": row.get("product_type"),
        "internal_status": row.get("internal_status"),
        "kaspi_status": row.get("kaspi_status"),
        "planned_shipment_date": row.get("planned_shipment_date"),
        "created_at": row.get("created_at"),
        "has_my_size": bool(str(row.get("my_size") or "").strip()),
        "has_assigned_size": bool(str(row.get("assigned_size") or "").strip()),
        "has_customer_height_cm": bool(str(row.get("customer_height_cm") or "").strip()),
        "has_customer_weight_kg": bool(str(row.get("customer_weight_kg") or "").strip()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve a redacted Kaspi customer-chat canary packet to one raw order ID."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--packet-manifest", type=Path)
    parser.add_argument("--db-row-id", type=int)
    parser.add_argument("--target-date", help="YYYY-MM-DD. Defaults to packet target_date or today.")
    parser.add_argument("--lookback-days", type=int)
    parser.add_argument("--audit-json", type=Path)
    parser.add_argument(
        "--print-raw-order-id",
        action="store_true",
        help="Print only the raw order ID to stdout. Never writes it to audit JSON.",
    )
    return parser


def resolve(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    context = _load_packet_context(args)
    db_path = args.db.resolve()
    db_sha_before = sha256_file(db_path)
    db_row_id = int(context["selected_db_row_id"])
    row = _load_order_row(db_path, db_row_id)
    raw_order_id = str(row.get("order_id") or "").strip()
    if not raw_order_id:
        raise ResolverError("RED_RUNTIME_SECRET_ORDER_ID_EMPTY", "order_id is empty")

    order_ref = private_hash("kaspi_order_id", raw_order_id)
    packet_ref = context.get("selected_order_ref")
    if packet_ref and packet_ref != order_ref:
        raise ResolverError(
            "RED_RUNTIME_SECRET_ORDER_HASH_MISMATCH",
            "Resolved order hash does not match packet selected_order_ref",
        )

    packet_store = str(context.get("selected_store_code") or "").strip().upper()
    row_store = str(row.get("store_code") or "").strip().upper()
    if packet_store and row_store and packet_store != row_store:
        raise ResolverError(
            "RED_RUNTIME_SECRET_STORE_MISMATCH",
            "Resolved store does not match packet selected_store_code",
        )

    target_date = _parse_date(args.target_date or context.get("target_date"))
    lookback_days = int(args.lookback_days if args.lookback_days is not None else context.get("lookback_days", 3))
    candidate_matches, reason_codes = is_missing_size_candidate(
        row,
        target_date=target_date,
        lookback_days=lookback_days,
    )
    if not candidate_matches:
        raise ResolverError(
            "YELLOW_RUNTIME_SECRET_CANDIDATE_NO_LONGER_ACTIVE_MISSING_SIZE",
            "Resolved row is no longer an active missing-size candidate",
            exit_code=3,
        )

    db_sha_after = sha256_file(db_path)
    audit = {
        "gate": "GREEN_RUNTIME_SECRET_RESOLVED_REDACTED_AUDIT",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": db_sha_after,
        "db_unchanged": db_sha_before == db_sha_after,
        "packet_manifest_path": context.get("packet_manifest_path"),
        "db_row_id": db_row_id,
        "order_ref": order_ref,
        "store_code": row.get("store_code"),
        "target_date": target_date.isoformat(),
        "lookback_days": lookback_days,
        "candidate_still_missing_size": True,
        "candidate_reason_codes": list(reason_codes),
        "suggested_merchant_status_filter": suggest_merchant_status_filter(row),
        "raw_order_id_printed_to_stdout": bool(args.print_raw_order_id),
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "kaspi_chat_write_allowed": False,
        "customer_send_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "resolved_row_redacted": _redacted_row(row, order_ref),
    }
    return raw_order_id, audit


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit: dict[str, Any] | None = None
    exit_code = 0
    try:
        raw_order_id, audit = resolve(args)
        if args.print_raw_order_id:
            print(raw_order_id)
        else:
            print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    except ResolverError as exc:
        audit = {
            "gate": exc.gate,
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "error_redacted": str(exc),
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "kaspi_chat_write_allowed": False,
            "customer_send_allowed": False,
        }
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        exit_code = exc.exit_code
    if args.audit_json and audit is not None:
        _write_json(args.audit_json, audit)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
