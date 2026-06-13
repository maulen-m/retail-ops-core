#!/usr/bin/env python3
"""Rebuild sales_fact_v2 from internal Kaspi order entries + status change dates (fail-closed)."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.parsers.kaspi_parser import extract_sku_from_article

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "sales_fact_v2_rebuild"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"


class RebuildError(RuntimeError):
    """Raised when strict rebuild contracts are violated."""


GENERIC_HEADER_SKU_KEYS = {"", "UNKNOWN", "CL", "ELS", "WB", "FUR"}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_sales_fact_v2_rebuild_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def _parse_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text[:10]) if len(text) >= 10 and text[4] == "-" else None
    if parsed is not None:
        return parsed.date().isoformat()
    try:
        return datetime.strptime(text[:10], "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None


def _normalize_status(internal_status: str, kaspi_status: str) -> str:
    raw_internal = str(internal_status or "").strip().upper()
    raw_kaspi = str(kaspi_status or "").strip().upper()
    if raw_internal in {"CANCELLED", "CANCELED"} or raw_kaspi in {"ОТМЕНЕН", "CANCELLED", "CANCELED"}:
        return "CANCELLED"
    if raw_internal in {"RETURNED"} or raw_kaspi in {"ВОЗВРАЩЕН", "RETURNED", "RETURN"}:
        return "RETURNED"
    # SHIPPED is an in-transit state and must not be counted as delivered sales truth.
    if raw_internal in {"COMPLETED", "DELIVERED"} or raw_kaspi in {"ВЫДАН", "ЗАВЕРШЕН", "DELIVERED", "COMPLETED"}:
        return "DELIVERED"
    return "OPEN"


def _store_fallback_rank(row_store_code: Any, entry_store_code: str) -> int:
    row_store = str(row_store_code or "").strip().upper()
    if row_store == str(entry_store_code or "").strip().upper():
        return 2
    if row_store in {"", "UNKNOWN"}:
        return 1
    return 0


def _resolve_sale_date(order_row: dict[str, Any], status: str) -> str | None:
    status_date = _parse_date(order_row.get("status_updated_at"))
    actual_ship = _parse_date(order_row.get("actual_shipment_date"))
    planned_ship = _parse_date(order_row.get("planned_shipment_date"))
    created = _parse_date(order_row.get("created_at"))

    if status in {"DELIVERED", "RETURNED", "CANCELLED"}:
        return status_date or actual_ship or planned_ship or created
    return None


def _is_generic_header_sku_key(value: str | None) -> bool:
    return str(value or "").strip().upper() in GENERIC_HEADER_SKU_KEYS


def _load_offer_map(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[str, str]]:
    if not _table_exists(conn, "dim_kaspi_article_map"):
        return {}
    cols = _table_columns(conn, "dim_kaspi_article_map")
    where_clause = ""
    if "active_flag" in cols:
        where_clause = "WHERE COALESCE(active_flag, 1) = 1"
    rows = conn.execute(
        f"""
        SELECT
            UPPER(COALESCE(store_code, '')),
            UPPER(COALESCE(kaspi_article, '')),
            UPPER(COALESCE(kaspi_offer_name, '')),
            UPPER(COALESCE(sku_key, '')),
            UPPER(COALESCE(sku_id, ''))
        FROM dim_kaspi_article_map
        {where_clause}
        """
    ).fetchall()
    mapping: dict[tuple[str, str], tuple[str, str]] = {}
    for store, article, offer, sku_key, sku_id in rows:
        store_norm = str(store or "").strip().upper()
        sku_key_norm = str(sku_key or "").strip().upper()
        if not store_norm or not sku_key_norm:
            continue
        sid = str(sku_id).strip().upper() or sku_key_norm
        for token in (article, offer):
            token_norm = str(token or "").strip().upper()
            if token_norm:
                mapping[(store_norm, token_norm)] = (sku_key_norm, sid)
    return mapping


def _extract_entry_offer_from_raw_json(raw_json: Any) -> tuple[str, str]:
    """Return offer code/name preserved in the raw Kaspi order-entry payload."""
    if not raw_json:
        return "", ""
    try:
        payload = json.loads(str(raw_json))
    except (TypeError, ValueError, json.JSONDecodeError):
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    attributes = payload.get("attributes")
    if not isinstance(attributes, dict):
        return "", ""
    offer = attributes.get("offer")
    if not isinstance(offer, dict):
        return "", ""
    code = str(offer.get("code") or "").strip().upper()
    name = str(offer.get("name") or "").strip()
    return code, name


def build_sales_fact_v2_rows_from_entries(
    conn: sqlite3.Connection,
    *,
    as_of: date,
    start_date: date | None = None,
    strict: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    for table in ("fact_orders_kaspi", "fact_order_entries_kaspi", "sales_fact_v2"):
        if not _table_exists(conn, table):
            raise RebuildError(f"missing required table: {table}")

    offer_map = _load_offer_map(conn)
    order_cols = _table_columns(conn, "fact_orders_kaspi")
    entry_cols = _table_columns(conn, "fact_order_entries_kaspi")
    if "offer_id" not in entry_cols:
        raise RebuildError("fact_order_entries_kaspi missing offer_id")
    raw_json_sql = (
        "COALESCE(raw_json, '') AS raw_json,"
        if "raw_json" in entry_cols
        else "'' AS raw_json,"
    )

    assigned_size_sql = (
        "COALESCE(assigned_size, '') AS assigned_size,"
        if "assigned_size" in order_cols
        else "'' AS assigned_size,"
    )
    unit_price_sql = (
        "COALESCE(unit_price_kzt, 0) AS unit_price_kzt,"
        if "unit_price_kzt" in order_cols
        else "0 AS unit_price_kzt,"
    )
    if "delivery_cost_for_seller" in order_cols and "delivery_cost" in order_cols:
        delivery_fee_sql = "COALESCE(delivery_cost_for_seller, delivery_cost, 0) AS delivery_fee,"
    elif "delivery_cost_for_seller" in order_cols:
        delivery_fee_sql = "COALESCE(delivery_cost_for_seller, 0) AS delivery_fee,"
    elif "delivery_cost" in order_cols:
        delivery_fee_sql = "COALESCE(delivery_cost, 0) AS delivery_fee,"
    else:
        delivery_fee_sql = "0 AS delivery_fee,"
    orders = conn.execute(
        """
        SELECT
            order_id,
            UPPER(COALESCE(store_code, '')) AS store_code,
            COALESCE(kaspi_offer_name, '') AS kaspi_offer_name,
            COALESCE(sku_key, '') AS sku_key,
            COALESCE(sku_id, '') AS sku_id,
            """
        + assigned_size_sql
        + """
            COALESCE(my_size, '') AS my_size,
            COALESCE(quantity, 1) AS quantity,
            """
        + unit_price_sql
        + delivery_fee_sql
        + """
            COALESCE(status_updated_at, '') AS status_updated_at,
            COALESCE(actual_shipment_date, '') AS actual_shipment_date,
            COALESCE(planned_shipment_date, '') AS planned_shipment_date,
            COALESCE(created_at, '') AS created_at,
            COALESCE(internal_status, '') AS internal_status,
            COALESCE(kaspi_status, '') AS kaspi_status
        FROM fact_orders_kaspi
        """
    ).fetchall()

    order_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    order_by_id: dict[str, list[dict[str, Any]]] = {}
    order_payloads: list[dict[str, Any]] = []
    for row in orders:
        payload = dict(zip(
            [
                "order_id",
                "store_code",
                "kaspi_offer_name",
                "sku_key",
                "sku_id",
                "assigned_size",
                "my_size",
                "quantity",
                "unit_price_kzt",
                "delivery_fee",
                "status_updated_at",
                "actual_shipment_date",
                "planned_shipment_date",
                "created_at",
                "internal_status",
                "kaspi_status",
            ],
            row,
        ))
        key = (str(payload["order_id"]), str(payload["store_code"]))
        order_payloads.append(payload)
        order_by_pair.setdefault(key, []).append(payload)
        order_by_id.setdefault(str(payload["order_id"]), []).append(payload)

    entries = conn.execute(
        """
        SELECT
            order_id,
            UPPER(COALESCE(store_code, '')) AS store_code,
            UPPER(COALESCE(offer_id, '')) AS offer_id,
            """
        + raw_json_sql
        + """
            COALESCE(quantity, 0) AS quantity,
            COALESCE(total_price_kzt, 0) AS total_price_kzt
        FROM fact_order_entries_kaspi
        """
    ).fetchall()
    entry_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for order_id, store_code, offer_id, raw_json, qty, total in entries:
        offer_norm = str(offer_id or "").strip().upper()
        raw_offer_code, raw_offer_name = _extract_entry_offer_from_raw_json(raw_json)
        if not offer_norm and raw_offer_code:
            offer_norm = raw_offer_code
        key = (str(order_id), str(store_code), offer_norm)
        grouped = entry_groups.setdefault(
            key,
            {
                "order_id": str(order_id),
                "store_code": str(store_code),
                "offer_id": offer_norm,
                "quantity": 0.0,
                "total_price_kzt": 0.0,
                "raw_offer_name": raw_offer_name,
            },
        )
        grouped["quantity"] += float(qty or 0.0)
        grouped["total_price_kzt"] += float(total or 0.0)
        if raw_offer_name and not grouped.get("raw_offer_name"):
            grouped["raw_offer_name"] = raw_offer_name
    entries = [
        (
            row["order_id"],
            row["store_code"],
            row["offer_id"],
            row["quantity"],
            row["total_price_kzt"],
            row.get("raw_offer_name") or "",
        )
        for row in entry_groups.values()
    ]

    totals_by_order: dict[tuple[str, str], float] = {}
    for order_id, store_code, _offer_id, _qty, total, _raw_offer_name in entries:
        key = (str(order_id), str(store_code))
        totals_by_order[key] = totals_by_order.get(key, 0.0) + float(total or 0.0)

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    skipped_open = 0
    rows_built_from_entries = 0
    rows_built_from_headers = 0

    for order_id, store_code, offer_id, qty, total, raw_offer_name in entries:
        pair = (str(order_id), str(store_code))
        order_rows = list(order_by_pair.get(pair, []))
        if not order_rows:
            order_rows = []
        fallback_rows = [
            row
            for row in order_by_id.get(str(order_id), [])
            if _store_fallback_rank(row.get("store_code"), str(store_code)) > 0
            and row not in order_rows
        ]
        candidate_rows = order_rows + fallback_rows
        if not candidate_rows:
            if strict and start_date is None:
                errors.append(f"order header missing for order_id={order_id} store={store_code}")
            continue

        status_row = sorted(
            candidate_rows,
            key=lambda r: (
                1 if _normalize_status(r.get("internal_status", ""), r.get("kaspi_status", "")) != "OPEN" else 0,
                _store_fallback_rank(r.get("store_code"), str(store_code)),
                _parse_date(r.get("status_updated_at")) or "",
                _parse_date(r.get("actual_shipment_date")) or "",
                _parse_date(r.get("planned_shipment_date")) or "",
            ),
            reverse=True,
        )[0]
        status = _normalize_status(status_row.get("internal_status", ""), status_row.get("kaspi_status", ""))
        if status == "OPEN":
            skipped_open += 1
            continue

        sale_date = _resolve_sale_date(status_row, status)
        if not sale_date:
            if strict:
                errors.append(f"missing sale_date for order_id={order_id} store={store_code}")
            continue
        if start_date and sale_date < start_date.isoformat():
            continue
        if sale_date > as_of.isoformat():
            continue

        offer_norm = str(offer_id or "").strip().upper()
        sku_key = ""
        sku_id = ""
        my_size = ""
        parsed = extract_sku_from_article(offer_norm, offer_norm)
        parsed_key = str(parsed.get("sku_key") or "").strip().upper()
        parsed_id = str(parsed.get("sku_id") or "").strip().upper()
        parsed_size = str(parsed.get("my_size") or "").strip().upper()

        mapped = offer_map.get((str(store_code), offer_norm))
        if mapped:
            sku_key, sku_id = mapped

        weak_sku_id = bool(sku_key) and (not sku_id or sku_id == sku_key)
        if not sku_key or weak_sku_id:
            sku_candidates = {str(r.get("sku_key") or "").strip().upper() for r in order_rows if str(r.get("sku_key") or "").strip()}
            if len(sku_candidates) == 1 and (not sku_key or next(iter(sku_candidates)) == sku_key):
                sku_key = next(iter(sku_candidates))
                sku_id_candidates = {
                    str(r.get("sku_id") or "").strip().upper()
                    for r in order_rows
                    if str(r.get("sku_id") or "").strip()
                }
                if len(sku_id_candidates) == 1:
                    header_sku_id = next(iter(sku_id_candidates))
                    if header_sku_id and (not sku_id or sku_id == sku_key or header_sku_id.startswith(f"{sku_key}_")):
                        sku_id = header_sku_id

        weak_sku_id = bool(sku_key) and (not sku_id or sku_id == sku_key)
        if parsed_key and (
            _is_generic_header_sku_key(sku_key)
            or not sku_key
            or (weak_sku_id and parsed_key == sku_key)
        ):
            sku_key = parsed_key
            if parsed_id:
                sku_id = parsed_id
            if parsed_size:
                my_size = parsed_size

        if not sku_key:
            if parsed_key:
                sku_key = parsed_key
            if parsed_id:
                sku_id = parsed_id
            if parsed_size:
                my_size = parsed_size

        if not sku_key:
            if strict and status != "CANCELLED":
                errors.append(
                    f"missing sku mapping for order_id={order_id} store={store_code} offer_id={offer_norm}"
                )
            continue

        line_identity_has_sku_id = bool(sku_id and sku_id != sku_key)
        assigned_size_candidates = {
            str(r.get("assigned_size") or "").strip().upper()
            for r in order_rows
            if str(r.get("assigned_size") or "").strip()
        }
        if assigned_size_candidates and not line_identity_has_sku_id:
            my_size = sorted(assigned_size_candidates)[0]

        size_candidates = {
            str(r.get("my_size") or "").strip().upper()
            for r in order_rows
            if str(r.get("my_size") or "").strip()
        }
        if not my_size and size_candidates and not line_identity_has_sku_id:
            my_size = sorted(size_candidates)[0]

        if not my_size and sku_key and sku_id.startswith(f"{sku_key}_"):
            my_size = sku_id[len(sku_key) + 1 :]

        if my_size and (not sku_id or sku_id == sku_key):
            sku_id = f"{sku_key}_{my_size}"
        elif not sku_id:
            sku_id = sku_key

        order_total = totals_by_order.get(pair, 0.0)
        gross = float(total or 0.0)
        quantity = float(qty or 0.0)
        if quantity <= 0:
            quantity = 1.0
        sell_price = gross / quantity if quantity > 0 else gross
        delivery_fee_total = float(status_row.get("delivery_fee") or 0.0)
        delivery_fee = delivery_fee_total * (gross / order_total) if order_total > 0 else delivery_fee_total
        net_rev = gross - delivery_fee

        offer_name = offer_norm or str(raw_offer_name or "").strip() or sku_key
        rows.append(
            {
                "order_id": str(order_id),
                "order_date": sale_date,
                "sku_key": sku_key,
                "sku_id": sku_id,
                "my_size": my_size,
                "kaspi_offer_name": offer_name,
                "store_code": str(store_code),
                "quantity": int(round(quantity)),
                "sell_price_kzt": float(sell_price),
                "delivery_fee": round(float(delivery_fee), 2),
                "cogs": None,
                "net_rev": round(float(net_rev), 2),
                "profit": None,
                "status": status,
                "return_flag": 1 if status == "RETURNED" else 0,
                "return_date": sale_date if status == "RETURNED" else None,
                "source_file": "KASPI_API_ENTRIES_REBUILD",
                "api_updated_at": None,
            }
        )
        rows_built_from_entries += 1

    entry_pairs = {(str(row[0]), str(row[1])) for row in entries}
    entry_order_ids = {str(row[0]) for row in entries}
    specific_header_order_ids = {
        str(header.get("order_id") or "").strip()
        for header in order_payloads
        if str(header.get("store_code") or "").strip().upper() not in {"", "UNKNOWN"}
    }
    identity_header_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for header in order_payloads:
        order_id = str(header.get("order_id") or "").strip()
        store_code = str(header.get("store_code") or "").strip().upper()
        sku_key = str(header.get("sku_key") or "").strip().upper()
        sku_id = str(header.get("sku_id") or "").strip().upper()
        offer_name = str(header.get("kaspi_offer_name") or "").strip().lower()
        if (
            order_id
            and store_code
            and sku_key
            and sku_id
            and offer_name not in {"", "nan", "none", "null"}
        ):
            identity_header_by_pair.setdefault((order_id, store_code), header)

    seen_header_keys: set[tuple[str, str, str, str]] = set()
    skipped_identityless_duplicate_headers = 0
    for header in order_payloads:
        order_id = str(header.get("order_id") or "").strip()
        store_code = str(header.get("store_code") or "").strip().upper()
        if not order_id or not store_code:
            continue
        if (order_id, store_code) in entry_pairs:
            continue
        if store_code in {"", "UNKNOWN"} and (
            order_id in entry_order_ids or order_id in specific_header_order_ids
        ):
            continue

        status = _normalize_status(header.get("internal_status", ""), header.get("kaspi_status", ""))
        if status == "OPEN":
            skipped_open += 1
            continue

        sale_date = _resolve_sale_date(header, status)
        if not sale_date:
            if strict and status == "DELIVERED":
                errors.append(f"missing required evidence sale_date for order_id={order_id} store={store_code}")
            continue
        if start_date and sale_date < start_date.isoformat():
            continue
        if sale_date > as_of.isoformat():
            continue

        sku_key = str(header.get("sku_key") or "").strip().upper()
        sku_id = str(header.get("sku_id") or "").strip().upper()
        my_size = str(header.get("assigned_size") or header.get("my_size") or "").strip().upper()
        offer_name_raw = str(header.get("kaspi_offer_name") or "").strip()
        identity_header = identity_header_by_pair.get((order_id, store_code))
        if (
            not sku_key
            and not sku_id
            and identity_header is not None
            and offer_name_raw.lower() in {"", "nan", "none", "null"}
        ):
            skipped_identityless_duplicate_headers += 1
            sku_key = str(identity_header.get("sku_key") or "").strip().upper()
            sku_id = str(identity_header.get("sku_id") or "").strip().upper()
            my_size = str(
                identity_header.get("assigned_size") or identity_header.get("my_size") or ""
            ).strip().upper()
            offer_name_raw = str(identity_header.get("kaspi_offer_name") or "").strip()

        if not my_size and sku_key and sku_id.startswith(f"{sku_key}_"):
            my_size = sku_id[len(sku_key) + 1 :]
        if my_size and sku_key and (not sku_id or sku_id == sku_key):
            sku_id = f"{sku_key}_{my_size}"

        quantity = float(header.get("quantity") or 0.0)
        sell_price = float(header.get("unit_price_kzt") or 0.0)
        if identity_header is not None:
            if quantity <= 0:
                quantity = float(identity_header.get("quantity") or 0.0)
            if sell_price <= 0:
                sell_price = float(identity_header.get("unit_price_kzt") or 0.0)
        missing_fields = []
        if not sku_key or not sku_id:
            missing_fields.append("sku_identity")
        if quantity <= 0:
            missing_fields.append("quantity")
        if sell_price <= 0:
            missing_fields.append("unit_price_kzt")
        if missing_fields:
            if strict and status == "DELIVERED":
                errors.append(
                    "missing required evidence "
                    f"{','.join(missing_fields)} for order_id={order_id} store={store_code}"
                )
            continue

        qty_int = int(round(quantity))
        if qty_int <= 0:
            if strict and status == "DELIVERED":
                errors.append(f"missing required evidence quantity for order_id={order_id} store={store_code}")
            continue
        gross = sell_price * qty_int
        delivery_fee = float(header.get("delivery_fee") or 0.0)
        kaspi_offer_name = offer_name_raw if offer_name_raw.lower() not in {"", "nan", "none", "null"} else sku_key
        key = (order_id, sku_id, store_code, kaspi_offer_name)
        if key in seen_header_keys:
            continue
        seen_header_keys.add(key)
        rows.append(
            {
                "order_id": order_id,
                "order_date": sale_date,
                "sku_key": sku_key,
                "sku_id": sku_id,
                "my_size": my_size or "",
                "kaspi_offer_name": kaspi_offer_name,
                "store_code": store_code,
                "quantity": qty_int,
                "sell_price_kzt": float(sell_price),
                "delivery_fee": round(delivery_fee, 2),
                "cogs": None,
                "net_rev": round(float(gross - delivery_fee), 2),
                "profit": None,
                "status": status,
                "return_flag": 1 if status == "RETURNED" else 0,
                "return_date": sale_date if status == "RETURNED" else None,
                "source_file": "KASPI_API_HEADER_FALLBACK_REBUILD",
                "api_updated_at": None,
            }
        )
        rows_built_from_headers += 1

    if strict and errors:
        raise RebuildError("; ".join(errors[:30]))

    rows.sort(
        key=lambda r: (
            r["order_date"],
            r["store_code"],
            r["order_id"],
            r["sku_id"],
            r["kaspi_offer_name"],
        )
    )
    summary = {
        "rows_source": len(entries),
        "rows_built": len(rows),
        "rows_built_from_entries": rows_built_from_entries,
        "rows_built_from_headers": rows_built_from_headers,
        "errors_count": len(errors),
        "errors_sample": errors[:50],
        "skipped_open": skipped_open,
        "skipped_identityless_duplicate_headers": skipped_identityless_duplicate_headers,
    }
    return rows, summary


def _load_existing_by_keys(conn: sqlite3.Connection, keys: list[tuple[str, str, str, str]]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    if not keys:
        return {}
    order_ids = sorted({k[0] for k in keys})
    placeholders = ",".join("?" for _ in order_ids)
    rows = conn.execute(
        f"""
        SELECT order_id, sku_id, UPPER(COALESCE(store_code, '')), kaspi_offer_name,
               order_date, sku_key, my_size, quantity, sell_price_kzt, delivery_fee, net_rev,
               status, return_flag, return_date
        FROM sales_fact_v2
        WHERE order_id IN ({placeholders})
        """,
        tuple(order_ids),
    ).fetchall()
    payload: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    key_set = set(keys)
    for row in rows:
        key = (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
        if key not in key_set:
            continue
        payload[key] = {
            "order_date": str(row[4] or ""),
            "sku_key": str(row[5] or ""),
            "my_size": str(row[6] or ""),
            "quantity": int(round(float(row[7] or 0))),
            "sell_price_kzt": float(row[8] or 0.0),
            "delivery_fee": float(row[9] or 0.0),
            "net_rev": float(row[10] or 0.0),
            "status": str(row[11] or ""),
            "return_flag": int(row[12] or 0),
            "return_date": str(row[13] or "") if row[13] is not None else None,
        }
    return payload


def _load_anchor_order_store_keys(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT DISTINCT CAST(order_id AS TEXT) AS order_id, UPPER(COALESCE(store_code, '')) AS store_code
        FROM sales_fact_v2
        WHERE UPPER(COALESCE(source_file, '')) = 'OCEAN_DROP_ANCHOR'
          AND UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED'
          AND COALESCE(return_flag, 0) = 0
        """
    ).fetchall()
    return {(str(row[0]), str(row[1])) for row in rows}


