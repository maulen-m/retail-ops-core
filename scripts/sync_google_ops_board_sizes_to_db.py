#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
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
from core.stores.roster import load_sync_enabled_kaspi_store_codes
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


def _normalize_store_code(value: Any) -> str:
    text = _clean(value).upper().replace(" ", "")
    return {
        "STORE-B": "STOREB",
        "STORE_B": "STOREB",
        "ACMEWEAR": "ACMEWEAR",
        "UNIVERSAL": "UNIVERSAL",
        "MELVIS": "MELVIS",
        "11KZ": "11KZ",
    }.get(text, text)


def _load_allowed_order_scope(
    path: Path,
    *,
    target_date: date,
) -> tuple[set[tuple[str, str]], list[dict[str, str]]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or int(payload.get("schema_version") or 0) != 2:
        raise ValueError("size writeback scope must be a schema_version=2 JSON object")
    if _clean(payload.get("target_date")) != target_date.isoformat():
        raise ValueError("size writeback scope target_date mismatch")
    request_identity = dict(payload.get("request_identity") or {})
    if (
        _clean(request_identity.get("target_date")) != target_date.isoformat()
        or not _clean(request_identity.get("ready_set_at"))
    ):
        raise ValueError("size writeback scope request identity is incomplete")
    raw_orders = payload.get("orders")
    if not isinstance(raw_orders, list):
        raise ValueError("size writeback scope orders must be a list")
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    enabled_stores = {
        _normalize_store_code(value) for value in load_sync_enabled_kaspi_store_codes()
    }
    for raw in raw_orders:
        if not isinstance(raw, dict):
            raise ValueError("size writeback scope order entry must be an object")
        pair = (
            _normalize_store_code(raw.get("store_code")),
            _clean(raw.get("order_id")),
        )
        if not all(pair) or pair in seen:
            raise ValueError("size writeback scope contains missing or duplicate identity")
        if pair[0] not in enabled_stores:
            raise ValueError(f"size writeback scope includes a sync-disabled store: {pair[0]}")
        seen.add(pair)
        normalized.append({"store_code": pair[0], "order_id": pair[1]})
    normalized.sort(key=lambda item: (item["store_code"], item["order_id"]))
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError("size writeback scope rows must be a list")
    pinned_rows: list[dict[str, str]] = []
    seen_db_row_ids: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise ValueError("size writeback scope row entry must be an object")
        item = {
            "store_code": _normalize_store_code(raw.get("store_code")),
            "order_id": _clean(raw.get("order_id")),
            "db_row_id": _clean(raw.get("db_row_id")),
            "line_key": _clean(raw.get("line_key")),
            "my_size": _clean(raw.get("my_size")),
        }
        if not all(item.values()):
            raise ValueError("size writeback scope contains an incomplete pinned row")
        if (item["store_code"], item["order_id"]) not in seen:
            raise ValueError("size writeback scope row is outside the allowed order set")
        if item["db_row_id"] in seen_db_row_ids:
            raise ValueError("size writeback scope contains a duplicate DB row identity")
        seen_db_row_ids.add(item["db_row_id"])
        pinned_rows.append(item)
    pinned_rows.sort(
        key=lambda item: (
            item["store_code"],
            item["order_id"],
            item["db_row_id"],
            item["line_key"],
        )
    )
    observed_hash = hashlib.sha256(
        json.dumps(pinned_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if observed_hash != _clean(payload.get("scope_sha256")):
        raise ValueError("size writeback scope hash mismatch")
    return seen, pinned_rows


def _db_line_key(db_row: dict[str, Any]) -> str:
    quantity = int(db_row.get("quantity") or 0)
    sku_token = _clean(db_row.get("sku_key")) or _clean(db_row.get("sku_id"))
    return "|".join(
        (
            _clean(db_row.get("order_id")),
            _clean(db_row.get("planned_shipment_date")),
            sku_token,
            _clean(db_row.get("kaspi_offer_name")),
            str(quantity),
        )
    )


def plan_size_writeback(
    sheet_rows: list[dict[str, Any]],
    db_rows: dict[str, dict[str, Any]],
    *,
    key_column: str,
    source_column: str,
    require_visible_identity: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    updates: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    seen_targets: dict[str, str] = {}
    for row in sheet_rows:
        target_key = _clean(row.get(key_column))
        raw_size = _clean(row.get(source_column))
        if not raw_size:
            continue
        if not target_key:
            invalid_rows.append(
                {
                    "target_key": "",
                    "raw_input_size": raw_size,
                    "reason": "missing_db_row_id",
                }
            )
            continue
        if target_key in seen_targets:
            invalid_rows.append(
                {
                    "target_key": target_key,
                    "raw_input_size": raw_size,
                    "first_input_size": seen_targets[target_key],
                    "reason": "duplicate_db_row_id",
                }
            )
            continue
        seen_targets[target_key] = raw_size
        db_row = db_rows.get(target_key)
        if not db_row:
            invalid_rows.append(
                {
                    "target_key": target_key,
                    "raw_input_size": raw_size,
                    "reason": "db_row_not_found",
                }
            )
            continue
        if require_visible_identity:
            visible_order_id = _clean(row.get("OrderID"))
            visible_store = _normalize_store_code(row.get("STORE_NAME"))
            visible_line_key = _clean(row.get("_line_key"))
            identity_issues: list[str] = []
            if not visible_order_id or visible_order_id != _clean(db_row.get("order_id")):
                identity_issues.append("order_id_mismatch")
            if not visible_store or visible_store != _normalize_store_code(db_row.get("store_code")):
                identity_issues.append("store_code_mismatch")
            if db_row.get("line_identity_available") and (
                not visible_line_key or visible_line_key != _db_line_key(db_row)
            ):
                identity_issues.append("line_key_mismatch")
            if identity_issues:
                invalid_rows.append(
                    {
                        "target_key": target_key,
                        "raw_input_size": raw_size,
                        "reason": "visible_identity_mismatch",
                        "identity_issues": identity_issues,
                    }
                )
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


def _load_db_rows(db_path: Path, row_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Load only the exact DB rows currently exposed on SalesRaw_Today.

    Row identity, not a date window, is the writeback authority.  This preserves
    no-expiry carry-forward sizes without scanning or mutating unrelated history.
    """
    normalized_ids = sorted({_clean(value) for value in row_ids if _clean(value)})
    if not normalized_ids:
        return {}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)").fetchall()
        }
        def _fk_expr(column: str, default_sql: str = "''") -> str:
            return f"fk.{column}" if column in columns else f"{default_sql} AS {column}"

        rows: list[sqlite3.Row] = []
        for offset in range(0, len(normalized_ids), 900):
            chunk = normalized_ids[offset : offset + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                conn.execute(
                    f"""
                    SELECT fk.id, fk.order_id, fk.store_code, fk.assigned_size,
                           fk.sku_key, {_fk_expr('sku_id')},
                           {_fk_expr('kaspi_offer_name')},
                           {_fk_expr('quantity', '1')},
                           fk.planned_shipment_date,
                           COALESCE(ds.product_type, '') AS product_type
                    FROM fact_orders_kaspi fk
                    LEFT JOIN dim_sku ds ON ds.sku_key = fk.sku_key
                    WHERE CAST(fk.id AS TEXT) IN ({placeholders})
                    """,
                    chunk,
                ).fetchall()
            )
        return {
            _clean(row["id"]): {
                "assigned_size": row["assigned_size"],
                "order_id": row["order_id"],
                "store_code": row["store_code"],
                "sku_key": row["sku_key"],
                "sku_id": row["sku_id"],
                "kaspi_offer_name": row["kaspi_offer_name"],
                "quantity": row["quantity"],
                "planned_shipment_date": row["planned_shipment_date"],
                "line_identity_available": all(
                    column in columns
                    for column in (
                        "order_id",
                        "planned_shipment_date",
                        "sku_key",
                        "sku_id",
                        "kaspi_offer_name",
                        "quantity",
                    )
                ),
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
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=5,
        help="Deprecated compatibility value; exact SalesRaw_Today row IDs drive writeback",
    )
    parser.add_argument("--apply", action="store_true", help="Apply DB updates (default: dry-run)")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT, help="Backup directory for --apply")
    parser.add_argument("--output-json", type=Path, default=None, help="Optional JSON report path")
    parser.add_argument(
        "--allowed-order-scope-file",
        type=Path,
        default=None,
        help="Source-backed exact store/order scope emitted by the closeout orchestrator; required for --apply",
    )
    args = parser.parse_args(argv)

    contract = load_ops_board_contract(args.contract)
    writeback_spec = contract.writeback["size_assignments"]
    _require_apply_gate(args.apply, contract.db_write_env_gate)

    db_path = Path(args.db).expanduser() if args.db else data_path("db", "app.db")
    target = _resolve_target_date(args.target_date)

    service_account_json = resolve_service_account_json(args.service_account_json, contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(args.spreadsheet_id, contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, service_account_json)
    matrix = client.get_tab_values(writeback_spec["tab"])
    headers = contract.tabs[writeback_spec["tab"]].headers
    sheet_rows = extract_rows_from_matrix(headers, matrix)
    if args.apply and args.allowed_order_scope_file is None:
        raise RuntimeError("--apply requires --allowed-order-scope-file")
    enabled_stores = {
        _normalize_store_code(value) for value in load_sync_enabled_kaspi_store_codes()
    }
    if args.allowed_order_scope_file is not None:
        allowed_order_scope, pinned_scope_rows = _load_allowed_order_scope(
            args.allowed_order_scope_file,
            target_date=target,
        )
        scoped_sheet_rows = [
            row
            for row in sheet_rows
            if (
                _normalize_store_code(row.get("STORE_NAME")),
                _clean(row.get("OrderID")),
            )
            in allowed_order_scope
        ]
        observed_scope_rows = [
            {
                "store_code": _normalize_store_code(row.get("STORE_NAME")),
                "order_id": _clean(row.get("OrderID")),
                "db_row_id": _clean(row.get("_db_row_id")),
                "line_key": _clean(row.get("_line_key")),
                "my_size": _clean(row.get("MY_SIZE")),
            }
            for row in scoped_sheet_rows
        ]
        observed_scope_rows.sort(
            key=lambda item: (
                item["store_code"],
                item["order_id"],
                item["db_row_id"],
                item["line_key"],
            )
        )
        if observed_scope_rows != pinned_scope_rows:
            raise RuntimeError(
                "SalesRaw_Today row identity or MY_SIZE changed after READY preflight"
            )
    else:
        allowed_order_scope = {
            (
                _normalize_store_code(row.get("STORE_NAME")),
                _clean(row.get("OrderID")),
            )
            for row in sheet_rows
            if _normalize_store_code(row.get("STORE_NAME")) in enabled_stores
            and _clean(row.get("OrderID"))
        }
        scoped_sheet_rows = [
            row
            for row in sheet_rows
            if _normalize_store_code(row.get("STORE_NAME")) in enabled_stores
        ]
        pinned_scope_rows = []
    requested_db_row_ids = {
        _clean(row.get(writeback_spec["key_column"]))
        for row in scoped_sheet_rows
        if _clean(row.get(writeback_spec["key_column"]))
    }
    db_rows = _load_db_rows(db_path, requested_db_row_ids)
    plan = plan_size_writeback(
        sheet_rows=scoped_sheet_rows,
        db_rows=db_rows,
        key_column=writeback_spec["key_column"],
        source_column=writeback_spec["source_column"],
        require_visible_identity=True,
    )
    updates = plan["updates"]
    invalid_rows = plan["invalid_rows"]

    report = {
        "db_path": str(db_path),
        "spreadsheet_id": spreadsheet_id,
        "tab": writeback_spec["tab"],
        "target_date": target.isoformat(),
        "lookback_days": args.lookback_days,
        "db_row_selection": "exact_salesraw_row_ids",
        "allowed_order_scope_path": str(args.allowed_order_scope_file or ""),
        "allowed_order_count": len(allowed_order_scope),
        "sheet_rows_outside_scope": len(sheet_rows) - len(scoped_sheet_rows),
        "requested_db_row_count": len(requested_db_row_ids),
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
