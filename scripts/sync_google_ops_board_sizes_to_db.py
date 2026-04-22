#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.google_ops_board import (
    DEFAULT_CONTRACT_PATH,
    GoogleOpsBoardClient,
    dump_json,
    extract_rows_from_matrix,
    load_ops_board_contract,
    resolve_service_account_json,
    resolve_spreadsheet_id,
)
from core.paths import data_path
from core.utils.sku_normalize import normalize_size


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_BACKUP_ROOT = data_path("runtime", "backups")
DEFAULT_OUTPUT_ROOT = data_path("exports", "google_ops_board")


def _require_apply_gate(apply: bool, env_name: str) -> None:
    if apply and str(__import__("os").environ.get(env_name) or "").strip() != "1":
        raise RuntimeError(f"{env_name}=1 is required with --apply")


def _resolve_target_date(value: str) -> date:
    text = str(value or "").strip().lower()
    today = datetime.now(ALMATY_TZ).date()
    if text in ("", "today"):
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    return datetime.strptime(text, "%Y-%m-%d").date()


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _fallback_product_type(db_row: dict[str, Any]) -> str:
    product_type = _clean(db_row.get("product_type"))
    if product_type:
        return product_type
    sku_key = _clean(db_row.get("sku_key"))
    if "_" in sku_key:
        return sku_key.split("_", 1)[0]
    return "CL"


def plan_size_writeback(
    sheet_rows: list[dict[str, Any]],
    db_rows: dict[str, dict[str, Any]],
    *,
    key_column: str,
    source_column: str,
) -> dict[str, list[dict[str, Any]]]:
    updates: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    for row in sheet_rows:
        target_key = _clean(row.get(key_column))
        raw_size = _clean(row.get(source_column))
        if not target_key or not raw_size:
            continue
        db_row = db_rows.get(target_key)
        if not db_row:
            continue
        product_type = _fallback_product_type(db_row)
        normalized_size = normalize_size(raw_size, product_type=product_type)
        if not normalized_size:
            invalid_rows.append(
                {
                    "target_key": target_key,
                    "raw_input_size": raw_size,
                    "product_type": product_type,
                    "store_code": _clean(db_row.get("store_code")),
                }
            )
            continue
        old_size = _clean(db_row.get("assigned_size"))
        if normalized_size == old_size:
            continue
        updates.append(
            {
                "target_key": target_key,
                "raw_input_size": raw_size,
                "new_assigned_size": normalized_size,
                "old_assigned_size": old_size,
                "store_code": _clean(db_row.get("store_code")),
                "product_type": product_type,
            }
        )
    return {
        "updates": updates,
        "invalid_rows": invalid_rows,
    }


