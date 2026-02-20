"""Kaspi order enrichment (order entries + cached lookup tables)."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import yaml

from core.integrations.kaspi_api_client import KaspiAPIClient
from core.integrations.kaspi_order_stage import StageCode, classify_kaspi_order_stage

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "kaspi_enrichment.yaml"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _load_config(path: Path) -> dict:
    defaults = {
        "enabled": False,
        "stores_allowlist": [],
        "fetch_entries": True,
        "fetch_entry_detail": False,
        "fetch_entry_product": False,
        "fetch_masterproduct": False,
        "fetch_merchantproduct": False,
        "fetch_point_of_service": False,
        "max_orders_per_run": 200,
    }
    if not path.exists():
        return defaults
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return defaults
    merged = {**defaults, **data}
    return merged


def _select_orders(
    conn: sqlite3.Connection,
    store_code: str,
    since: str,
    until: str,
    max_orders: int,
) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT
            order_id,
            store_code,
            kaspi_status,
            kaspi_status_detail,
            signature_required,
            pre_order,
            courier_transmission_date,
            actual_shipment_date,
            delivery_mode,
            returned_to_warehouse
        FROM fact_orders_kaspi
        WHERE store_code = ?
          AND date(COALESCE(status_updated_at, actual_shipment_date, planned_shipment_date, created_at))
              BETWEEN ? AND ?
        ORDER BY status_updated_at DESC
        LIMIT ?
        """,
        (store_code, since, until, max_orders),
    ).fetchall()
    selected: list[tuple[str, str]] = []
    for row in rows:
        order = {
            "state": row["kaspi_status"],
            "status": row["kaspi_status_detail"],
            "signatureRequired": row["signature_required"],
            "preOrder": row["pre_order"],
            "courierTransmissionDate": row["courier_transmission_date"] or row["actual_shipment_date"],
            "deliveryMode": row["delivery_mode"],
            "returnedToWarehouse": row["returned_to_warehouse"],
        }
        stage = classify_kaspi_order_stage(order)
        if stage in {StageCode.SIGN_REQUIRED, StageCode.UNKNOWN}:
            continue
        selected.append((row["order_id"], row["store_code"]))
    return selected


def _parse_entry(entry: dict, fallback_order_id: str, store_code: str) -> dict:
    attributes = entry.get("attributes") or {}
    relationships = entry.get("relationships") or {}
    order_rel = (relationships.get("order") or {}).get("data") or {}
    product_rel = (relationships.get("product") or {}).get("data") or {}
    pos_rel = (relationships.get("pointOfService") or {}).get("data") or {}
    entry_id = entry.get("id") or ""
    return {
        "entry_id": entry_id,
        "order_id": order_rel.get("id") or fallback_order_id,
        "store_code": store_code,
        "product_id": product_rel.get("id"),
        "offer_id": attributes.get("offerId"),
        "quantity": float(attributes.get("quantity") or 0.0),
        "unit_price_kzt": float(attributes.get("price") or 0.0),
        "total_price_kzt": float(attributes.get("totalPrice") or 0.0),
        "point_of_service_id": pos_rel.get("id"),
        "raw_json": json.dumps(entry, ensure_ascii=False),
    }


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_entry_detail(entry_detail: dict) -> dict:
    attributes = entry_detail.get("attributes") or {}
    relationships = entry_detail.get("relationships") or {}
    category = attributes.get("category") or {}
    delivery_pos_rel = (relationships.get("deliveryPointOfService") or {}).get("data") or {}
    return {
        "unit_type": attributes.get("unitType"),
        "min_allowed_weight": _coerce_float(attributes.get("minAllowedWeight")),
        "weight_kg": _coerce_float(attributes.get("weight")),
        "entry_number": _coerce_int(attributes.get("entryNumber")),
        "category_code": category.get("code"),
        "category_title": category.get("title"),
        "delivery_cost_kzt": _coerce_float(attributes.get("deliveryCost")),
        "base_price_kzt": _coerce_float(attributes.get("basePrice")),
        "delivery_point_of_service_id": delivery_pos_rel.get("id"),
    }


