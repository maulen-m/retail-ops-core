#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache
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
    extract_rows_with_positions_from_matrix,
    load_ops_board_contract,
    merge_rows_preserving_editables,
    resolve_service_account_json,
    resolve_spreadsheet_id,
    validate_contract_layout,
)
from core.calc.size_probability import PRODUCT_TYPE_DEFAULTS, calc_size_from_params, determine_size
from core.integrations.kaspi_order_stage import StageCode, classify_kaspi_stage_from_db_row
from core.ops.waybill_overdue_carryforward import get_overdue_waybill_ready_order_ids_from_db
from core.paths import data_path
from core.utils.kaspi_name_core_resolver import (
    KaspiNameCoreMaps,
    load_active_kaspi_name_core_maps,
    resolve_kaspi_name_core,
)


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_OUTPUT_ROOT = data_path("exports", "google_ops_board")
METADATA_TABS = {"README", "Config_Do_Not_Edit"}
SAME_DAY_PRESERVE_TABS = {"SalesRaw_Today", "Run_Control"}
PENDING_BOARD_STAGES = {
    StageCode.ACCEPTED_PENDING_ASSEMBLY,
    StageCode.ASSEMBLED_PENDING_HANDOVER,
}


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


def _clean_str(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _normalize_store_key(value: Any) -> str:
    store = _clean_str(value).upper()
    if store == "STORE-B":
        return "STOREB"
    return store


def _display_store_name(value: Any) -> str:
    store = _normalize_store_key(value)
    return {
        "ACMEWEAR": "AcmeWear",
        "UNIVERSAL": "Universal",
        "STOREB": "STORE-B",
        "11KZ": "11KZ",
        "MELVIS": "Store-C",
    }.get(store, _clean_str(value))


def _normalize_offer_key(value: Any) -> str:
    return " ".join(_clean_str(value).split()).casefold()


def _clean_offer_value(value: Any) -> str:
    offer = _clean_str(value)
    if offer.upper() in {"YES", "NO", "TRUE", "FALSE", "Y", "N"}:
        return ""
    return offer


def _first_non_empty(values: list[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _summarize_offer(offers: list[str]) -> str:
    unique = []
    seen = set()
    for offer in offers:
        cleaned = _clean_str(offer)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return f"{unique[0]} +{len(unique) - 1} more"


def _summarize_sku(skus: list[str]) -> str:
    unique = []
    seen = set()
    for sku in skus:
        cleaned = _clean_str(sku)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        unique.append(cleaned)
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return "MULTI"


def _summarize_size(rows: list[sqlite3.Row]) -> str:
    sizes = []
    seen = set()
    for row in rows:
        value = _clean_str(row["assigned_size"]) or _clean_str(row["my_size"])
        if not value or value in seen:
            continue
        seen.add(value)
        sizes.append(value)
    if not sizes:
        return ""
    if len(sizes) == 1:
        return sizes[0]
    return "MULTI"


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(float(value))
    except Exception:
        return None


def _is_shipped(rows: list[sqlite3.Row]) -> bool:
    shipped_statuses = {"SHIPPED", "COMPLETED"}
    for row in rows:
        if _clean_str(row["actual_shipment_date"]) or _clean_str(row["courier_transmission_date"]):
            return True
        if _clean_str(row["internal_status"]).upper() in shipped_statuses:
            return True
    return False


def _is_row_shipped(row: sqlite3.Row) -> bool:
    return _is_shipped([row])


def _ship_date(rows: list[sqlite3.Row], target_date: date) -> str:
    target_iso = target_date.isoformat()
    for row in rows:
        actual = _clean_str(row["actual_shipment_date"])
        if actual == target_iso:
            return actual
        courier = _clean_str(row["courier_transmission_date"])
        if courier[:10] == target_iso:
            return courier[:10]
    return ""


def _product_type_from_row(row: sqlite3.Row) -> str:
    direct = _clean_str(row["product_type"])
    if direct:
        return direct
    sku_key = _clean_str(row["sku_key"])
    if "_" in sku_key:
        return sku_key.split("_", 1)[0]
    return "CL"


@lru_cache(maxsize=4096)
def _cached_probable_size(
    db_path_str: str,
    kaspi_offer_name: str,
    sku_key: str,
    sku_id: str,
    product_type: str,
    customer_height: int | None,
    customer_weight: int | None,
) -> tuple[str, str, str]:
    try:
        result = determine_size(
            order={
                "kaspi_offer_name": kaspi_offer_name,
                "sku_key": sku_key,
                "sku_id": sku_id,
                "product_type": product_type,
            },
            customer_height=customer_height,
            customer_weight=customer_weight,
            db_path=Path(db_path_str),
        )
        return result.size, result.source, result.confidence
    except Exception:
        if customer_height and customer_weight:
            guessed = calc_size_from_params(customer_height, customer_weight, product_type)
            if guessed:
                return guessed, "CUSTOMER", "HIGH"
        return PRODUCT_TYPE_DEFAULTS.get(product_type, "L"), "DEFAULT", "LOW"


def _build_salesraw_line_key(row: sqlite3.Row) -> str:
    order_id = _clean_str(row["order_id"])
    planned_date = _clean_str(row["planned_shipment_date"])
    sku_token = _clean_str(row["sku_key"]) or _clean_str(row["sku_id"])
    offer_name = _clean_str(row["kaspi_offer_name"])
    quantity = str(int(row["quantity"] or 0))
    return f"{order_id}|{planned_date}|{sku_token}|{offer_name}|{quantity}"


def _load_db_rows(conn: sqlite3.Connection, *, start: date, target: date) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT fk.id, fk.order_id, fk.store_code, fk.planned_shipment_date, fk.kaspi_status, fk.internal_status,
               fk.kaspi_offer_name, fk.sku_key, fk.sku_id, fk.my_size, fk.assigned_size, fk.quantity,
               fk.waybill_url, fk.waybill_downloaded, fk.actual_shipment_date, fk.courier_transmission_date,
               fk.customer_first_name, fk.customer_last_name, fk.customer_phone,
               fk.customer_height_cm, fk.customer_weight_kg, fk.updated_at,
               fk.kaspi_status_detail, fk.signature_required, fk.delivery_mode,
               fk.returned_to_warehouse, fk.planned_delivery_date, fk.payment_mode,
               COALESCE(ds.product_type, '') AS product_type
        FROM fact_orders_kaspi fk
        LEFT JOIN dim_sku ds ON ds.sku_key = fk.sku_key
        WHERE planned_shipment_date BETWEEN ? AND ?
        ORDER BY fk.planned_shipment_date, fk.order_id, fk.id, fk.updated_at
        """,
        (start.isoformat(), target.isoformat()),
    ).fetchall()


def _select_operational_rows(
    rows: list[sqlite3.Row],
    *,
    overdue_ids_by_store: dict[str, set[str]],
    target_date: date,
) -> list[sqlite3.Row]:
    selected: list[sqlite3.Row] = []
    target_iso = target_date.isoformat()
    for row in rows:
        if _is_row_shipped(row):
            continue
        store_code = _normalize_store_key(row["store_code"])
        order_id = _clean_str(row["order_id"])
        planned_date = _clean_str(row["planned_shipment_date"])
        stage = classify_kaspi_stage_from_db_row(row)
        is_overdue = order_id in overdue_ids_by_store.get(store_code, set())
        is_today_pending = planned_date == target_iso and stage in PENDING_BOARD_STAGES
        if is_overdue or is_today_pending:
            selected.append(row)
    return selected


def _operational_status(row: sqlite3.Row, overdue_ids_by_store: dict[str, set[str]]) -> str:
    store_code = _normalize_store_key(row["store_code"])
    order_id = _clean_str(row["order_id"])
    if order_id in overdue_ids_by_store.get(store_code, set()):
        return "OVERDUE"
    return "TODAY"


def _resolve_kaspi_name_core(
    row: sqlite3.Row,
    *,
    kaspi_core_maps: KaspiNameCoreMaps,
) -> str:
    resolution = resolve_kaspi_name_core(
        store_code=row["store_code"],
        kaspi_offer_name=_clean_offer_value(row["kaspi_offer_name"]),
        sku_key=_clean_str(row["sku_key"]),
        sku_id=_clean_str(row["sku_id"]),
        maps=kaspi_core_maps,
    )
    return resolution.core or "UNKNOWN"


def _salesraw_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _clean_str(row.get("OrderID")),
        _clean_str(row.get("STORE_NAME")).casefold(),
        _clean_str(row.get("Kaspi_name_core")).casefold(),
        _clean_str(row.get("_db_row_id")),
    )


def _build_salesraw_row(
    row: sqlite3.Row,
    *,
    overdue_ids_by_store: dict[str, set[str]],
    db_path: Path,
    kaspi_core_maps: KaspiNameCoreMaps,
) -> dict[str, Any]:
    size_value = _clean_str(row["assigned_size"]) or _clean_str(row["my_size"])
    product_type = _product_type_from_row(row)
    height = _safe_int(row["customer_height_cm"])
    weight = _safe_int(row["customer_weight_kg"])
    probable_size, probable_source, probable_confidence = _cached_probable_size(
        str(db_path),
        _clean_str(row["kaspi_offer_name"]),
        _clean_str(row["sku_key"]),
        _clean_str(row["sku_id"]),
        product_type,
        height,
        weight,
    )
    kaspi_core = _resolve_kaspi_name_core(
        row,
        kaspi_core_maps=kaspi_core_maps,
    )
    return {
        "Status": _operational_status(row, overdue_ids_by_store),
        "Date": _clean_str(row["planned_shipment_date"]),
        "STORE_NAME": _display_store_name(row["store_code"]),
        "HEIGHT": height if height is not None else "",
        "WEIGHT": weight if weight is not None else "",
        "Quantity": int(row["quantity"] or 0),
        "Kaspi_name_core": kaspi_core,
        "OrderID": _clean_str(row["order_id"]),
        "MY_SIZE": size_value,
        "PROBABLE_SIZE": probable_size,
        "KASPI_OFFER_NAME": _clean_str(row["kaspi_offer_name"]),
        "SKU_key": _clean_str(row["sku_key"]),
        "_db_row_id": _clean_str(row["id"]),
        "_line_key": _build_salesraw_line_key(row),
        "_probable_size_source": probable_source,
        "_probable_size_confidence": probable_confidence,
    }


def _build_order_record(order_id: str, rows: list[sqlite3.Row], now_iso: str) -> dict[str, Any]:
    store = _first_non_empty([_clean_str(r["store_code"]) for r in rows])
    planned_date = min(_clean_str(r["planned_shipment_date"]) for r in rows if _clean_str(r["planned_shipment_date"]))
    status = _first_non_empty([_clean_str(r["internal_status"]) for r in rows]) or _first_non_empty(
        [_clean_str(r["kaspi_status"]) for r in rows]
    )
    first_names = [_clean_str(r["customer_first_name"]) for r in rows]
    last_names = [_clean_str(r["customer_last_name"]) for r in rows]
    full_names = []
    for first, last in zip(first_names, last_names):
        full = " ".join(part for part in (first, last) if part).strip()
        if full:
            full_names.append(full)
    customer_name = _first_non_empty(full_names)
    phone = _first_non_empty([_clean_str(r["customer_phone"]) for r in rows])
    quantity = sum(int(r["quantity"] or 0) for r in rows)
    size_value = _summarize_size(rows)
    waybill_ready = "yes" if any(int(r["waybill_downloaded"] or 0) for r in rows) else "no"
    offer_name = _summarize_offer([_clean_str(r["kaspi_offer_name"]) for r in rows])
    sku = _summarize_sku([_clean_str(r["sku_key"]) for r in rows])
    return {
        "order_id": order_id,
        "store": store,
        "planned_date": planned_date,
        "status": status,
        "customer_name": customer_name,
        "phone": phone,
        "offer_name": offer_name,
        "sku": sku,
        "quantity": quantity,
        "my_size": size_value,
        "package_qty": "",
        "waybill_status": "ready" if waybill_ready == "yes" else "pending",
        "whatsapp_status": "",
        "exception_flag": "MISSING_SIZE" if not size_value else "",
        "last_sync_at": now_iso,
        "waybill_ready": waybill_ready,
        "pdf_ready": waybill_ready,
        "whatsapp_batch": "",
        "shipping_status": "ready" if size_value else "needs_size",
    }


def build_phase1_payload(
    db_path: Path,
    contract,
    target_date: str | date,
    lookback_days: int,
    now_iso: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    target = _resolve_target_date(target_date.isoformat() if isinstance(target_date, date) else target_date)
    start = target - timedelta(days=max(lookback_days - 1, 0))
    now_text = now_iso or datetime.now(ALMATY_TZ).isoformat()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = _load_db_rows(conn, start=start, target=target)
        overdue_ids_by_store = get_overdue_waybill_ready_order_ids_from_db(
            db_path,
            target_date=target,
            lookback_days=lookback_days,
        )
        selected_rows = _select_operational_rows(
            rows,
            overdue_ids_by_store=overdue_ids_by_store,
            target_date=target,
        )
        kaspi_core_maps = load_active_kaspi_name_core_maps(
            conn,
            sku_keys={_clean_str(row["sku_key"]) for row in selected_rows},
            store_offer_pairs={
                (_clean_str(row["store_code"]), _clean_offer_value(row["kaspi_offer_name"]))
                for row in selected_rows
            },
        )
    finally:
        conn.close()

    all_grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        all_grouped[_clean_str(row["order_id"])].append(row)
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in selected_rows:
        grouped[_clean_str(row["order_id"])].append(row)

    salesraw_rows: list[dict[str, Any]] = []
    active_order_rows: list[dict[str, Any]] = []
    needs_size_rows: list[dict[str, Any]] = []
    shipping_rows: list[dict[str, Any]] = []
    shipped_rows: list[dict[str, Any]] = []
    exception_rows: list[dict[str, Any]] = []
    run_control_rows: list[dict[str, Any]] = [
        {
            "target_date": target.isoformat(),
            "ready_for_closeout": "HOLD",
            "ready_set_by": "",
            "ready_set_at": "",
            "notes": "",
            "last_verified_ready_at": "",
            "last_orchestrator_run_id": "",
            "last_orchestrator_status": "",
        }
    ]

    for order_id in sorted(all_grouped):
        order_rows = all_grouped[order_id]
        if _is_shipped(order_rows):
            shipped_at = _ship_date(order_rows, target)
            if shipped_at == target.isoformat():
                record = _build_order_record(order_id=order_id, rows=order_rows, now_iso=now_text)
                shipped_rows.append(
                    {
                        "order_id": order_id,
                        "store": record["store"],
                        "planned_date": record["planned_date"],
                        "my_size": record["my_size"],
                        "package_qty": "",
                        "shipped_at": shipped_at,
                        "whatsapp_batch": "",
                        "whatsapp_sent_at": "",
                        "last_sync_at": now_text,
                    }
                )

    for order_id in sorted(grouped):
        order_rows = grouped[order_id]
        record = _build_order_record(order_id=order_id, rows=order_rows, now_iso=now_text)

        active_order_rows.append(
            {
                key: record[key]
                for key in contract.tabs["Orders_Today"].headers
            }
        )

        if record["my_size"]:
            shipping_rows.append(
                {
                    "order_id": order_id,
                    "store": record["store"],
                    "planned_date": record["planned_date"],
                    "my_size": record["my_size"],
                    "package_qty": "",
                    "waybill_ready": record["waybill_ready"],
                    "pdf_ready": record["pdf_ready"],
                    "whatsapp_batch": "",
                    "shipping_status": "ready",
                    "last_sync_at": now_text,
                }
            )
        else:
            needs_size_rows.append(
                {
                    "order_id": order_id,
                    "store": record["store"],
                    "planned_date": record["planned_date"],
                    "offer_name": record["offer_name"],
                    "quantity": record["quantity"],
                    "my_size": "",
                    "size_status": "needs_size",
                    "assigned_to": "",
                    "note": "",
                    "last_sync_at": now_text,
                }
            )
            exception_rows.append(
                {
                    "exception_key": f"{order_id}:MISSING_SIZE",
                    "order_id": order_id,
                    "store": record["store"],
                    "planned_date": record["planned_date"],
                    "exception_type": "MISSING_SIZE",
                    "exception_note": "",
                    "owner": "",
                    "resolved": "",
                    "last_sync_at": now_text,
                }
            )

    for row in selected_rows:
        built = _build_salesraw_row(
                    row,
                    overdue_ids_by_store=overdue_ids_by_store,
                    db_path=db_path,
                    kaspi_core_maps=kaspi_core_maps,
                )
        salesraw_rows.append({key: built.get(key, "") for key in contract.tabs["SalesRaw_Today"].headers})
    salesraw_rows.sort(key=_salesraw_sort_key)

    readme_rows = [
        {"field": "contract_version", "value": str(contract.version), "notes": "Repo-owned Google ops board contract"},
        {"field": "sync_mode", "value": contract.sync_mode, "notes": "Phase-1 board is DB-first"},
        {"field": "target_date", "value": target.isoformat(), "notes": "Operational date for this sync"},
        {
            "field": "lookback_days",
            "value": str(lookback_days),
            "notes": "Carry-forward overdue rows are limited to the waybill-ready lookback window",
        },
        {"field": "source_of_truth", "value": "db/app.db", "notes": "Google Sheet is an ops surface, not the canonical truth"},
        {
            "field": "employee_edit_policy",
            "value": "preserve_editable_columns_only",
            "notes": "Publisher preserves contract-marked editable columns; DB writeback is explicit",
        },
        {
            "field": "overdue_policy",
            "value": "waybill_carryforward_only",
            "notes": "OVERDUE is reserved for waybill-ready carry-forward rows, not generic older backlog",
        },
        {
            "field": "closeout_gate",
            "value": "Run_Control.READY + no blank SalesRaw_Today.MY_SIZE",
            "notes": "18:30 closeout runs only after the explicit ready toggle and the sizing gate are both green",
        },
        {"field": "last_sync_at", "value": now_text, "notes": "Latest publisher build time"},
    ]

    config_rows = [
        {"key": "spreadsheet_id", "value": contract.spreadsheet_id, "notes": "Google Sheet target"},
        {"key": "write_env_gate", "value": contract.write_env_gate, "notes": "Required with --apply for sheet writes"},
        {"key": "db_write_env_gate", "value": contract.db_write_env_gate, "notes": "Required with --apply for DB writeback"},
        {
            "key": "closeout_write_env_gate",
            "value": contract.closeout_write_env_gate,
            "notes": "Required with --apply for the 18:30 automated closeout run",
        },
        {
            "key": "size_writeback_contract",
            "value": "SalesRaw_Today.MY_SIZE -> fact_orders_kaspi.assigned_size",
            "notes": "Narrow phase-2 writeback path by db row id",
        },
        {
            "key": "editable_columns",
            "value": (
                "SalesRaw_Today.MY_SIZE | "
                "Orders_Today.exception_flag | Needs_Size.my_size,size_status,assigned_to,note | "
                "Shipping_Queue.package_qty,shipping_status | Exceptions.exception_note,owner,resolved | "
                "Shipped_Today.whatsapp_batch,whatsapp_sent_at"
            ),
            "notes": "Only these columns are preserved from the live sheet during publish",
        },
        {
            "key": "service_account_env",
            "value": ",".join(contract.service_account_env_vars),
            "notes": "Any one of these may point to the local JSON credentials file",
        },
    ]

    return {
        "README": readme_rows,
        "SalesRaw_Today": salesraw_rows,
        "Run_Control": run_control_rows,
        "Orders_Today": active_order_rows,
        "Needs_Size": needs_size_rows,
        "Shipping_Queue": shipping_rows,
        "Exceptions": exception_rows,
        "Shipped_Today": shipped_rows,
        "Config_Do_Not_Edit": config_rows,
    }


def _resolve_db_path(path: Path | None) -> Path:
    return Path(path).expanduser() if path else data_path("db", "app.db")


def _build_output_path(output_json: Path | None, target_date: date) -> Path:
    if output_json is not None:
        return output_json
    stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_ROOT / target_date.isoformat() / f"sync_google_ops_board_{stamp}.json"


def _read_previous_target_date(contract, before_snapshot: dict[str, list[list[Any]]]) -> str:
    readme_rows = extract_rows_from_matrix(contract.tabs["README"].headers, before_snapshot.get("README"))
    for row in readme_rows:
        if str(row.get("field") or "").strip() == "target_date":
            return str(row.get("value") or "").strip()
    return ""


def _invalid_layout_tabs(layout_report: dict[str, Any]) -> set[str]:
    invalid = set(layout_report.get("missing_tabs") or [])
    for tab_name, tab_report in (layout_report.get("tabs") or {}).items():
        if not tab_report.get("header_ok", False):
            invalid.add(str(tab_name))
    return invalid


def _append_only_tab_rows(tab_contract, fresh_rows: list[dict[str, Any]], existing_rows: list[dict[str, Any]]) -> dict[str, Any]:
    existing_keys = {
        _clean_str(row.get(tab_contract.key_column)): row
        for row in existing_rows
        if _clean_str(row.get(tab_contract.key_column))
    }
    append_rows: list[dict[str, Any]] = []
    final_rows = list(existing_rows)
    for fresh in fresh_rows:
        key = _clean_str(fresh.get(tab_contract.key_column))
        if key and key in existing_keys:
            continue
        append_rows.append(fresh)
        final_rows.append(fresh)
    return {
        "mode": "append_only",
        "existing_rows": existing_rows,
        "fresh_rows": fresh_rows,
        "update_rows": [],
        "append_rows": append_rows,
        "final_rows": final_rows,
    }


def _upsert_preserve_tab_rows(
    tab_contract,
    fresh_rows: list[dict[str, Any]],
    existing_rows_with_positions: list[dict[str, Any]],
) -> dict[str, Any]:
    existing_by_key: dict[str, dict[str, Any]] = {}
    final_rows = [dict(entry["row"]) for entry in existing_rows_with_positions]
    final_index_by_key: dict[str, int] = {}
    for idx, entry in enumerate(existing_rows_with_positions):
        key = _clean_str(entry["row"].get(tab_contract.key_column))
        if not key or key in existing_by_key:
            continue
        existing_by_key[key] = entry
        final_index_by_key[key] = idx

    update_rows: list[dict[str, Any]] = []
    append_rows: list[dict[str, Any]] = []
    for fresh in fresh_rows:
        key = _clean_str(fresh.get(tab_contract.key_column))
        if key and key in existing_by_key:
            existing_entry = existing_by_key[key]
            merged = merge_rows_preserving_editables(
                tab_contract=tab_contract,
                fresh_rows=[fresh],
                existing_rows=[existing_entry["row"]],
            )[0]
            if merged != existing_entry["row"]:
                update_rows.append({"sheet_row": int(existing_entry["sheet_row"]), "row": merged})
            final_rows[final_index_by_key[key]] = merged
            continue
        append_rows.append(fresh)
        final_rows.append(fresh)

    return {
        "mode": "upsert_preserve",
        "existing_rows": [dict(entry["row"]) for entry in existing_rows_with_positions],
        "fresh_rows": fresh_rows,
        "update_rows": update_rows,
        "append_rows": append_rows,
        "final_rows": final_rows,
    }


def build_publish_plan(
    contract,
    before_snapshot: dict[str, list[list[Any]]],
    fresh_payload: dict[str, list[dict[str, Any]]],
    target_date: str | date,
    *,
    force_rewrite_operational_tabs: bool = False,
) -> dict[str, Any]:
    target = _resolve_target_date(target_date.isoformat() if isinstance(target_date, date) else str(target_date))
    target_iso = target.isoformat()
    previous_target_date = _read_previous_target_date(contract, before_snapshot)
    same_day = bool(previous_target_date) and previous_target_date == target_iso and not force_rewrite_operational_tabs
    rollover = bool(previous_target_date) and previous_target_date != target_iso

    tab_actions: dict[str, dict[str, Any]] = {}
    for tab_name, tab_contract in contract.tabs.items():
        existing_rows = extract_rows_from_matrix(tab_contract.headers, before_snapshot.get(tab_name))
        existing_rows_with_positions = extract_rows_with_positions_from_matrix(
            tab_contract.headers,
            before_snapshot.get(tab_name),
        )
        fresh_rows = fresh_payload.get(tab_name) or []
        if tab_name in METADATA_TABS or not same_day or tab_name not in SAME_DAY_PRESERVE_TABS:
            tab_actions[tab_name] = {
                "mode": "rewrite",
                "existing_rows": existing_rows,
                "fresh_rows": fresh_rows,
                "update_rows": [],
                "append_rows": [],
                "final_rows": list(fresh_rows),
            }
            continue
        tab_actions[tab_name] = _upsert_preserve_tab_rows(tab_contract, fresh_rows, existing_rows_with_positions)

    return {
        "target_date": target_iso,
        "previous_target_date": previous_target_date,
        "rollover": rollover,
        "same_day_preserve": same_day,
        "force_rewrite_operational_tabs": force_rewrite_operational_tabs,
        "tab_actions": tab_actions,
    }


def write_rollover_archive(
    archive_root: Path,
    previous_target_date: str,
    before_snapshot: dict[str, list[list[Any]]],
) -> Path:
    stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    archive_path = archive_root / "archive" / previous_target_date / f"google_ops_board_rollover_{stamp}.json"
    dump_json(
        archive_path,
        {
            "generated_at": datetime.now(ALMATY_TZ).isoformat(),
            "previous_target_date": previous_target_date,
            "snapshot": before_snapshot,
        },
    )
    return archive_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync the phase-1 Google Ops Board from db/app.db.")
    parser.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: db/app.db)")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH, help="Contract YAML path")
    parser.add_argument("--service-account-json", type=Path, default=None, help="Path to service-account JSON")
    parser.add_argument("--spreadsheet-id", type=str, default=None, help="Override spreadsheet ID")
    parser.add_argument("--target-date", type=str, default="today", help="Target date (default: today)")
    parser.add_argument("--lookback-days", type=int, default=5, help="Operational lookback window (default: 5)")
    parser.add_argument("--validate-only", action="store_true", help="Read-only validation; no sheet writes")
    parser.add_argument("--apply", action="store_true", help="Write sheet tabs (default: dry-run)")
    parser.add_argument(
        "--force-rewrite-operational-tabs",
        action="store_true",
        help="Rewrite live operational tabs even on same-day publishes (repair / reset mode)",
    )
    parser.add_argument("--output-json", type=Path, default=None, help="Optional JSON report path")
    args = parser.parse_args(argv)

    contract = load_ops_board_contract(args.contract)
    target = _resolve_target_date(args.target_date)
    _require_apply_gate(args.apply, contract.write_env_gate)

    db_path = _resolve_db_path(args.db)
    service_account_json = resolve_service_account_json(args.service_account_json, contract=contract)
    spreadsheet_id = resolve_spreadsheet_id(args.spreadsheet_id, contract=contract)
    client = GoogleOpsBoardClient.from_service_account_file(spreadsheet_id, service_account_json)

    created_tabs: list[str] = []
    if args.apply:
        created_tabs = client.ensure_tabs(list(contract.tabs))
    sheet_names = client.get_sheet_names()
    existing_tab_names = [tab_name for tab_name in contract.tabs if tab_name in sheet_names]
    header_rows = client.get_header_rows(existing_tab_names)
    layout_report = validate_contract_layout(contract=contract, sheet_names=sheet_names, header_rows=header_rows)

    payload = build_phase1_payload(
        db_path=db_path,
        contract=contract,
        target_date=target,
        lookback_days=args.lookback_days,
    )
    before_snapshot = client.snapshot_tabs(existing_tab_names)
    publish_plan = build_publish_plan(
        contract=contract,
        before_snapshot=before_snapshot,
        fresh_payload=payload,
        target_date=target,
        force_rewrite_operational_tabs=args.force_rewrite_operational_tabs,
    )
    invalid_tabs = _invalid_layout_tabs(layout_report)
    if invalid_tabs:
        for tab_name, rows in payload.items():
            if tab_name not in invalid_tabs:
                continue
            existing_rows = extract_rows_from_matrix(contract.tabs[tab_name].headers, before_snapshot.get(tab_name))
            publish_plan["tab_actions"][tab_name] = {
                "mode": "rewrite",
                "existing_rows": existing_rows,
                "fresh_rows": rows,
                "update_rows": [],
                "append_rows": [],
                "final_rows": list(rows),
            }
        if invalid_tabs == set(contract.tabs):
            publish_plan["same_day_preserve"] = False
        publish_plan["layout_repair_rewrite"] = True

    tab_counts: dict[str, dict[str, int]] = {}
    for tab_name, action in publish_plan["tab_actions"].items():
        tab_counts[tab_name] = {
            "fresh_rows": len(action["fresh_rows"]),
            "existing_rows": len(action["existing_rows"]),
            "update_rows": len(action.get("update_rows") or []),
            "append_rows": len(action["append_rows"]),
            "write_rows": len(action["final_rows"]),
        }

    report = {
        "ok": layout_report["ok"] or args.apply,
        "mode": "apply" if args.apply else ("validate_only" if args.validate_only else "dry_run"),
        "db_path": str(db_path),
        "spreadsheet_id": spreadsheet_id,
        "service_account_json": str(service_account_json),
        "target_date": target.isoformat(),
        "lookback_days": args.lookback_days,
        "layout_report": layout_report,
        "previous_target_date": publish_plan["previous_target_date"],
        "rollover": bool(publish_plan["rollover"]),
        "same_day_preserve": bool(publish_plan["same_day_preserve"]),
        "force_rewrite_operational_tabs": bool(args.force_rewrite_operational_tabs),
        "layout_repair_rewrite": bool(publish_plan.get("layout_repair_rewrite")),
        "layout_repair_tabs": sorted(invalid_tabs),
        "created_tabs": created_tabs,
        "tab_counts": tab_counts,
    }

    if args.apply:
        archive_path = None
        if publish_plan["rollover"]:
            archive_path = write_rollover_archive(
                archive_root=DEFAULT_OUTPUT_ROOT,
                previous_target_date=publish_plan["previous_target_date"],
                before_snapshot=before_snapshot,
            )
            report["rollover_archive_path"] = str(archive_path)
        for tab_name, action in publish_plan["tab_actions"].items():
            if action["mode"] == "upsert_preserve":
                client.update_tab_rows(tab_name, contract.tabs[tab_name].headers, action["update_rows"])
                client.append_tab_rows(tab_name, contract.tabs[tab_name].headers, action["append_rows"])
                continue
            if action["mode"] == "append_only":
                client.append_tab_rows(tab_name, contract.tabs[tab_name].headers, action["append_rows"])
                continue
            client.clear_tab(tab_name)
            client.write_tab_rows(tab_name, contract.tabs[tab_name].headers, action["final_rows"])
        report["ui_applied_tabs"] = client.apply_contract_ui(contract)
        report["write_applied"] = True
        report["after_layout_report"] = validate_contract_layout(
            contract=contract,
            sheet_names=client.get_sheet_names(),
            header_rows=client.get_header_rows(list(contract.tabs)),
        )
    else:
        report["ui_applied_tabs"] = []
        report["write_applied"] = False

    output_path = _build_output_path(args.output_json, target)
    dump_json(output_path, report)
    print(f"Google Ops Board sync report: {output_path}")
    print(f"Mode: {report['mode']}")
    print(f"Layout OK before write: {layout_report['ok']}")
    print(f"Same-day preserve: {report['same_day_preserve']}")
    print(f"Rollover: {report['rollover']}")
    for tab_name in contract.tabs:
        counts = tab_counts[tab_name]
        print(
            f"  {tab_name}: fresh={counts['fresh_rows']} existing={counts['existing_rows']} "
            f"update={counts['update_rows']} append={counts['append_rows']} write={counts['write_rows']}"
        )
    if args.apply:
        print("Sheet write applied.")
        if not report["after_layout_report"]["ok"]:
            print("WARNING: contract still not fully clean after apply.")
            return 1
    elif args.validate_only and not layout_report["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
