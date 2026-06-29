#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from datetime import date, datetime, time, timedelta
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
from core.utils.kaspi_order_core_overrides import load_order_name_core_overrides


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_OUTPUT_ROOT = data_path("exports", "google_ops_board")
METADATA_TABS = {"README", "Config_Do_Not_Edit"}
SAME_DAY_PRESERVE_TABS = {"SalesRaw_Today", "Run_Control"}
PENDING_BOARD_STAGES = {
    StageCode.ACCEPTED_PENDING_ASSEMBLY,
    StageCode.ASSEMBLED_PENDING_HANDOVER,
}
WAREHOUSE_STORE_TO_API = {
    "30137883_PP1": "ACMEWEAR",
    "30000001_PP1": "UNIVERSAL",
    "30290083_PP1": "11KZ",
    "30000002_PP1": "STOREB",
    "30362323_PP1": "MELVIS",
    "PP1": "ACMEWEAR",
    "PP2": "ACMEWEAR",
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
    store = _clean_str(value).upper().replace(" ", "")
    if store in WAREHOUSE_STORE_TO_API:
        return WAREHOUSE_STORE_TO_API[store]
    if store == "STORE-B":
        return "STOREB"
    if store == "STORE_B":
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


def _is_blankish_source_value(value: Any) -> bool:
    return _clean_str(value).casefold() in {"", "nan", "none", "null"}


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


def _row_value(row: Any, key: str, default: Any = "") -> Any:
    if hasattr(row, "keys"):
        try:
            if key in row.keys():
                return row[key]
        except Exception:
            pass
    if hasattr(row, "get"):
        try:
            return row.get(key, default)
        except Exception:
            return default
    return default


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(int(value))
    text = _clean_str(value).casefold()
    return text in {"1", "true", "yes", "y", "да"}


def _format_express_delivery_status(row: Any) -> str:
    if _truthy_flag(_row_value(row, "express")):
        return "EXPRESS"
    delivery_mode = _clean_str(_row_value(row, "delivery_mode")).upper()
    kaspi_status = _clean_str(_row_value(row, "kaspi_status")).upper()
    if "SELF" in delivery_mode or kaspi_status == "PICKUP":
        return "SELF_PICKUP"
    if "PICKUP" in delivery_mode:
        return "PICKUP"
    if delivery_mode:
        return "STANDARD"
    return ""


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


def _order_key(row: sqlite3.Row) -> tuple[str, str]:
    return (_normalize_store_key(row["store_code"]), _clean_str(row["order_id"]))


def _handed_over_order_keys(rows: list[sqlite3.Row]) -> set[tuple[str, str]]:
    return {_order_key(row) for row in rows if _is_row_shipped(row)}


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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _optional_fk_column(columns: set[str], column_name: str, *, default_sql: str = "''") -> str:
    if column_name in columns:
        return f"fk.{column_name}"
    return f"{default_sql} AS {column_name}"


def _load_db_rows(conn: sqlite3.Connection, *, start: date, target: date) -> list[sqlite3.Row]:
    fact_columns = _table_columns(conn, "fact_orders_kaspi")
    express_expr = _optional_fk_column(fact_columns, "express", default_sql="0")
    return conn.execute(
        f"""
        SELECT fk.id, fk.order_id, fk.store_code, fk.planned_shipment_date, fk.created_at,
               fk.kaspi_status, fk.internal_status,
               fk.kaspi_offer_name, fk.sku_key, fk.sku_id, fk.my_size, fk.assigned_size, fk.quantity,
               fk.waybill_url, fk.waybill_downloaded, fk.actual_shipment_date, fk.courier_transmission_date,
               fk.customer_first_name, fk.customer_last_name, fk.customer_phone,
               fk.customer_height_cm, fk.customer_weight_kg, fk.updated_at,
               fk.kaspi_status_detail, fk.signature_required, fk.delivery_mode,
               {express_expr},
               fk.returned_to_warehouse, fk.planned_delivery_date, fk.payment_mode,
               COALESCE(ds.product_type, '') AS product_type
        FROM fact_orders_kaspi fk
        LEFT JOIN dim_sku ds ON ds.sku_key = fk.sku_key
        WHERE planned_shipment_date BETWEEN ? AND ?
        ORDER BY fk.planned_shipment_date, fk.order_id, fk.id, fk.updated_at
        """,
        (start.isoformat(), target.isoformat()),
    ).fetchall()


def _parse_local_dt(value: Any) -> datetime | None:
    text = _clean_str(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    if "T" not in normalized and " " in normalized:
        normalized = normalized.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ALMATY_TZ)
    return parsed.astimezone(ALMATY_TZ)


def _parse_cutoff(value: str) -> tuple[int, int]:
    text = str(value or "").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except Exception as exc:
        raise ValueError(f"Invalid same-day cutoff value: {value!r}") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Invalid same-day cutoff value: {value!r}")
    return hour, minute


def _row_is_before_same_day_cutoff(row: sqlite3.Row, *, contract, target_date: date) -> bool:
    store_code = _normalize_store_key(row["store_code"])
    cutoff_text = contract.same_day_cutoff_by_store.get(store_code) or contract.same_day_cutoff_default
    cutoff_hour, cutoff_minute = _parse_cutoff(cutoff_text)
    created_at = _parse_local_dt(row["created_at"])
    if created_at is None:
        return True
    cutoff_dt = datetime.combine(target_date, time(cutoff_hour, cutoff_minute), tzinfo=ALMATY_TZ)
    return created_at <= cutoff_dt


def _parse_iso_date(value: Any) -> date | None:
    text = _clean_str(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _is_pending_carryforward_row(
    row: sqlite3.Row,
    *,
    target_date: date,
    lookback_days: int,
    contract,
) -> bool:
    planned_date = _parse_iso_date(row["planned_shipment_date"])
    if planned_date is None or planned_date >= target_date:
        return False
    min_date = target_date - timedelta(days=max(lookback_days - 1, 0))
    if planned_date < min_date:
        return False
    stage = classify_kaspi_stage_from_db_row(row)
    if stage not in PENDING_BOARD_STAGES:
        return False
    return _row_is_before_same_day_cutoff(row, contract=contract, target_date=planned_date)


def _build_board_overdue_ids_by_store(
    rows: list[sqlite3.Row],
    *,
    waybill_overdue_ids_by_store: dict[str, set[str]],
    target_date: date,
    lookback_days: int,
    contract,
) -> dict[str, set[str]]:
    handed_over_keys = _handed_over_order_keys(rows)
    overdue_ids_by_store = {
        store_code: set(order_ids)
        for store_code, order_ids in waybill_overdue_ids_by_store.items()
    }
    for store_code, order_id in handed_over_keys:
        overdue_ids_by_store.get(store_code, set()).discard(order_id)
    for row in rows:
        if _order_key(row) in handed_over_keys:
            continue
        if not _is_pending_carryforward_row(
            row,
            target_date=target_date,
            lookback_days=lookback_days,
            contract=contract,
        ):
            continue
        store_code = _normalize_store_key(row["store_code"])
        order_id = _clean_str(row["order_id"])
        if store_code and order_id:
            overdue_ids_by_store.setdefault(store_code, set()).add(order_id)
    return overdue_ids_by_store


def _select_operational_rows(
    rows: list[sqlite3.Row],
    *,
    overdue_ids_by_store: dict[str, set[str]],
    target_date: date,
    contract,
) -> list[sqlite3.Row]:
    selected: list[sqlite3.Row] = []
    target_iso = target_date.isoformat()
    handed_over_keys = _handed_over_order_keys(rows)
    for row in rows:
        if _order_key(row) in handed_over_keys:
            continue
        store_code = _normalize_store_key(row["store_code"])
        order_id = _clean_str(row["order_id"])
        planned_date = _clean_str(row["planned_shipment_date"])
        stage = classify_kaspi_stage_from_db_row(row)
        is_overdue = order_id in overdue_ids_by_store.get(store_code, set())
        is_today_pending = (
            planned_date == target_iso
            and stage in PENDING_BOARD_STAGES
            and _row_is_before_same_day_cutoff(row, contract=contract, target_date=target_date)
        )
        if is_overdue or is_today_pending:
            selected.append(row)
    return selected


def _shadow_group_key(row: sqlite3.Row) -> tuple[str, str, str]:
    return (
        _clean_str(row["order_id"]),
        _normalize_store_key(row["store_code"]),
        _clean_str(row["planned_shipment_date"]),
    )


def _is_placeholder_shadow_row(row: sqlite3.Row) -> bool:
    return (
        _is_blankish_source_value(_clean_offer_value(row["kaspi_offer_name"]))
        and _is_blankish_source_value(row["sku_key"])
        and _is_blankish_source_value(row["sku_id"])
    )


def _drop_placeholder_shadow_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    concrete_groups = {
        _shadow_group_key(row)
        for row in rows
        if not _is_placeholder_shadow_row(row)
    }
    if not concrete_groups:
        return rows
    return [
        row
        for row in rows
        if not (_is_placeholder_shadow_row(row) and _shadow_group_key(row) in concrete_groups)
    ]


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
    order_core_overrides: dict[str, str] | None = None,
) -> str:
    order_id = _clean_str(row["order_id"])
    preferred_core = (order_core_overrides or {}).get(order_id, "")
    resolution = resolve_kaspi_name_core(
        store_code=row["store_code"],
        kaspi_offer_name=_clean_offer_value(row["kaspi_offer_name"]),
        sku_key=_clean_str(row["sku_key"]),
        sku_id=_clean_str(row["sku_id"]),
        maps=kaspi_core_maps,
        preferred_core=preferred_core,
        preferred_source="forced_core" if preferred_core else "preferred_core",
    )
    return resolution.core or "UNKNOWN"


def _row_store_sort_value(row: dict[str, Any]) -> str:
    return _display_store_name(row.get("STORE_NAME") or row.get("store")).casefold()


def _row_order_sort_value(row: dict[str, Any]) -> str:
    return _clean_str(row.get("OrderID") or row.get("order_id"))


def _salesraw_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _row_store_sort_value(row),
        _row_order_sort_value(row),
        _clean_str(row.get("Kaspi_name_core")).casefold(),
        _clean_str(row.get("_db_row_id")),
    )


