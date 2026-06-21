#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db
from core.parsers.kaspi_export_parser import parse_active_orders
from core.paths import data_path
from core.utils.sku_normalize import normalize_size


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_EXPORT_PATH = data_path("excel_ui", "ActiveOrders", "ActiveOrders.xlsx")
DEFAULT_BACKUP_ROOT = data_path("runtime", "backups")
DEFAULT_OUTPUT_ROOT = data_path("exports", "google_ops_board")
WRITE_ENV_GATE = "ENABLE_KASPI_ACTIVEORDERS_DB_WRITE"
LINE_GRAIN_CONFLICT_COLUMNS = ("order_id", "store_code", "line_identity_key", "sku_id")
LEGACY_CONFLICT_COLUMNS = ("order_id", "sku_id", "store_code")


def _require_apply_gate(apply: bool) -> None:
    if apply and str(__import__("os").environ.get(WRITE_ENV_GATE) or "").strip() != "1":
        raise RuntimeError(f"{WRITE_ENV_GATE}=1 is required with --apply")


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


def _clean_upper(value: Any) -> str:
    return _clean(value).upper()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _index_columns(conn: sqlite3.Connection, index_name: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
    return tuple(str(row[2]) for row in rows)


def _has_unique_index(conn: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> bool:
    for row in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if int(row[2] or 0) != 1:
            continue
        if _index_columns(conn, str(row[1])) == columns:
            return True
    return False


def _line_identity_key(order: dict[str, Any]) -> str:
    return (
        _clean(order.get("kaspi_article"))
        or _clean(order.get("line_identity_key"))
        or _clean(order.get("kaspi_offer_name"))
        or _clean(order.get("sku_id"))
    )


def _public_line_identity_candidates(row: dict[str, Any]) -> set[str]:
    sku_id = _clean(row.get("sku_id"))
    values = [
        _clean(row.get("kaspi_article")),
        _clean(row.get("line_identity_key")),
        _clean(row.get("kaspi_offer_name")),
    ]
    return {value for value in values if value and value != sku_id}


def _product_type_from_order(order: dict[str, Any]) -> str:
    explicit = _clean(order.get("product_type"))
    if explicit:
        return explicit
    sku_key = _clean(order.get("sku_key"))
    if "_" in sku_key:
        return sku_key.split("_", 1)[0]
    return "CL"


def _extract_model(sku_key: str) -> str:
    parts = [part for part in str(sku_key or "").split("_") if part]
    if len(parts) > 3:
        return parts[3]
    return sku_key or "UNKNOWN"


def _extract_color(sku_key: str) -> str | None:
    parts = [part for part in str(sku_key or "").split("_") if part]
    if len(parts) > 4:
        return parts[4]
    return None


def _extract_gender(sku_key: str) -> str | None:
    parts = [part for part in str(sku_key or "").split("_") if part]
    if len(parts) > 2:
        return parts[2]
    return None


def _size_order(size_label: str) -> int | None:
    normalized = _clean_upper(size_label)
    ordered = {
        "XS": 1,
        "S": 2,
        "M": 3,
        "L": 4,
        "XL": 5,
        "2XL": 6,
        "3XL": 7,
        "4XL": 8,
        "5XL": 9,
        "22": 1,
        "24": 2,
        "26": 3,
        "28": 4,
        "30": 5,
        "32": 6,
        "34": 7,
        "36": 8,
        "38": 9,
        "40": 10,
        "42": 11,
        "ONE_SIZE": 99,
    }
    return ordered.get(normalized)


def _normalize_article_key(value: Any) -> str:
    article = _clean_upper(value)
    if not article:
        return ""
    return re.sub(r"_[0-9]{6,}$", "", article)


def _article_suffix_key(value: Any) -> str:
    article = _clean_upper(value)
    if not article or "_" not in article:
        return ""
    suffix = article.rsplit("_", 1)[-1]
    if suffix.isdigit() and len(suffix) >= 6:
        return f"_{suffix}"
    return ""


def _load_article_identity_map(
    conn: sqlite3.Connection,
    orders: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, str]]:
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dim_kaspi_article_map'"
    ).fetchone()
    if not has_table:
        return {}

    store_codes = sorted({_clean_upper(order.get("store_code")) for order in orders if _clean(order.get("store_code"))})
    if not store_codes:
        return {}

    placeholders = ",".join("?" for _ in store_codes)
    rows = conn.execute(
        f"""
        SELECT store_code, kaspi_article, sku_key, sku_id, kaspi_offer_name
        FROM dim_kaspi_article_map
        WHERE UPPER(COALESCE(store_code, '')) IN ({placeholders})
        """,
        store_codes,
    ).fetchall()

    article_map: dict[tuple[str, str], dict[str, str]] = {}
    ambiguous: set[tuple[str, str]] = set()

    def _store_mapping(key: tuple[str, str], value: dict[str, str]) -> None:
        if not key[0] or not key[1]:
            return
        if key in ambiguous:
            return
        if key in article_map and article_map[key] != value:
            article_map.pop(key, None)
            ambiguous.add(key)
            return
        article_map[key] = value

    for row in rows:
        store_code = _clean_upper(row["store_code"])
        exact_article = _clean_upper(row["kaspi_article"])
        normalized_article = _normalize_article_key(row["kaspi_article"])
        suffix_article = _article_suffix_key(row["kaspi_article"])
        value = {
            "sku_key": _clean(row["sku_key"]),
            "sku_id": _clean(row["sku_id"]),
            "kaspi_offer_name": _clean(row["kaspi_offer_name"]),
        }
        _store_mapping((store_code, exact_article), value)
        _store_mapping((store_code, normalized_article), value)
        _store_mapping((store_code, suffix_article), value)
    return article_map


