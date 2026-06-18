#!/usr/bin/env python3
"""Build a no-write Google Ops Board MY_SIZE patch packet from reply classifications."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from core.ops.customer_size_request import (
    export_customer_size_ledger_snapshot,
    is_missing_size_candidate,
    sha256_file,
)
from core.utils.sku_normalize import normalize_size


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
BOARD_TAB = "SalesRaw_Today"
BOARD_KEY_COLUMN = "_db_row_id"
BOARD_SIZE_COLUMN = "MY_SIZE"


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _default_output_dir(target_date: date) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_size_google_board_patch_packet_{target_date.isoformat()}_{stamp}"
    )


def _select_order_rows(db_path: Path, db_row_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not db_row_ids:
        return {}
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()}
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
        if "id" not in selected:
            return {}
        placeholders = ",".join("?" for _ in db_row_ids)
        rows = conn.execute(
            f"SELECT {', '.join(selected)} FROM fact_orders_kaspi WHERE id IN ({placeholders})",
            db_row_ids,
        ).fetchall()
    return {int(row["id"]): dict(row) for row in rows}


def _product_type(row: Mapping[str, Any], ledger_row: Mapping[str, Any]) -> str:
    value = str(row.get("product_type") or "").strip()
    if value:
        return value
    sku_key = str(row.get("sku_key") or ledger_row.get("sku_key") or "").strip()
    if "_" in sku_key:
        return sku_key.split("_", 1)[0]
    return "CL"


def _has_text(value: Any) -> bool:
    return str(value or "").strip() != ""


def build_patch_rows(
    *,
    ledger_rows: list[dict[str, Any]],
    db_rows: dict[int, dict[str, Any]],
    target_date: date,
    lookback_days: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    patch_rows: list[dict[str, Any]] = []
    already_applied_rows: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    for ledger_row in ledger_rows:
        status = str(ledger_row.get("status") or "").strip().upper()
        planned_size_raw = str(ledger_row.get("planned_size") or "").strip()
        if status != "CLASSIFICATION_READY" or not planned_size_raw:
            continue
        db_row_id = ledger_row.get("db_row_id")
        if db_row_id is None:
            blockers.append(
                {
                    "order_ref": ledger_row.get("order_ref"),
                    "blocker": "missing_db_row_id",
                    "raw_order_id_exported": False,
                }
            )
            continue
        db_row = db_rows.get(int(db_row_id))
        if not db_row:
            blockers.append(
                {
                    "db_row_id": db_row_id,
                    "order_ref": ledger_row.get("order_ref"),
                    "blocker": "db_row_not_found",
                    "raw_order_id_exported": False,
                }
            )
            continue
        product_type = _product_type(db_row, ledger_row)
        normalized_size = normalize_size(planned_size_raw, product_type=product_type)
        if not normalized_size:
            blockers.append(
                {
                    "db_row_id": db_row_id,
                    "order_ref": ledger_row.get("order_ref"),
                    "blocker": "planned_size_invalid",
                    "planned_size_hash": ledger_row.get("reply_hash"),
                    "product_type": product_type,
                    "raw_order_id_exported": False,
                }
            )
            continue
        current_size = str(db_row.get("assigned_size") or db_row.get("my_size") or "").strip()
        if current_size:
            row = {
                "db_row_id": db_row_id,
                "order_ref": ledger_row.get("order_ref"),
                "store_code": ledger_row.get("store_code"),
                "current_size_present": True,
                "planned_my_size": normalized_size,
                "raw_order_id_exported": False,
            }
            if normalize_size(current_size, product_type=product_type) == normalized_size:
                already_applied_rows.append(row | {"status": "already_applied_same_size"})
            else:
                blockers.append(row | {"blocker": "db_row_already_has_different_size"})
            continue
        candidate_matches, reason_codes = is_missing_size_candidate(
            db_row,
            target_date=target_date,
            lookback_days=lookback_days,
        )
        if not candidate_matches:
            blockers.append(
                {
                    "db_row_id": db_row_id,
                    "order_ref": ledger_row.get("order_ref"),
                    "store_code": ledger_row.get("store_code"),
                    "blocker": "db_row_no_longer_active_missing_size",
                    "reason_codes": "|".join(reason_codes),
                    "raw_order_id_exported": False,
                }
            )
            continue
        patch_rows.append(
            {
                "target_tab": BOARD_TAB,
                "key_column": BOARD_KEY_COLUMN,
                "key_value": db_row_id,
                "source_column": BOARD_SIZE_COLUMN,
                "planned_cell_value": normalized_size,
                "db_target_table": "fact_orders_kaspi",
                "db_target_key_column": "id",
                "db_target_key_value": db_row_id,
                "db_target_column": "assigned_size",
                "db_target_source_column": "size_source",
                "db_target_source_value_after_board_writeback": "GOOGLE_OPS_BOARD",
                "order_ref": ledger_row.get("order_ref"),
                "store_code": ledger_row.get("store_code"),
                "sku_key": ledger_row.get("sku_key"),
                "sku_id": ledger_row.get("sku_id"),
                "size_source": ledger_row.get("size_source"),
                "size_confidence": ledger_row.get("size_confidence"),
                "height_cm": ledger_row.get("height_cm"),
                "weight_kg": ledger_row.get("weight_kg"),
                "explicit_size": ledger_row.get("explicit_size"),
                "write_allowed": False,
                "google_board_write_allowed": False,
                "db_write_allowed": False,
                "raw_order_id_exported": False,
                "raw_reply_text_exported": False,
            }
        )
    return patch_rows, already_applied_rows, blockers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--target-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_date = _parse_date(args.target_date)
    output_dir = args.output_dir or _default_output_dir(target_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = args.db.resolve()
    ledger_path = args.ledger_db.resolve()

    db_sha_before = sha256_file(db_path) if db_path.exists() else None
    ledger_rows = export_customer_size_ledger_snapshot(ledger_path)
    classification_rows = [
        row
        for row in ledger_rows
        if str(row.get("status") or "").strip().upper() == "CLASSIFICATION_READY"
        and _has_text(row.get("planned_size"))
    ]
    db_row_ids = sorted(
        {
            int(row["db_row_id"])
            for row in classification_rows
            if row.get("db_row_id") is not None
        }
    )
    db_rows = _select_order_rows(db_path, db_row_ids)
    patch_rows, already_applied_rows, blockers = build_patch_rows(
        ledger_rows=ledger_rows,
        db_rows=db_rows,
        target_date=target_date,
        lookback_days=args.lookback_days,
    )
    db_sha_after = sha256_file(db_path) if db_path.exists() else None

    if blockers:
        gate = "YELLOW_GOOGLE_BOARD_SIZE_PATCH_PACKET_HAS_BLOCKERS_NO_WRITE"
    elif patch_rows:
        gate = "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE"
    else:
        gate = "YELLOW_GOOGLE_BOARD_SIZE_PATCH_PACKET_NO_READY_ROWS_NO_WRITE"

    _write_json(output_dir / "google_board_my_size_patch_rows_no_write.json", patch_rows)
    _write_csv(output_dir / "google_board_my_size_patch_rows_no_write.csv", patch_rows)
    _write_json(output_dir / "already_applied_rows_redacted.json", already_applied_rows)
    _write_json(output_dir / "blockers_redacted.json", blockers)

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": db_sha_after,
        "db_unchanged": db_sha_before == db_sha_after,
        "ledger_db_path": str(ledger_path),
        "target_date": target_date.isoformat(),
        "lookback_days": args.lookback_days,
        "ledger_rows": len(ledger_rows),
        "classification_ready_rows": len(classification_rows),
        "patch_rows_count": len(patch_rows),
        "already_applied_rows_count": len(already_applied_rows),
        "blockers_count": len(blockers),
        "target_tab": BOARD_TAB,
        "key_column": BOARD_KEY_COLUMN,
        "source_column": BOARD_SIZE_COLUMN,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "raw_order_ids_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    closeout = "\n".join(
        [
            "# Kaspi Customer Size Google Board Patch Packet",
            "",
            f"Gate: {gate}",
            "",
            f"- Output folder: {output_dir}",
            f"- Ledger rows: {len(ledger_rows)}",
            f"- Classification-ready rows: {len(classification_rows)}",
            f"- Patch rows: {len(patch_rows)}",
            f"- Already applied rows: {len(already_applied_rows)}",
            f"- Blockers: {len(blockers)}",
            f"- Target board tab: {BOARD_TAB}",
            f"- Target key column: {BOARD_KEY_COLUMN}",
            f"- Target size column: {BOARD_SIZE_COLUMN}",
            f"- DB unchanged: {db_sha_before == db_sha_after}",
            "",
            "No customer messages, Kaspi UI/API writes, Google Board writes, DB writes,",
            "Telegram/WhatsApp sends, workbook writes, scheduler changes, raw order ID",
            "exports, or raw reply text exports happened.",
            "",
        ]
    )
    (output_dir / "closeout.md").write_text(closeout, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