def _upsert_dim(conn: sqlite3.Connection, table: str, key: str, store_code: str | None, payload: dict) -> bool:
    raw_json = json.dumps(payload, ensure_ascii=False)
    if table == "dim_point_of_service":
        conn.execute(
            """
            INSERT OR IGNORE INTO dim_point_of_service (pos_id, store_code, raw_json)
            VALUES (?, ?, ?)
            """,
            (key, store_code, raw_json),
        )
    elif table == "dim_masterproduct":
        conn.execute(
            """
            INSERT OR IGNORE INTO dim_masterproduct (masterproduct_id, raw_json)
            VALUES (?, ?)
            """,
            (key, raw_json),
        )
    elif table == "dim_merchantproduct":
        conn.execute(
            """
            INSERT OR IGNORE INTO dim_merchantproduct (merchantproduct_id, masterproduct_id, raw_json)
            VALUES (?, ?, ?)
            """,
            (payload.get("id"), payload.get("masterproduct_id"), raw_json),
        )
    else:
        return False
    return True


def enrich_orders(
    db_path: Path,
    store_code: str,
    since: str,
    until: str,
    apply: bool = False,
    config_path: Path = DEFAULT_CONFIG,
    client_factory: Callable[[str], KaspiAPIClient] = KaspiAPIClient,
) -> dict:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    config = _load_config(config_path)
    if not config.get("enabled"):
        logger.info("Kaspi enrichment disabled in config.")
        return {"enabled": False, "inserted": 0, "skipped": 0}

    allowlist = [
        str(store).upper()
        for store in (config.get("stores_allowlist") or [])
        if str(store).strip()
    ]
    if allowlist and store_code.upper() not in allowlist:
        logger.info("Kaspi enrichment skipped for %s (not in allowlist).", store_code)
        return {"enabled": True, "inserted": 0, "skipped": 0}

    if apply and os.environ.get("ENABLE_KASPI_ENRICHMENT") != "1":
        raise RuntimeError("ENABLE_KASPI_ENRICHMENT=1 is required to apply enrichment writes.")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        for required in (
            "fact_orders_kaspi",
            "fact_order_entries_kaspi",
            "dim_point_of_service",
            "dim_masterproduct",
            "dim_merchantproduct",
        ):
            if not _table_exists(conn, required):
                raise RuntimeError(f"Missing table: {required}. Run migrate_019_kaspi_enrichment.py")

        orders = _select_orders(
            conn,
            store_code=store_code,
            since=since,
            until=until,
            max_orders=int(config.get("max_orders_per_run") or 0) or 0,
        )
        if not orders:
            return {"enabled": True, "inserted": 0, "skipped": 0}

        client = client_factory(store_code)
        seen_masterproduct_ids: set[str] = set()
        seen_merchantproduct_ids: set[str] = set()
        seen_pos_ids: set[str] = set()
        inserted = 0
        skipped = 0
        for order_id, order_store in orders:
            try:
                if not config.get("fetch_entries", True):
                    continue
                response = client.get_order_entries(order_id)
                if not getattr(response, "success", False):
                    logger.warning("Order entries fetch failed for %s", order_id)
                    continue
                entries = (response.data or {}).get("data") or []
            except Exception as exc:
                logger.warning("Order entries error for %s: %s", order_id, exc)
                continue

            for entry in entries:
                parsed = _parse_entry(entry, order_id, order_store)
                if not parsed.get("entry_id"):
                    skipped += 1
                    continue

                if config.get("fetch_entry_detail") and parsed.get("entry_id"):
                    try:
                        resp = client.get_order_entry(parsed["entry_id"])
                        if getattr(resp, "success", False):
                            data = (resp.data or {}).get("data") or {}
                            parsed.update(_parse_entry_detail(data))
                    except Exception as exc:
                        logger.warning("orderentry detail fetch failed: %s", exc)
                if apply:
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO fact_order_entries_kaspi (
                            entry_id, order_id, store_code, product_id, offer_id,
                            quantity, unit_price_kzt, total_price_kzt,
                            unit_type, min_allowed_weight, weight_kg, entry_number,
                            category_code, category_title, delivery_cost_kzt, base_price_kzt,
                            point_of_service_id, delivery_point_of_service_id,
                            raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            parsed["entry_id"],
                            parsed["order_id"],
                            parsed["store_code"],
                            parsed["product_id"],
                            parsed["offer_id"],
                            parsed["quantity"],
                            parsed["unit_price_kzt"],
                            parsed["total_price_kzt"],
                            parsed.get("unit_type"),
                            parsed.get("min_allowed_weight"),
                            parsed.get("weight_kg"),
                            parsed.get("entry_number"),
                            parsed.get("category_code"),
                            parsed.get("category_title"),
                            parsed.get("delivery_cost_kzt"),
                            parsed.get("base_price_kzt"),
                            parsed.get("point_of_service_id"),
                            parsed.get("delivery_point_of_service_id"),
                            parsed["raw_json"],
                        ),
                    )
                    if cur.rowcount and cur.rowcount > 0:
                        inserted += cur.rowcount
                    else:
                        skipped += 1
                else:
                    inserted += 1

                if not apply:
                    continue

                if config.get("fetch_entry_product") and parsed.get("entry_id"):
                    try:
                        resp = client.get_order_entry_product(parsed["entry_id"])
                        if getattr(resp, "success", False):
                            data = (resp.data or {}).get("data") or {}
                            master_id = data.get("id")
                            if master_id:
                                _upsert_dim(conn, "dim_masterproduct", master_id, None, data)
                    except Exception as exc:
                        logger.warning("orderentry product fetch failed: %s", exc)

                if config.get("fetch_masterproduct") and parsed.get("product_id"):
                    master_id = parsed["product_id"]
                    if master_id and master_id not in seen_masterproduct_ids:
                        try:
                            resp = client.get_masterproduct(master_id)
                            if getattr(resp, "success", False):
                                data = (resp.data or {}).get("data") or {}
                                master_id = data.get("id")
                                if master_id:
                                    _upsert_dim(conn, "dim_masterproduct", master_id, None, data)
                                    seen_masterproduct_ids.add(master_id)
                        except Exception as exc:
                            logger.warning("masterproduct fetch failed: %s", exc)

                if config.get("fetch_merchantproduct") and parsed.get("product_id"):
                    master_id = parsed.get("product_id")
                    if master_id and master_id not in seen_merchantproduct_ids:
                        try:
                            resp = client.get_merchantproduct(master_id)
                            if getattr(resp, "success", False):
                                data = (resp.data or {}).get("data") or {}
                                merchant_id = data.get("id")
                                if merchant_id:
                                    payload = dict(data)
                                    payload["masterproduct_id"] = master_id
                                    _upsert_dim(conn, "dim_merchantproduct", merchant_id, None, payload)
                                    seen_merchantproduct_ids.add(master_id)
                        except Exception as exc:
                            logger.warning("merchantproduct fetch failed: %s", exc)

                if config.get("fetch_point_of_service"):
                    for pos_id in (
                        parsed.get("point_of_service_id"),
                        parsed.get("delivery_point_of_service_id"),
                    ):
                        if pos_id and pos_id not in seen_pos_ids:
                            try:
                                resp = client.get_point_of_service(pos_id)
                                if getattr(resp, "success", False):
                                    data = (resp.data or {}).get("data") or {}
                                    _upsert_dim(conn, "dim_point_of_service", pos_id, order_store, data)
                                    seen_pos_ids.add(pos_id)
                            except Exception as exc:
                                logger.warning("point of service fetch failed: %s", exc)

        if apply:
            conn.commit()

    return {"enabled": True, "inserted": inserted, "skipped": skipped}