def _canonicalize_parsed_orders(
    orders: list[dict[str, Any]],
    article_map: dict[tuple[str, str], dict[str, str]],
) -> tuple[list[dict[str, Any]], int]:
    canonicalized: list[dict[str, Any]] = []
    overrides = 0
    for order in orders:
        store_code = _clean_upper(order.get("store_code"))
        exact_article = _clean_upper(order.get("kaspi_article"))
        normalized_article = _normalize_article_key(order.get("kaspi_article"))
        suffix_article = _article_suffix_key(order.get("kaspi_article"))
        mapping = (
            article_map.get((store_code, exact_article))
            or article_map.get((store_code, normalized_article))
            or article_map.get((store_code, suffix_article))
        )
        if not mapping:
            canonicalized.append(order)
            continue

        mapped_sku_key = _clean(mapping.get("sku_key"))
        mapped_sku_id = _clean(mapping.get("sku_id"))
        mapped_offer_name = _clean(mapping.get("kaspi_offer_name"))
        mapped_size = normalize_size(_clean(order.get("my_size"))) if _clean(order.get("my_size")) else None

        updated = dict(order)
        changed = False
        if mapped_sku_key and mapped_sku_key != _clean(order.get("sku_key")):
            updated["sku_key"] = mapped_sku_key
            changed = True
        if mapped_sku_id:
            if mapped_sku_id != _clean(order.get("sku_id")):
                updated["sku_id"] = mapped_sku_id
                changed = True
            if not mapped_size:
                suffix_size = normalize_size(mapped_sku_id.rsplit("_", 1)[-1]) if "_" in mapped_sku_id else None
                if suffix_size:
                    updated["my_size"] = suffix_size
        elif mapped_sku_key and mapped_size:
            canonical_sku_id = f"{mapped_sku_key}_{mapped_size}"
            if canonical_sku_id != _clean(order.get("sku_id")):
                updated["sku_id"] = canonical_sku_id
                changed = True
        if mapped_offer_name and not _clean(order.get("kaspi_offer_name")):
            updated["kaspi_offer_name"] = mapped_offer_name
            changed = True
        if mapped_size and mapped_size != _clean(order.get("my_size")):
            updated["my_size"] = mapped_size
            changed = True

        if changed:
            overrides += 1
        canonicalized.append(updated)
    return canonicalized, overrides


