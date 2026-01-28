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
        "fetch_entries": True,
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
        SELECT order_id, store_code
        FROM fact_orders_kaspi
        WHERE store_code = ?
          AND date(COALESCE(status_updated_at, actual_shipment_date, planned_shipment_date, created_at))
              BETWEEN ? AND ?
        ORDER BY status_updated_at DESC
        LIMIT ?
        """,
        (store_code, since, until, max_orders),
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


def _parse_entry(entry: dict, fallback_order_id: str, store_code: str) -> dict:
    attributes = entry.get("attributes") or {}
    relationships = entry.get("relationships") or {}
    order_rel = (relationships.get("order") or {}).get("data") or {}
    product_rel = (relationships.get("product") or {}).get("data") or {}
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
        "raw_json": json.dumps(entry, ensure_ascii=False),
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
                if apply:
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO fact_order_entries_kaspi (
                            entry_id, order_id, store_code, product_id, offer_id,
                            quantity, unit_price_kzt, total_price_kzt, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        resp = client._request("GET", f"/orderentries/{parsed['entry_id']}/product")
                        if getattr(resp, "success", False):
                            data = (resp.data or {}).get("data") or {}
                            master_id = data.get("id")
                            if master_id:
                                _upsert_dim(conn, "dim_masterproduct", master_id, None, data)
                    except Exception as exc:
                        logger.warning("orderentry product fetch failed: %s", exc)

                if config.get("fetch_masterproduct") and parsed.get("product_id"):
                    try:
                        resp = client._request("GET", f"/masterproducts/{parsed['product_id']}")
                        if getattr(resp, "success", False):
                            data = (resp.data or {}).get("data") or {}
                            master_id = data.get("id")
                            if master_id:
                                _upsert_dim(conn, "dim_masterproduct", master_id, None, data)
                    except Exception as exc:
                        logger.warning("masterproduct fetch failed: %s", exc)

                if config.get("fetch_merchantproduct") and parsed.get("product_id"):
                    try:
                        resp = client._request("GET", f"/masterproducts/{parsed['product_id']}/merchantProduct")
                        if getattr(resp, "success", False):
                            data = (resp.data or {}).get("data") or {}
                            merchant_id = data.get("id")
                            if merchant_id:
                                payload = dict(data)
                                payload["masterproduct_id"] = parsed.get("product_id")
                                _upsert_dim(conn, "dim_merchantproduct", merchant_id, None, payload)
                    except Exception as exc:
                        logger.warning("merchantproduct fetch failed: %s", exc)

                if config.get("fetch_point_of_service"):
                    pos_rel = (entry.get("relationships") or {}).get("pointOfService")
                    pos_id = (pos_rel or {}).get("data", {}).get("id")
                    if pos_id:
                        try:
                            resp = client._request("GET", f"/pointofservices/{pos_id}")
                            if getattr(resp, "success", False):
                                data = (resp.data or {}).get("data") or {}
                                _upsert_dim(conn, "dim_point_of_service", pos_id, order_store, data)
                        except Exception as exc:
                            logger.warning("point of service fetch failed: %s", exc)

        if apply:
            conn.commit()

    return {"enabled": True, "inserted": inserted, "skipped": skipped}
