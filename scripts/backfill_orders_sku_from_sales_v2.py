#!/usr/bin/env python3
"""
Backfill missing SKU identity in fact_orders_kaspi from sales_fact_v2.

Default: DRY RUN. Apply requires ENABLE_ORDER_WRITE=1 and --apply.
Writes a CSV change log to exports/.
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.cashflow.order_status import normalize_order_status
from core.integrations.kaspi_order_stage import classify_kaspi_stage_from_db_row, stage_to_internal_status
from core.utils.sku_normalize import normalize_size

EXPORT_DIR = PROJECT_ROOT / "exports"
DEFAULT_STATUSES = ("COMPLETED", "CANCELLED", "RETURNED", "ON_DELIVERY")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _pick_single(values: Iterable[str]) -> str | None:
    cleaned = [v for v in values if v]
    if len(cleaned) == 1:
        return cleaned[0]
    return None


def _load_order_article_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"CRM article map not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            order_id = _clean(row.get("order_id") or row.get("OrderID") or row.get("№ заказа"))
            article = _clean(row.get("kaspi_article") or row.get("Артикул") or row.get("SKU_ID_KSP"))
            if order_id and article:
                mapping[order_id] = article
    return mapping


def backfill_orders(
    db_path: Path,
    since: date,
    until: date,
    apply: bool = False,
    statuses: Iterable[str] | None = None,
    order_article_map: dict[str, str] | None = None,
    exports_dir: Path | None = None,
) -> dict[str, int]:
    stats = {
        "candidates": 0,
        "updated": 0,
        "unchanged": 0,
        "missing_map": 0,
        "ambiguous": 0,
        "skipped_duplicate": 0,
        "fallback_order_only": 0,
        "fallback_article_map": 0,
        "skipped_status": 0,
    }
    export_dir = exports_dir or EXPORT_DIR
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path = export_dir / f"orders_sku_backfill_{since:%Y%m%d}_{until:%Y%m%d}.csv"

    status_set = {s.strip().upper() for s in (statuses or DEFAULT_STATUSES) if s}

    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, order_id, store_code, sku_key, sku_id, my_size,
                   kaspi_offer_name, internal_status, kaspi_status,
                   kaspi_status_detail, status_updated_at,
                   actual_shipment_date, planned_shipment_date, created_at
            FROM fact_orders_kaspi
            WHERE date(COALESCE(status_updated_at, actual_shipment_date, planned_shipment_date, created_at))
                  BETWEEN ? AND ?
              AND (
                    sku_key IS NULL OR sku_key = ''
                 OR sku_id IS NULL OR sku_id = ''
              )
            """,
            (since.isoformat(), until.isoformat()),
        ).fetchall()

        order_ids = sorted({_clean(order_id) for _, order_id, *_ in rows if _clean(order_id)})
        sales_rows = []
        if order_ids:
            for i in range(0, len(order_ids), 900):
                batch = order_ids[i : i + 900]
                placeholders = ",".join("?" for _ in batch)
                sales_rows.extend(
                    conn.execute(
                        f"""
                        SELECT order_id, store_code, sku_key, sku_id, my_size, kaspi_offer_name
                        FROM sales_fact_v2
                        WHERE order_id IN ({placeholders})
                        """,
                        batch,
                    ).fetchall()
                )

        sales_index: dict[tuple[str, str], dict[str, Any]] = {}
        sales_index_order: dict[str, dict[str, Any]] = {}
        for order_id, store_code, sku_key, sku_id, my_size, offer in sales_rows:
            key = (_clean(order_id), _clean(store_code))
            if not key[0] or not key[1]:
                continue
            entry = sales_index.setdefault(
                key,
                {"sku_keys": set(), "sku_ids": set(), "sizes": set(), "offers": set()},
            )
            entry["sku_keys"].add(_clean(sku_key))
            entry["sku_ids"].add(_clean(sku_id))
            if my_size:
                entry["sizes"].add(_clean(my_size))
            if offer:
                entry["offers"].add(_clean(offer))
            order_key = _clean(order_id)
            order_entry = sales_index_order.setdefault(
                order_key,
                {"sku_keys": set(), "sku_ids": set(), "sizes": set(), "offers": set()},
            )
            order_entry["sku_keys"].add(_clean(sku_key))
            order_entry["sku_ids"].add(_clean(sku_id))
            if my_size:
                order_entry["sizes"].add(_clean(my_size))
            if offer:
                order_entry["offers"].add(_clean(offer))

        sales_unique_order: dict[str, dict[str, Any]] = {}
        for order_key, entry in sales_index_order.items():
            sku_key_val = _pick_single(entry["sku_keys"])
            sku_id_val = _pick_single(entry["sku_ids"])
            if not sku_key_val or not sku_id_val:
                continue
            sales_unique_order[order_key] = {
                "sku_key": sku_key_val,
                "sku_id": sku_id_val,
                "my_size": _pick_single(entry["sizes"]),
                "kaspi_offer_name": _pick_single(entry["offers"]),
            }

        article_map: dict[str, dict[str, str]] = {}
        article_map_store: dict[tuple[str, str], dict[str, str]] = {}
        if order_article_map:
            cols = {
                row[1].strip().lower()
                for row in conn.execute("PRAGMA table_info(dim_kaspi_article_map)")
            }
            has_store = "store_code" in cols
            if has_store:
                article_rows = conn.execute(
                    "SELECT store_code, kaspi_article, sku_key, sku_id FROM dim_kaspi_article_map"
                ).fetchall()
            else:
                article_rows = conn.execute(
                    "SELECT kaspi_article, sku_key, sku_id FROM dim_kaspi_article_map"
                ).fetchall()
            ambiguous = set()
            ambiguous_store = set()
            for row in article_rows:
                if has_store:
                    store_code, kaspi_article, sku_key, sku_id = row
                else:
                    store_code, kaspi_article, sku_key, sku_id = None, row[0], row[1], row[2]
                if not kaspi_article or not sku_key or not sku_id:
                    continue
                if has_store:
                    store_key = (_clean(store_code), _clean(kaspi_article))
                    if store_key in ambiguous_store:
                        continue
                    store_val = {"sku_key": sku_key, "sku_id": sku_id}
                    if store_key in article_map_store and article_map_store[store_key] != store_val:
                        ambiguous_store.add(store_key)
                        article_map_store.pop(store_key, None)
                    else:
                        article_map_store[store_key] = store_val
                if kaspi_article in ambiguous:
                    continue
                val = {"sku_key": sku_key, "sku_id": sku_id}
                if kaspi_article in article_map and article_map[kaspi_article] != val:
                    ambiguous.add(kaspi_article)
                    article_map.pop(kaspi_article, None)
                    continue
                article_map[kaspi_article] = val

        updates: list[dict[str, Any]] = []
        for (
            row_id,
            order_id,
            store_code,
            sku_key,
            sku_id,
            my_size,
            offer_name,
            internal_status,
            kaspi_status,
            kaspi_status_detail,
            status_updated_at,
            actual_shipment_date,
            planned_shipment_date,
            created_at,
        ) in rows:
            stats["candidates"] += 1
            stage = classify_kaspi_stage_from_db_row(
                {
                    "kaspi_status": kaspi_status,
                    "kaspi_status_detail": kaspi_status_detail,
                    "actual_shipment_date": actual_shipment_date,
                    "courier_transmission_planning_date": planned_shipment_date,
                }
            )
            norm_status = normalize_order_status(stage_to_internal_status(stage), kaspi_status, {})
            status = _clean(norm_status).upper()
            if status_set and status not in status_set:
                stats["skipped_status"] += 1
                continue
            key = (_clean(order_id), _clean(store_code))
            mapping = sales_index.get(key)
            used_order_fallback = False
            used_article_fallback = False
            if not mapping:
                fallback = sales_unique_order.get(_clean(order_id))
                if fallback:
                    mapping = {
                        "sku_keys": {fallback["sku_key"]},
                        "sku_ids": {fallback["sku_id"]},
                        "sizes": {fallback["my_size"] or ""},
                        "offers": {fallback["kaspi_offer_name"] or ""},
                    }
                    used_order_fallback = True
            if not mapping and order_article_map:
                article = order_article_map.get(_clean(order_id))
                if article:
                    store_key = (_clean(store_code), _clean(article))
                    if store_key in article_map_store:
                        sku_key_val = article_map_store[store_key]["sku_key"]
                        sku_id_val = article_map_store[store_key]["sku_id"]
                        mapping = {
                            "sku_keys": {sku_key_val},
                            "sku_ids": {sku_id_val},
                            "sizes": set(),
                            "offers": set(),
                        }
                        used_article_fallback = True
                    elif article in article_map:
                        sku_key_val = article_map[article]["sku_key"]
                        sku_id_val = article_map[article]["sku_id"]
                        mapping = {
                            "sku_keys": {sku_key_val},
                            "sku_ids": {sku_id_val},
                            "sizes": set(),
                            "offers": set(),
                        }
                        used_article_fallback = True
            if not mapping:
                stats["missing_map"] += 1
                continue
            sku_key_val = _pick_single(mapping["sku_keys"])
            sku_id_val = _pick_single(mapping["sku_ids"])
            if not sku_key_val or not sku_id_val:
                stats["ambiguous"] += 1
                continue
            size_val = _pick_single(mapping["sizes"])
            offer_val = _pick_single(mapping["offers"])
            if (used_order_fallback or used_article_fallback) and not size_val and sku_id_val:
                row_size = conn.execute(
                    "SELECT my_size FROM dim_sku_size WHERE sku_id = ?",
                    (sku_id_val,),
                ).fetchone()
                if row_size:
                    size_val = normalize_size(row_size[0])
            if used_order_fallback:
                stats["fallback_order_only"] += 1
            if used_article_fallback:
                stats["fallback_article_map"] += 1

            new_sku_key = _clean(sku_key) or sku_key_val
            new_sku_id = _clean(sku_id) or sku_id_val
            new_my_size = _clean(my_size) or size_val or _clean(my_size)
            new_offer = _clean(offer_name) or offer_val or _clean(offer_name)

            if (
                _clean(sku_key) == new_sku_key
                and _clean(sku_id) == new_sku_id
                and _clean(my_size) == new_my_size
                and _clean(offer_name) == new_offer
            ):
                stats["unchanged"] += 1
                continue

            update_row = {
                "id": row_id,
                "order_id": order_id,
                "store_code": store_code,
                "sku_key_old": sku_key,
                "sku_key_new": new_sku_key,
                "sku_id_old": sku_id,
                "sku_id_new": new_sku_id,
                "my_size_old": my_size,
                "my_size_new": new_my_size,
                "offer_old": offer_name,
                "offer_new": new_offer,
                "internal_status": internal_status,
                "status_updated_at": status_updated_at,
                "actual_shipment_date": actual_shipment_date,
                "planned_shipment_date": planned_shipment_date,
                "created_at": created_at,
            }
            updates.append(update_row)

        if apply and updates:
            applied_updates = 0
            for row in updates:
                existing = conn.execute(
                    """
                    SELECT id FROM fact_orders_kaspi
                    WHERE order_id = ? AND store_code = ? AND sku_id = ? AND id != ?
                    """,
                    (
                        row["order_id"],
                        row["store_code"],
                        row["sku_id_new"],
                        row["id"],
                    ),
                ).fetchone()
                if existing:
                    stats["skipped_duplicate"] += 1
                    continue
                conn.execute(
                    """
                    UPDATE fact_orders_kaspi
                    SET sku_key = ?,
                        sku_id = ?,
                        my_size = ?,
                        kaspi_offer_name = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        row["sku_key_new"],
                        row["sku_id_new"],
                        row["my_size_new"],
                        row["offer_new"],
                        row["id"],
                    ),
                )
                applied_updates += 1
            stats["updated"] = applied_updates
        else:
            stats["updated"] = len(updates)

    if updates:
        with out_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(updates[0].keys()))
            writer.writeheader()
            writer.writerows(updates)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill missing SKU identity in fact_orders_kaspi from sales_fact_v2"
    )
    parser.add_argument("--since", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--until", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--apply", action="store_true", help="Apply updates (default: dry-run)")
    parser.add_argument(
        "--status",
        action="append",
        default=None,
        help="Normalized status to include (repeatable). Default: COMPLETED,CANCELLED,RETURNED,ON_DELIVERY",
    )
    parser.add_argument(
        "--crm-articles",
        default=None,
        help="Optional CSV with order_id -> kaspi_article mapping (columns: order_id, kaspi_article)",
    )
    parser.add_argument("--db", default=None, help="DB path override")
    args = parser.parse_args()

    if args.apply and os.environ.get("ENABLE_ORDER_WRITE") != "1":
        print("ERROR: ENABLE_ORDER_WRITE=1 is required to apply changes.")
        return 1

    since = _parse_date(args.since)
    until = _parse_date(args.until)
    if not since or not until:
        print("ERROR: Invalid --since/--until dates (expected YYYY-MM-DD).")
        return 1
    db_path = Path(args.db).expanduser() if args.db else DEFAULT_DB_PATH
    order_article_map = None
    if args.crm_articles:
        order_article_map = _load_order_article_map(Path(args.crm_articles))

    stats = backfill_orders(
        db_path=db_path,
        since=since,
        until=until,
        apply=args.apply,
        statuses=args.status,
        order_article_map=order_article_map,
    )

    print("Orders SKU backfill summary")
    print(f"  Candidates: {stats['candidates']}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Unchanged: {stats['unchanged']}")
    print(f"  Missing map: {stats['missing_map']}")
    print(f"  Ambiguous: {stats['ambiguous']}")
    print(f"  Skipped duplicate: {stats['skipped_duplicate']}")
    print(f"  Fallback order-only: {stats['fallback_order_only']}")
    print(f"  Fallback article-map: {stats['fallback_article_map']}")
    print(f"  Skipped status: {stats['skipped_status']}")
    if not args.apply:
        print("  Dry-run only (no DB writes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