def _identity_sort_key(order: dict[str, Any]) -> tuple[str, str]:
    return (_clean(order.get("sku_id")), _clean(order.get("kaspi_offer_name")))


def _candidate_match_score(candidate: dict[str, Any], order: dict[str, Any]) -> tuple[int, int, int, int]:
    line_match = int(bool(_public_line_identity_candidates(candidate) & _public_line_identity_candidates(order)))
    candidate_sku = _clean(candidate.get("sku_id"))
    order_sku = _clean(order.get("sku_id"))
    candidate_offer = _clean(candidate.get("kaspi_offer_name"))
    order_offer = _clean(order.get("kaspi_offer_name"))
    sku_match = int(bool(order_sku) and candidate_sku == order_sku)
    offer_match = int(bool(order_offer) and candidate_offer == order_offer)
    blank_identity = int(not candidate_sku and not candidate_offer)
    return (-line_match, -sku_match, -offer_match, -blank_identity)


def _build_output_path(output_json: Path | None, target_date: date) -> Path:
    if output_json is not None:
        return output_json
    stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_ROOT / target_date.isoformat() / f"enrich_kaspi_orders_from_activeorders_{stamp}.json"


def dump_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_activeorders_enrich_{stamp}.sqlite"
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


def _filter_parsed_orders(orders: list[dict[str, Any]], *, target_date: date) -> list[dict[str, Any]]:
    target_iso = target_date.isoformat()
    filtered: list[dict[str, Any]] = []
    for order in orders:
        if _clean_upper(order.get("internal_status")) != "READY":
            continue
        planned = _clean(order.get("planned_shipment_date"))
        if not planned or planned > target_iso:
            continue
        filtered.append(order)
    return filtered