def _operational_tab_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _row_store_sort_value(row),
        _row_order_sort_value(row),
        _clean_str(row.get("planned_date") or row.get("Date")),
        _clean_str(row.get("exception_key") or row.get("_db_row_id")),
    )


def _sort_operational_rows(tab_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if tab_name == "SalesRaw_Today":
        return sorted(rows, key=_salesraw_sort_key)
    if tab_name in {"Orders_Today", "Needs_Size", "Shipping_Queue", "Exceptions", "Shipped_Today"}:
        return sorted(rows, key=_operational_tab_sort_key)
    return list(rows)


def _build_salesraw_row(
    row: sqlite3.Row,
    *,
    overdue_ids_by_store: dict[str, set[str]],
    db_path: Path,
    kaspi_core_maps: KaspiNameCoreMaps,
    order_core_overrides: dict[str, str],
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
        order_core_overrides=order_core_overrides,
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
        "ExpressDeliveryStatus": _format_express_delivery_status(row),
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
        waybill_overdue_ids_by_store = get_overdue_waybill_ready_order_ids_from_db(
            db_path,
            target_date=target,
            lookback_days=lookback_days,
        )
        overdue_ids_by_store = _build_board_overdue_ids_by_store(
            rows,
            waybill_overdue_ids_by_store=waybill_overdue_ids_by_store,
            target_date=target,
            lookback_days=lookback_days,
            contract=contract,
        )
        selected_rows = _select_operational_rows(
            rows,
            overdue_ids_by_store=overdue_ids_by_store,
            target_date=target,
            contract=contract,
        )
        selected_rows = _drop_placeholder_shadow_rows(selected_rows)
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
    order_core_overrides = load_order_name_core_overrides()

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
                    order_core_overrides=order_core_overrides,
                )
        salesraw_rows.append({key: built.get(key, "") for key in contract.tabs["SalesRaw_Today"].headers})

    salesraw_rows = _sort_operational_rows("SalesRaw_Today", salesraw_rows)
    active_order_rows = _sort_operational_rows("Orders_Today", active_order_rows)
    needs_size_rows = _sort_operational_rows("Needs_Size", needs_size_rows)
    shipping_rows = _sort_operational_rows("Shipping_Queue", shipping_rows)
    exception_rows = _sort_operational_rows("Exceptions", exception_rows)
    shipped_rows = _sort_operational_rows("Shipped_Today", shipped_rows)

    readme_rows = [
        {"field": "contract_version", "value": str(contract.version), "notes": "Repo-owned Google ops board contract"},
        {"field": "sync_mode", "value": contract.sync_mode, "notes": "Phase-1 board is DB-first"},
        {"field": "target_date", "value": target.isoformat(), "notes": "Operational date for this sync"},
        {
            "field": "lookback_days",
            "value": str(lookback_days),
            "notes": "Carry-forward overdue rows are limited to the operational lookback window",
        },
        {"field": "source_of_truth", "value": "db/app.db", "notes": "Google Sheet is an ops surface, not the canonical truth"},
        {
            "field": "employee_edit_policy",
            "value": "preserve_editable_columns_only",
            "notes": "Publisher preserves contract-marked editable columns; DB writeback is explicit",
        },
        {
            "field": "overdue_policy",
            "value": "operational_carryforward",
            "notes": "OVERDUE covers waybill-ready carry-forward plus prior pending rows that were inside store cutoff",
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
                "SalesRaw_Today.HEIGHT,WEIGHT,MY_SIZE | "
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
    run_control_rows = extract_rows_from_matrix(
        contract.tabs["Run_Control"].headers,
        before_snapshot.get("Run_Control"),
    )
    for row in run_control_rows:
        target_date = str(row.get("target_date") or "").strip()
        if target_date:
            return target_date
    return ""


def _invalid_layout_tabs(layout_report: dict[str, Any]) -> set[str]:
    invalid = set(layout_report.get("missing_tabs") or [])
    for tab_name, tab_report in (layout_report.get("tabs") or {}).items():
        if not tab_report.get("header_ok", False):
            invalid.add(str(tab_name))
    return invalid


def _is_trailing_header_extension(expected_headers: list[str], observed_row: list[Any] | None) -> bool:
    observed = [str(cell or "").strip() for cell in (observed_row or [])]
    while observed and not observed[-1]:
        observed.pop()
    return bool(
        observed
        and len(observed) < len(expected_headers)
        and observed == expected_headers[: len(observed)]
    )


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
        fresh_rows = _sort_operational_rows(tab_name, fresh_payload.get(tab_name) or [])
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
    layout_header_update_tabs = {
        tab_name
        for tab_name in list(invalid_tabs)
        if _is_trailing_header_extension(
            contract.tabs[tab_name].headers,
            header_rows.get(tab_name),
        )
    }
    invalid_tabs -= layout_header_update_tabs
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
    publish_plan["layout_header_update_tabs"] = sorted(layout_header_update_tabs)

    tab_counts: dict[str, dict[str, int]] = {}
    planned_write_operations = 0
    for tab_name, action in publish_plan["tab_actions"].items():
        write_rows = len(action["final_rows"])
        if action["mode"] == "rewrite" and action["existing_rows"] == action["final_rows"] and tab_name not in invalid_tabs:
            write_rows = 0
        header_update = tab_name in layout_header_update_tabs
        operation_count = (
            len(action.get("update_rows") or [])
            + len(action.get("append_rows") or [])
            + write_rows
            + (1 if header_update else 0)
        )
        planned_write_operations += operation_count
        tab_counts[tab_name] = {
            "fresh_rows": len(action["fresh_rows"]),
            "existing_rows": len(action["existing_rows"]),
            "update_rows": len(action.get("update_rows") or []),
            "append_rows": len(action["append_rows"]),
            "write_rows": len(action["final_rows"]),
            "header_update": header_update,
            "write_operations": operation_count,
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
        "layout_header_update_tabs": sorted(layout_header_update_tabs),
        "created_tabs": created_tabs,
        "tab_counts": tab_counts,
        "planned_write_operations": planned_write_operations,
        "write_noop": planned_write_operations == 0,
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
        skipped_noop_tabs: list[str] = []
        for tab_name, action in publish_plan["tab_actions"].items():
            if tab_name in layout_header_update_tabs:
                headers = contract.tabs[tab_name].headers
                client.update_tab_rows(
                    tab_name,
                    headers,
                    [{"sheet_row": 1, "row": {header: header for header in headers}}],
                )
            if action["mode"] == "upsert_preserve":
                client.update_tab_rows(tab_name, contract.tabs[tab_name].headers, action["update_rows"])
                client.append_tab_rows(tab_name, contract.tabs[tab_name].headers, action["append_rows"])
                continue
            if action["mode"] == "append_only":
                client.append_tab_rows(tab_name, contract.tabs[tab_name].headers, action["append_rows"])
                continue
            if action["existing_rows"] == action["final_rows"] and tab_name not in invalid_tabs:
                skipped_noop_tabs.append(tab_name)
                continue
            client.clear_tab(tab_name)
            client.write_tab_rows(tab_name, contract.tabs[tab_name].headers, action["final_rows"])
        report["skipped_noop_tabs"] = skipped_noop_tabs
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