def build_size_writeback_plan(
    sheet_rows: list[dict[str, Any]],
    db_rows: dict[str, dict[str, Any]],
    *,
    key_column: str,
    source_column: str,
) -> list[dict[str, Any]]:
    return plan_size_writeback(
        sheet_rows=sheet_rows,
        db_rows=db_rows,
        key_column=key_column,
        source_column=source_column,
    )["updates"]


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_google_ops_board_size_sync_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(backup_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return backup_path


def _load_db_rows(db_path: Path, start_date: date, target_date: date) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT fk.id, fk.store_code, fk.assigned_size, fk.sku_key, COALESCE(ds.product_type, '') AS product_type
            FROM fact_orders_kaspi fk
            LEFT JOIN dim_sku ds ON ds.sku_key = fk.sku_key
            WHERE fk.planned_shipment_date BETWEEN ? AND ?
            """,
            (start_date.isoformat(), target_date.isoformat()),
        ).fetchall()
        return {
            _clean(row["id"]): {
                "assigned_size": row["assigned_size"],
                "store_code": row["store_code"],
                "sku_key": row["sku_key"],
                "product_type": row["product_type"],
            }
            for row in rows
        }
    finally:
        conn.close()


def _apply_updates(db_path: Path, updates: list[dict[str, Any]], source_value: str) -> int:
    if not updates:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        for update in updates:
            conn.execute(
                """
                UPDATE fact_orders_kaspi
                SET assigned_size = ?, size_source = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (update["new_assigned_size"], source_value, update["target_key"]),
            )
        conn.commit()
        return len(updates)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write back Google Ops Board MY_SIZE into fact_orders_kaspi.assigned_size.")
    parser.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: db/app.db)")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH, help="Contract YAML path")
    parser.add_argument("--service-account-json", type=Path, default=None, help="Path to service-account JSON")
    parser.add_argument("--spreadsheet-id", type=str, default=None, help="Override spreadsheet ID")
    parser.add_argument("--target-date", type=str, default="today", help="Target date (default: today)")
    parser.add_argument("--lookback-days", type=int, default=5, help="Operational lookback window (default: 5)")
    parser.add_argument("--apply", action="store_true", help="Apply DB updates (default: dry-run)")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT, help="Backup directory for --apply")
    parser.add_argument("--output-json", type=Path, default=None, help="Optional JSON report path")
    args = parser.parse_args(argv)

    contract = load_ops_board_contract(args.contract)
    writeback_spec = contract.writeback["size_assignments"]
    _require_apply_gate(args.apply, contract.db_write_env_gate)

    db_path = Path(args.db).expanduser() if args.db else data_path("db", "app.db")
    target = _resolve_target_date(args.target_date)
    start = target - timedelta(days=max(args.lookback_days - 1, 0))

    service_account_json = resolve_service_account_json(args.service_account_json, contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(args.spreadsheet_id, contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, service_account_json)
    matrix = client.get_tab_values(writeback_spec["tab"])
    headers = contract.tabs[writeback_spec["tab"]].headers
    sheet_rows = extract_rows_from_matrix(headers, matrix)
    db_rows = _load_db_rows(db_path, start, target)
    plan = plan_size_writeback(
        sheet_rows=sheet_rows,
        db_rows=db_rows,
        key_column=writeback_spec["key_column"],
        source_column=writeback_spec["source_column"],
    )
    updates = plan["updates"]
    invalid_rows = plan["invalid_rows"]

    report = {
        "db_path": str(db_path),
        "spreadsheet_id": spreadsheet_id,
        "tab": writeback_spec["tab"],
        "target_date": target.isoformat(),
        "lookback_days": args.lookback_days,
        "updates_planned": updates,
        "invalid_rows": invalid_rows,
        "invalid_rows_count": len(invalid_rows),
        "updates_count": len(updates),
        "apply": args.apply,
    }

    if args.apply and invalid_rows:
        report["db_backup_path"] = None
        report["updates_applied"] = 0
        report["blocked_reason"] = (
            f"Refusing DB writeback: {len(invalid_rows)} invalid MY_SIZE value(s) need operator cleanup first."
        )
        if args.output_json is not None:
            output_path = args.output_json
        else:
            stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
            output_path = DEFAULT_OUTPUT_ROOT / target.isoformat() / f"sync_google_ops_board_sizes_to_db_{stamp}.json"
        dump_json(output_path, report)
        raise RuntimeError(report["blocked_reason"])

    if args.apply and not updates:
        report["db_backup_path"] = None
        report["updates_applied"] = 0
        report["skipped_db_backup"] = True
        report["noop"] = True
    elif args.apply:
        backup_path = _backup_db(db_path, Path(args.backup_root).expanduser())
        report["db_backup_path"] = str(backup_path)
        report["updates_applied"] = _apply_updates(
            db_path=db_path,
            updates=updates,
            source_value=writeback_spec["target_source_value"],
        )
        report["skipped_db_backup"] = False
        report["noop"] = False
    else:
        report["db_backup_path"] = None
        report["updates_applied"] = 0
        report["skipped_db_backup"] = False
        report["noop"] = False

    if args.output_json is not None:
        output_path = args.output_json
    else:
        stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
        output_path = DEFAULT_OUTPUT_ROOT / target.isoformat() / f"sync_google_ops_board_sizes_to_db_{stamp}.json"
    dump_json(output_path, report)
    print(f"Google Ops Board size writeback report: {output_path}")
    print(f"Planned updates: {len(updates)}")
    if args.apply:
        print(f"DB backup: {report['db_backup_path']}")
        print(f"Applied updates: {report['updates_applied']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