def _load_candidate_rows(conn: sqlite3.Connection, orders: list[dict[str, Any]], *, target_date: date, lookback_days: int) -> list[dict[str, Any]]:
    order_ids = sorted({_clean(order.get("order_id")) for order in orders if _clean(order.get("order_id"))})
    if not order_ids:
        return []
    columns = _table_columns(conn, "fact_orders_kaspi")
    kaspi_article_expr = "kaspi_article" if "kaspi_article" in columns else "'' AS kaspi_article"
    line_identity_expr = "line_identity_key" if "line_identity_key" in columns else "'' AS line_identity_key"
    placeholders = ",".join("?" for _ in order_ids)
    start_date = (target_date - timedelta(days=max(lookback_days - 1, 0))).isoformat()
    sql = f"""
        SELECT
            id,
            order_id,
            store_code,
            channel_code,
            kaspi_offer_name,
            {kaspi_article_expr},
            {line_identity_expr},
            sku_key,
            sku_id,
            my_size,
            assigned_size,
            quantity,
            unit_price_kzt,
            created_at,
            planned_shipment_date,
            actual_shipment_date,
            kaspi_status,
            internal_status,
            status_updated_at,
            waybill_url,
            waybill_number,
            waybill_downloaded,
            source,
            source_file,
            kaspi_status_detail,
            planned_delivery_date,
            courier_transmission_planning_date,
            courier_transmission_date,
            delivery_mode,
            payment_mode,
            signature_required,
            credit_term,
            pre_order,
            approved_by_bank_date,
            reservation_date,
            delivery_cost,
            delivery_cost_for_seller,
            delivery_address,
            is_imei_required,
            express,
            returned_to_warehouse,
            category,
            customer_first_name,
            customer_last_name,
            customer_phone,
            customer_height_cm,
            customer_weight_kg
        FROM fact_orders_kaspi
        WHERE order_id IN ({placeholders})
          AND planned_shipment_date BETWEEN ? AND ?
          AND COALESCE(actual_shipment_date, '') = ''
    """
    params = [*order_ids, start_date, target_date.isoformat()]
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _match_group_updates(
    parsed_group: list[dict[str, Any]],
    candidate_group: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    updates: list[dict[str, Any]] = []
    inserts: list[dict[str, Any]] = []
    remaining_candidates = list(candidate_group)
    template_row = candidate_group[0] if candidate_group else {}

    for order in sorted(parsed_group, key=_identity_sort_key):
        matched_idx = None
        for idx, candidate in enumerate(sorted(remaining_candidates, key=lambda row: (_candidate_match_score(row, order), int(row["id"])))):
            candidate_public_lines = _public_line_identity_candidates(candidate)
            order_public_lines = _public_line_identity_candidates(order)
            line_match = bool(candidate_public_lines & order_public_lines)
            line_conflict = bool(candidate_public_lines and order_public_lines and not line_match)
            sku_match = _clean(candidate.get("sku_id")) == _clean(order.get("sku_id")) and _clean(order.get("sku_id"))
            offer_match = _clean(candidate.get("kaspi_offer_name")) == _clean(order.get("kaspi_offer_name")) and _clean(order.get("kaspi_offer_name"))
            blank_identity = not _clean(candidate.get("sku_id")) and not _clean(candidate.get("kaspi_offer_name"))
            if line_match or (not line_conflict and (sku_match or offer_match or blank_identity)):
                matched_idx = remaining_candidates.index(candidate)
                break
        if matched_idx is not None:
            candidate = remaining_candidates.pop(matched_idx)
            updates.append(
                {
                    "id": int(candidate["id"]),
                    "order": order,
                    "candidate": candidate,
                }
            )
            continue
        inserts.append({"order": order, "template": template_row})
    return updates, inserts


def plan_activeorders_enrichment(
    *,
    parsed_orders: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    parsed_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for order in parsed_orders:
        parsed_by_group[(_clean(order.get("order_id")), _clean(order.get("store_code")))].append(order)

    candidates_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        candidates_by_group[(_clean(row.get("order_id")), _clean(row.get("store_code")))].append(row)

    updates: list[dict[str, Any]] = []
    inserts: list[dict[str, Any]] = []
    unmatched_db_groups: list[dict[str, Any]] = []
    for group_key, parsed_group in parsed_by_group.items():
        candidate_group = candidates_by_group.get(group_key, [])
        matched_updates, matched_inserts = _match_group_updates(parsed_group, candidate_group)
        updates.extend(matched_updates)
        inserts.extend(matched_inserts)
        if len(candidate_group) > len(parsed_group):
            unmatched_db_groups.append(
                {
                    "group_key": group_key,
                    "candidate_rows": len(candidate_group),
                    "parsed_rows": len(parsed_group),
                }
            )

    return {
        "updates": updates,
        "inserts": inserts,
        "unmatched_db_groups": unmatched_db_groups,
    }


def _ensure_dim_sku(conn: sqlite3.Connection, sku_key: str, *, product_type: str) -> bool:
    if not sku_key:
        return False
    existing = conn.execute("SELECT 1 FROM dim_sku WHERE sku_key = ?", (sku_key,)).fetchone()
    if existing:
        return False
    conn.execute(
        """
        INSERT INTO dim_sku (
            sku_key, model, color, product_type, base_cost_cny, weight_kg, category, gender
        ) VALUES (?, ?, ?, ?, 0, 0, NULL, ?)
        """,
        (
            sku_key,
            _extract_model(sku_key),
            _extract_color(sku_key),
            product_type or "CL",
            _extract_gender(sku_key),
        ),
    )
    return True


def _ensure_dim_sku_size(conn: sqlite3.Connection, sku_id: str, sku_key: str, size_label: str) -> bool:
    if not sku_id or not sku_key or not size_label:
        return False
    existing = conn.execute("SELECT 1 FROM dim_sku_size WHERE sku_id = ?", (sku_id,)).fetchone()
    if existing:
        return False
    conn.execute(
        """
        INSERT INTO dim_sku_size (sku_id, sku_key, my_size, size_order)
        VALUES (?, ?, ?, ?)
        """,
        (sku_id, sku_key, size_label, _size_order(size_label)),
    )
    return True


def _apply_updates(conn: sqlite3.Connection, updates: list[dict[str, Any]], source_file: str) -> int:
    applied = 0
    columns = _table_columns(conn, "fact_orders_kaspi")
    for update in updates:
        order = update["order"]
        candidate = update["candidate"]
        assignments: list[tuple[str, Any]] = [
            ("kaspi_offer_name", _clean(order.get("kaspi_offer_name")) or candidate.get("kaspi_offer_name")),
            ("sku_key", _clean(order.get("sku_key")) or candidate.get("sku_key")),
            ("sku_id", _clean(order.get("sku_id")) or candidate.get("sku_id")),
            ("quantity", _safe_int(order.get("quantity"), default=_safe_int(candidate.get("quantity"), 1))),
            (
                "unit_price_kzt",
                order.get("unit_price_kzt")
                if order.get("unit_price_kzt") not in ("", None)
                else candidate.get("unit_price_kzt"),
            ),
            ("planned_shipment_date", _clean(order.get("planned_shipment_date")) or candidate.get("planned_shipment_date")),
            ("source_file", source_file),
        ]
        if "kaspi_article" in columns:
            assignments.append(("kaspi_article", _clean(order.get("kaspi_article")) or candidate.get("kaspi_article")))
        if "line_identity_key" in columns:
            assignments.append(("line_identity_key", _line_identity_key(order) or candidate.get("line_identity_key") or ""))
        assignments = [(column, value) for column, value in assignments if column in columns]
        set_sql = ",\n                ".join(f"{column} = ?" for column, _value in assignments)
        values = [value for _column, value in assignments]
        if "updated_at" in columns:
            set_sql += ",\n                updated_at = CURRENT_TIMESTAMP"
        conn.execute(
            f"""
            UPDATE fact_orders_kaspi
            SET {set_sql}
            WHERE id = ?
            """,
            (*values, int(candidate["id"])),
        )
        applied += 1
    return applied


def _insert_from_template(conn: sqlite3.Connection, inserts: list[dict[str, Any]], source_file: str) -> int:
    applied = 0
    columns = _table_columns(conn, "fact_orders_kaspi")
    if "line_identity_key" in columns:
        if not _has_unique_index(conn, "fact_orders_kaspi", LINE_GRAIN_CONFLICT_COLUMNS):
            raise RuntimeError(
                "fact_orders_kaspi has line_identity_key but is missing the line-grain unique key; "
                "run scripts/migrate_030_fact_orders_kaspi_line_grain.py"
            )
        conflict_columns = LINE_GRAIN_CONFLICT_COLUMNS
    elif _has_unique_index(conn, "fact_orders_kaspi", LEGACY_CONFLICT_COLUMNS):
        conflict_columns = LEGACY_CONFLICT_COLUMNS
    else:
        conflict_columns = ()

    preferred_columns = [
        "order_id",
        "store_code",
        "channel_code",
        "kaspi_offer_name",
        "kaspi_article",
        "line_identity_key",
        "sku_key",
        "sku_id",
        "my_size",
        "quantity",
        "unit_price_kzt",
        "created_at",
        "planned_shipment_date",
        "actual_shipment_date",
        "kaspi_status",
        "internal_status",
        "status_updated_at",
        "waybill_url",
        "waybill_number",
        "waybill_downloaded",
        "source",
        "source_file",
        "assigned_size",
        "size_source",
        "size_confidence",
        "customer_height_cm",
        "customer_weight_kg",
        "kaspi_status_detail",
        "planned_delivery_date",
        "courier_transmission_planning_date",
        "courier_transmission_date",
        "delivery_mode",
        "payment_mode",
        "signature_required",
        "credit_term",
        "pre_order",
        "approved_by_bank_date",
        "reservation_date",
        "delivery_cost",
        "delivery_cost_for_seller",
        "delivery_address",
        "is_imei_required",
        "express",
        "returned_to_warehouse",
        "category",
        "customer_first_name",
        "customer_last_name",
        "customer_phone",
    ]
    for item in inserts:
        order = item["order"]
        template = dict(item.get("template") or {})
        row_data = {
            "order_id": _clean(order.get("order_id")),
            "store_code": _clean(order.get("store_code")) or _clean(template.get("store_code")),
            "channel_code": _clean(template.get("channel_code")) or "KSP",
            "kaspi_offer_name": _clean(order.get("kaspi_offer_name")),
            "kaspi_article": _clean(order.get("kaspi_article")) or _clean(template.get("kaspi_article")),
            "line_identity_key": _line_identity_key(order) or _clean(template.get("line_identity_key")),
            "sku_key": _clean(order.get("sku_key")),
            "sku_id": _clean(order.get("sku_id")),
            "my_size": None,
            "quantity": _safe_int(order.get("quantity"), default=1),
            "unit_price_kzt": (
                order.get("unit_price_kzt")
                if order.get("unit_price_kzt") not in ("", None)
                else template.get("unit_price_kzt")
            ),
            "created_at": _clean(order.get("created_at")) or template.get("created_at"),
            "planned_shipment_date": _clean(order.get("planned_shipment_date")) or template.get("planned_shipment_date"),
            "actual_shipment_date": template.get("actual_shipment_date"),
            "kaspi_status": _clean(template.get("kaspi_status")) or "KASPI_DELIVERY",
            "internal_status": _clean(template.get("internal_status")) or "ACCEPTED",
            "status_updated_at": template.get("status_updated_at"),
            "waybill_url": template.get("waybill_url"),
            "waybill_number": template.get("waybill_number"),
            "waybill_downloaded": _safe_int(template.get("waybill_downloaded"), default=0),
            "source": _clean(template.get("source")) or "ACTIVEORDERS_ENRICH",
            "source_file": source_file,
            "assigned_size": None,
            "size_source": None,
            "size_confidence": None,
            "customer_height_cm": template.get("customer_height_cm"),
            "customer_weight_kg": template.get("customer_weight_kg"),
            "kaspi_status_detail": template.get("kaspi_status_detail"),
            "planned_delivery_date": template.get("planned_delivery_date"),
            "courier_transmission_planning_date": template.get("courier_transmission_planning_date"),
            "courier_transmission_date": template.get("courier_transmission_date"),
            "delivery_mode": template.get("delivery_mode"),
            "payment_mode": template.get("payment_mode"),
            "signature_required": template.get("signature_required"),
            "credit_term": template.get("credit_term"),
            "pre_order": template.get("pre_order"),
            "approved_by_bank_date": template.get("approved_by_bank_date"),
            "reservation_date": template.get("reservation_date"),
            "delivery_cost": template.get("delivery_cost"),
            "delivery_cost_for_seller": template.get("delivery_cost_for_seller"),
            "delivery_address": template.get("delivery_address"),
            "is_imei_required": template.get("is_imei_required"),
            "express": template.get("express"),
            "returned_to_warehouse": template.get("returned_to_warehouse"),
            "category": template.get("category"),
            "customer_first_name": template.get("customer_first_name"),
            "customer_last_name": template.get("customer_last_name"),
            "customer_phone": template.get("customer_phone"),
        }
        insert_columns = [column for column in preferred_columns if column in columns]
        placeholders = ", ".join("?" for _column in insert_columns)
        insert_sql = ", ".join(insert_columns)
        values = [row_data.get(column) for column in insert_columns]
        conflict_sql = ""
        if conflict_columns:
            conflict_target = ", ".join(conflict_columns)
            update_assignments: list[str] = []
            if "channel_code" in insert_columns:
                update_assignments.append(
                    "channel_code = COALESCE(NULLIF(excluded.channel_code, ''), fact_orders_kaspi.channel_code)"
                )
            if "kaspi_offer_name" in insert_columns:
                update_assignments.append(
                    "kaspi_offer_name = COALESCE(NULLIF(excluded.kaspi_offer_name, ''), fact_orders_kaspi.kaspi_offer_name)"
                )
            if "sku_key" in insert_columns:
                update_assignments.append("sku_key = COALESCE(NULLIF(excluded.sku_key, ''), fact_orders_kaspi.sku_key)")
            if "quantity" in insert_columns:
                update_assignments.append("quantity = COALESCE(excluded.quantity, fact_orders_kaspi.quantity)")
            if "unit_price_kzt" in insert_columns:
                update_assignments.append(
                    "unit_price_kzt = COALESCE(excluded.unit_price_kzt, fact_orders_kaspi.unit_price_kzt)"
                )
            if "planned_shipment_date" in insert_columns:
                update_assignments.append(
                    "planned_shipment_date = COALESCE(NULLIF(excluded.planned_shipment_date, ''), fact_orders_kaspi.planned_shipment_date)"
                )
            if "source_file" in insert_columns:
                update_assignments.append(
                    "source_file = COALESCE(NULLIF(excluded.source_file, ''), fact_orders_kaspi.source_file)"
                )
            if "kaspi_article" in insert_columns:
                update_assignments.append(
                    "kaspi_article = COALESCE(NULLIF(excluded.kaspi_article, ''), fact_orders_kaspi.kaspi_article)"
                )
            if "line_identity_key" in insert_columns:
                update_assignments.append(
                    "line_identity_key = COALESCE(NULLIF(excluded.line_identity_key, ''), fact_orders_kaspi.line_identity_key)"
                )
            if "updated_at" in columns:
                update_assignments.append("updated_at = CURRENT_TIMESTAMP")
            conflict_sql = (
                f" ON CONFLICT({conflict_target}) DO UPDATE SET "
                + ", ".join(update_assignments)
            )
        conn.execute(
            f"INSERT INTO fact_orders_kaspi ({insert_sql}) VALUES ({placeholders}){conflict_sql}",
            values,
        )
        applied += 1
    return applied


def _summarize_orders(orders: list[dict[str, Any]]) -> dict[str, Any]:
    store_counts: dict[str, int] = defaultdict(int)
    for order in orders:
        store_counts[_clean(order.get("store_code"))] += 1
    return {
        "rows": len(orders),
        "orders": len({_clean(order.get("order_id")) for order in orders if _clean(order.get("order_id"))}),
        "stores": dict(sorted(store_counts.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enrich current pending fact_orders_kaspi rows from ActiveOrders.xlsx.")
    parser.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: db/app.db)")
    parser.add_argument("--file", type=Path, default=DEFAULT_EXPORT_PATH, help="Path to ActiveOrders.xlsx")
    parser.add_argument("--target-date", type=str, default="today", help="Target date (default: today)")
    parser.add_argument("--lookback-days", type=int, default=5, help="Lookback window for matching DB rows")
    parser.add_argument("--apply", action="store_true", help="Apply DB enrichment writes")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT, help="Backup directory for --apply")
    parser.add_argument("--output-json", type=Path, default=None, help="Optional JSON report path")
    args = parser.parse_args(argv)

    _require_apply_gate(args.apply)
    target = _resolve_target_date(args.target_date)
    db_path = Path(args.db).expanduser() if args.db else data_path("db", "app.db")
    export_path = Path(args.file).expanduser()
    if not export_path.exists():
        raise RuntimeError(f"ActiveOrders export not found: {export_path}")

    parse_result = parse_active_orders(export_path)
    parsed_orders = _filter_parsed_orders(parse_result.orders, target_date=target)

    with get_db(db_path) as conn:
        article_identity_map = _load_article_identity_map(conn, parsed_orders)
        parsed_orders, article_map_override_count = _canonicalize_parsed_orders(parsed_orders, article_identity_map)
        candidate_rows = _load_candidate_rows(conn, parsed_orders, target_date=target, lookback_days=args.lookback_days)
        plan = plan_activeorders_enrichment(parsed_orders=parsed_orders, candidate_rows=candidate_rows)

    report: dict[str, Any] = {
        "db_path": str(db_path),
        "activeorders_file": str(export_path),
        "target_date": target.isoformat(),
        "lookback_days": args.lookback_days,
        "parsed_summary": _summarize_orders(parse_result.orders),
        "filtered_summary": _summarize_orders(parsed_orders),
        "candidate_rows": len(candidate_rows),
        "updates_planned": len(plan["updates"]),
        "inserts_planned": len(plan["inserts"]),
        "unmatched_db_groups": plan["unmatched_db_groups"],
        "article_map_overrides": article_map_override_count,
        "apply": args.apply,
    }

    if args.apply:
        backup_path = _backup_db(db_path, Path(args.backup_root).expanduser())
        report["db_backup_path"] = str(backup_path)
        with get_db(db_path) as conn:
            created_sku_keys = 0
            created_sku_ids = 0
            for item in [*plan["updates"], *plan["inserts"]]:
                order = item["order"]
                product_type = _product_type_from_order(order)
                if _ensure_dim_sku(conn, _clean(order.get("sku_key")), product_type=product_type):
                    created_sku_keys += 1
                if _ensure_dim_sku_size(
                    conn,
                    _clean(order.get("sku_id")),
                    _clean(order.get("sku_key")),
                    _clean(order.get("my_size")),
                ):
                    created_sku_ids += 1
            updates_applied = _apply_updates(conn, plan["updates"], source_file=str(export_path))
            inserts_applied = _insert_from_template(conn, plan["inserts"], source_file=str(export_path))
        report["created_sku_keys"] = created_sku_keys
        report["created_sku_ids"] = created_sku_ids
        report["updates_applied"] = updates_applied
        report["inserts_applied"] = inserts_applied
    else:
        with get_db(db_path) as conn:
            article_identity_map = _load_article_identity_map(conn, parsed_orders)
        parsed_orders, article_map_override_count = _canonicalize_parsed_orders(parsed_orders, article_identity_map)
        report["filtered_summary"] = _summarize_orders(parsed_orders)
        with get_db(db_path) as conn:
            candidate_rows = _load_candidate_rows(conn, parsed_orders, target_date=target, lookback_days=args.lookback_days)
        plan = plan_activeorders_enrichment(parsed_orders=parsed_orders, candidate_rows=candidate_rows)
        report["candidate_rows"] = len(candidate_rows)
        report["updates_planned"] = len(plan["updates"])
        report["inserts_planned"] = len(plan["inserts"])
        report["unmatched_db_groups"] = plan["unmatched_db_groups"]
        report["db_backup_path"] = None
        report["created_sku_keys"] = 0
        report["created_sku_ids"] = 0
        report["updates_applied"] = 0
        report["inserts_applied"] = 0

    output_path = _build_output_path(args.output_json, target)
    dump_json(output_path, report)
    print(f"ActiveOrders DB enrichment report: {output_path}")
    print(f"Parsed rows: {report['parsed_summary']['rows']}")
    print(f"Filtered rows: {report['filtered_summary']['rows']}")
    print(f"Planned updates: {report['updates_planned']}")
    print(f"Planned inserts: {report['inserts_planned']}")
    if args.apply:
        print(f"DB backup: {report['db_backup_path']}")
        print(f"Applied updates: {report['updates_applied']}")
        print(f"Applied inserts: {report['inserts_applied']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