def _load_existing_kaspi_rebuild_keys(
    conn: sqlite3.Connection,
    *,
    start_date: date | None = None,
    as_of: date | None = None,
) -> list[tuple[str, str, str, str]]:
    filters = [
        "UPPER(COALESCE(source_file, '')) IN ('KASPI_API_ENTRIES_REBUILD', 'KASPI_API_HEADER_FALLBACK_REBUILD')"
    ]
    params: list[Any] = []
    if start_date is not None:
        filters.append("order_date >= ?")
        params.append(start_date.isoformat())
    if as_of is not None:
        filters.append("order_date <= ?")
        params.append(as_of.isoformat())
    where_clause = " AND ".join(filters)
    rows = conn.execute(
        f"""
        SELECT
            CAST(order_id AS TEXT) AS order_id,
            CAST(sku_id AS TEXT) AS sku_id,
            UPPER(COALESCE(store_code, '')) AS store_code,
            CAST(kaspi_offer_name AS TEXT) AS kaspi_offer_name
        FROM sales_fact_v2
        WHERE {where_clause}
        """,
        params,
    ).fetchall()
    return [(str(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in rows]


def build_rebuild_plan(
    *,
    rows: list[dict[str, Any]],
    conn: sqlite3.Connection,
    start_date: date | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    anchor_order_store = _load_anchor_order_store_keys(conn)
    filtered_rows: list[dict[str, Any]] = []
    skipped_anchor_overlap = 0
    for row in rows:
        order_store = (str(row["order_id"]), str(row["store_code"]))
        if order_store in anchor_order_store:
            skipped_anchor_overlap += 1
            continue
        filtered_rows.append(row)

    keys = [
        (r["order_id"], r["sku_id"], r["store_code"], r["kaspi_offer_name"])
        for r in filtered_rows
    ]
    existing = _load_existing_by_keys(conn, keys)

    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    unchanged = 0

    for row in filtered_rows:
        key = (row["order_id"], row["sku_id"], row["store_code"], row["kaspi_offer_name"])
        current = existing.get(key)
        if current is None:
            inserts.append(row)
            continue
        changed = False
        for field in ("order_date", "sku_key", "my_size", "quantity", "sell_price_kzt", "delivery_fee", "net_rev", "status", "return_flag", "return_date"):
            left = current.get(field)
            right = row.get(field)
            if isinstance(left, float) or isinstance(right, float):
                if abs(float(left or 0.0) - float(right or 0.0)) > 1e-6:
                    changed = True
                    break
            elif str(left or "") != str(right or ""):
                changed = True
                break
        if changed:
            updates.append(row)
        else:
            unchanged += 1

    target_keys = set(keys)
    existing_kaspi_rebuild_keys = _load_existing_kaspi_rebuild_keys(
        conn,
        start_date=start_date,
        as_of=as_of,
    )
    delete_keys = sorted(key for key in existing_kaspi_rebuild_keys if key not in target_keys)

    return {
        "rows_input_count": len(rows),
        "rows_filtered_count": len(filtered_rows),
        "skipped_anchor_overlap_count": skipped_anchor_overlap,
        "insert_count": len(inserts),
        "update_count": len(updates),
        "unchanged_count": unchanged,
        "delete_count": len(delete_keys),
        "rows_insert": inserts,
        "rows_update": updates,
        "rows_delete_keys": delete_keys,
    }


def _upsert(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
            quantity, sell_price_kzt, delivery_fee, cogs, net_rev, profit,
            status, return_flag, return_date, source_file, api_updated_at
        ) VALUES (
            :order_id, :order_date, :sku_key, :sku_id, :my_size, :kaspi_offer_name, :store_code,
            :quantity, :sell_price_kzt, :delivery_fee, :cogs, :net_rev, :profit,
            :status, :return_flag, :return_date, :source_file, :api_updated_at
        )
        ON CONFLICT(order_id, sku_id, store_code, kaspi_offer_name)
        DO UPDATE SET
            order_date=excluded.order_date,
            sku_key=excluded.sku_key,
            my_size=excluded.my_size,
            quantity=excluded.quantity,
            sell_price_kzt=excluded.sell_price_kzt,
            delivery_fee=excluded.delivery_fee,
            cogs=excluded.cogs,
            net_rev=excluded.net_rev,
            profit=excluded.profit,
            status=excluded.status,
            return_flag=excluded.return_flag,
            return_date=excluded.return_date,
            source_file=excluded.source_file,
            api_updated_at=excluded.api_updated_at,
            ingested_at=CURRENT_TIMESTAMP
        """,
        rows,
    )
    return len(rows)


def _delete_by_keys(conn: sqlite3.Connection, keys: list[tuple[str, str, str, str]]) -> int:
    if not keys:
        return 0
    conn.executemany(
        """
        DELETE FROM sales_fact_v2
        WHERE order_id = ?
          AND sku_id = ?
          AND UPPER(COALESCE(store_code, '')) = ?
          AND kaspi_offer_name = ?
        """,
        keys,
    )
    return len(keys)


def run_rebuild(
    *,
    db_path: Path,
    as_of: date,
    output_root: Path,
    strict: bool,
    apply: bool,
    start_date: date | None,
    backup_root: Path,
) -> dict[str, Any]:
    if not db_path.exists():
        raise RebuildError(f"db not found: {db_path}")

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_json = out_dir / "rebuild_plan.json"
    plan_md = out_dir / "rebuild_plan.md"
    summary_json = out_dir / "rebuild_summary.json"

    conn = sqlite3.connect(str(db_path))
    try:
        rows, summary = build_sales_fact_v2_rows_from_entries(
            conn,
            as_of=as_of,
            start_date=start_date,
            strict=strict,
        )
        plan = build_rebuild_plan(rows=rows, conn=conn, start_date=start_date, as_of=as_of)

        payload = {
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
            "as_of": as_of.isoformat(),
            "start_date": start_date.isoformat() if start_date else None,
            "rows_source": summary["rows_source"],
            "rows_built": summary["rows_built"],
            "rows_built_from_entries": summary["rows_built_from_entries"],
            "rows_built_from_headers": summary["rows_built_from_headers"],
            "rows_input_count": plan["rows_input_count"],
            "rows_filtered_count": plan["rows_filtered_count"],
            "skipped_anchor_overlap_count": plan["skipped_anchor_overlap_count"],
            "insert_count": plan["insert_count"],
            "update_count": plan["update_count"],
            "delete_count": plan["delete_count"],
            "unchanged_count": plan["unchanged_count"],
            "errors_count": summary["errors_count"],
            "errors_sample": summary["errors_sample"],
            "skipped_open": summary["skipped_open"],
            "apply_status": "DRY_RUN",
            "rows_applied": 0,
            "rows_deleted": 0,
            "backup_path": None,
        }

        plan_payload = {
            "as_of": as_of.isoformat(),
            "start_date": start_date.isoformat() if start_date else None,
            **plan,
        }
        plan_json.write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        plan_md.write_text(
            "\n".join(
                [
                    "# sales_fact_v2 rebuild plan",
                    "",
                    f"- as_of: `{as_of.isoformat()}`",
                    f"- start_date: `{start_date.isoformat() if start_date else ''}`",
                    f"- rows_input_count: `{plan['rows_input_count']}`",
                    f"- rows_filtered_count: `{plan['rows_filtered_count']}`",
                    f"- skipped_anchor_overlap_count: `{plan['skipped_anchor_overlap_count']}`",
                    f"- rows_built: `{summary['rows_built']}`",
                    f"- rows_built_from_entries: `{summary['rows_built_from_entries']}`",
                    f"- rows_built_from_headers: `{summary['rows_built_from_headers']}`",
                    f"- insert_count: `{plan['insert_count']}`",
                    f"- update_count: `{plan['update_count']}`",
                    f"- delete_count: `{plan['delete_count']}`",
                    f"- unchanged_count: `{plan['unchanged_count']}`",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        if apply:
            if str(os.environ.get("ENABLE_SALES_FACT_V2_REBUILD_APPLY") or "").strip() != "1":
                raise RebuildError("ENABLE_SALES_FACT_V2_REBUILD_APPLY=1 is required for --apply")
            backup = _backup_db(db_path, backup_root)
            rows_deleted = _delete_by_keys(conn, plan["rows_delete_keys"])
            rows_applied = _upsert(conn, plan["rows_insert"] + plan["rows_update"])
            conn.commit()
            payload["apply_status"] = "APPLIED"
            payload["rows_applied"] = rows_applied
            payload["rows_deleted"] = rows_deleted
            payload["backup_path"] = str(backup)

        summary_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        conn.close()

    return {
        "plan_json": str(plan_json),
        "plan_md": str(plan_md),
        "summary_json": str(summary_json),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild sales_fact_v2 from internal order entries")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = run_rebuild(
        db_path=args.db,
        as_of=date.fromisoformat(str(args.as_of)),
        start_date=date.fromisoformat(str(args.start_date)) if args.start_date else None,
        output_root=args.output_root,
        backup_root=args.backup_root,
        strict=bool(args.strict),
        apply=bool(args.apply),
    )
    print(f"rebuild_plan_json={report['plan_json']}")
    print(f"rebuild_plan_md={report['plan_md']}")
    print(f"rebuild_summary_json={report['summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
