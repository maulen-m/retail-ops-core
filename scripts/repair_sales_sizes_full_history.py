#!/usr/bin/env python3
"""
Repair invalid size values in sales_fact_v2 and fact_sales.

Priority for size resolution:
1) dim_kaspi_article_map (offer/article mapping)
2) Existing normalized MY_SIZE
3) SKU_ID suffix
4) Size token parsed from Kaspi offer text
5) Historical mode for (sku_key, offer_name)
6) Historical mode for sku_key
7) First known catalog size for sku_key (forced nearest guess fallback)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, get_db
from core.ingest.sales_ingest import infer_size_from_offer_name
from core.utils.sku_normalize import (
    VALID_SIZES,
    infer_size_from_sku_id,
    normalize_size,
    normalize_sku_key,
)


TABLE_CONFIG: dict[str, dict[str, Any]] = {
    "sales_fact_v2": {
        "pk": "sale_id",
        "sum_cols": ["net_rev", "cogs", "profit", "delivery_fee"],
        "price_col": "sell_price_kzt",
        "qty_col": "quantity",
    },
    "fact_sales": {
        "pk": "id",
        "sum_cols": ["line_net_rev", "cogs_line", "profit_line", "delivery_fee"],
        "price_col": "sell_price_kzt",
        "qty_col": "quantity",
    },
}

LETTER_SIZE_ORDER = {
    "XS": 1,
    "S": 2,
    "M": 3,
    "L": 4,
    "XL": 5,
    "2XL": 6,
    "3XL": 7,
    "4XL": 8,
    "5XL": 9,
    "ONE_SIZE": 100,
}


def _offer_key(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _product_type(sku_key: str | None, sku_id: str | None) -> str | None:
    base = str(sku_key or "").strip() or str(sku_id or "").strip()
    if "_" not in base:
        return None
    return base.split("_", 1)[0]


def _size_rank(size: str) -> tuple[int, str]:
    if size in LETTER_SIZE_ORDER:
        return LETTER_SIZE_ORDER[size], size
    if str(size).isdigit():
        return 200 + int(size), str(size)
    return 9999, str(size)


def _counter_mode(counter: Counter[str]) -> str | None:
    if not counter:
        return None
    ranked = sorted(counter.items(), key=lambda item: (-item[1], _size_rank(item[0])))
    return ranked[0][0]


def _coerce_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _prefer_sku_id(sku_key: str, size: str, current: str | None, candidate: str) -> str:
    canonical = f"{sku_key}_{size}"
    if candidate == canonical:
        return candidate
    if current == canonical:
        return current
    if current and len(current) <= len(candidate):
        return current
    return candidate


@dataclass
class Lookups:
    dim_skuid_to_identity: dict[str, tuple[str, str]]
    dim_key_size_to_skuid: dict[tuple[str, str], str]
    dim_sizes_by_key: dict[str, list[str]]
    offer_mode: dict[tuple[str, str], str]
    hist_mode_offer: dict[tuple[str, str], str]
    hist_mode_sku: dict[str, str]


def _build_lookups(conn) -> Lookups:
    dim_skuid_to_identity: dict[str, tuple[str, str]] = {}
    dim_key_size_to_skuid: dict[tuple[str, str], str] = {}
    dim_sizes_raw: dict[str, set[str]] = defaultdict(set)

    dim_rows = conn.execute(
        "SELECT sku_id, sku_key, my_size FROM dim_sku_size"
    ).fetchall()
    for row in dim_rows:
        sku_id = str(row["sku_id"] or "").strip()
        sku_key = str(row["sku_key"] or "").strip()
        if not sku_id or not sku_key:
            continue
        product_type = _product_type(sku_key, sku_id)
        size = normalize_size(row["my_size"], product_type=product_type)
        if not size:
            size = normalize_size(infer_size_from_sku_id(sku_id), product_type=product_type)
        if not size or size not in VALID_SIZES:
            continue
        dim_skuid_to_identity[sku_id] = (sku_key, size)
        key = (sku_key, size)
        dim_key_size_to_skuid[key] = _prefer_sku_id(
            sku_key, size, dim_key_size_to_skuid.get(key), sku_id
        )
        dim_sizes_raw[sku_key].add(size)

    dim_sizes_by_key = {
        sku_key: sorted(list(sizes), key=_size_rank)
        for sku_key, sizes in dim_sizes_raw.items()
    }

    offer_counter: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    offer_rows = conn.execute(
        """
        SELECT sku_key, sku_id, kaspi_offer_name
        FROM dim_kaspi_article_map
        WHERE active_flag = 1
        """
    ).fetchall()
    for row in offer_rows:
        sku_key = str(row["sku_key"] or "").strip()
        offer_name = str(row["kaspi_offer_name"] or "").strip()
        sku_id = str(row["sku_id"] or "").strip()
        if not sku_key or not offer_name:
            continue
        product_type = _product_type(sku_key, sku_id)
        size = None
        if sku_id in dim_skuid_to_identity:
            size = dim_skuid_to_identity[sku_id][1]
        if not size:
            size = normalize_size(infer_size_from_sku_id(sku_id), product_type=product_type)
        if not size:
            continue
        offer_counter[(sku_key, _offer_key(offer_name))][size] += 1
    offer_mode = {k: _counter_mode(v) for k, v in offer_counter.items() if v}

    hist_offer_counter: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    hist_sku_counter: dict[str, Counter[str]] = defaultdict(Counter)
    for table, cfg in TABLE_CONFIG.items():
        rows = conn.execute(
            f"""
            SELECT sku_key, sku_id, my_size, kaspi_offer_name, {cfg['qty_col']} AS qty
            FROM {table}
            """
        ).fetchall()
        for row in rows:
            sku_key = str(row["sku_key"] or "").strip()
            sku_id = str(row["sku_id"] or "").strip()
            offer_name = str(row["kaspi_offer_name"] or "").strip()
            if not sku_key:
                continue
            product_type = _product_type(sku_key, sku_id)
            size = normalize_size(row["my_size"], product_type=product_type)
            if not size:
                size = normalize_size(infer_size_from_sku_id(sku_id), product_type=product_type)
            if not size:
                continue
            qty = max(_coerce_int(row["qty"]), 1)
            hist_offer_counter[(sku_key, _offer_key(offer_name))][size] += qty
            hist_sku_counter[sku_key][size] += qty

    hist_mode_offer = {k: _counter_mode(v) for k, v in hist_offer_counter.items() if v}
    hist_mode_sku = {k: _counter_mode(v) for k, v in hist_sku_counter.items() if v}

    return Lookups(
        dim_skuid_to_identity=dim_skuid_to_identity,
        dim_key_size_to_skuid=dim_key_size_to_skuid,
        dim_sizes_by_key=dim_sizes_by_key,
        offer_mode=offer_mode,
        hist_mode_offer=hist_mode_offer,
        hist_mode_sku=hist_mode_sku,
    )


def _canonical_sku_id(lookups: Lookups, sku_key: str, size: str) -> str:
    return lookups.dim_key_size_to_skuid.get((sku_key, size), f"{sku_key}_{size}")


def _ensure_dim_sku_size(conn, lookups: Lookups, sku_key: str, size: str, sku_id: str) -> None:
    if sku_id in lookups.dim_skuid_to_identity:
        return
    conn.execute(
        "INSERT OR IGNORE INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?, ?, ?)",
        (sku_id, sku_key, size),
    )
    lookups.dim_skuid_to_identity[sku_id] = (sku_key, size)
    key = (sku_key, size)
    lookups.dim_key_size_to_skuid[key] = _prefer_sku_id(
        sku_key,
        size,
        lookups.dim_key_size_to_skuid.get(key),
        sku_id,
    )
    if sku_key not in lookups.dim_sizes_by_key:
        lookups.dim_sizes_by_key[sku_key] = [size]
    elif size not in lookups.dim_sizes_by_key[sku_key]:
        lookups.dim_sizes_by_key[sku_key].append(size)
        lookups.dim_sizes_by_key[sku_key] = sorted(lookups.dim_sizes_by_key[sku_key], key=_size_rank)


def _choose_size_for_invalid_row(row, lookups: Lookups) -> tuple[str | None, str]:
    sku_key = str(row["sku_key"] or "").strip()
    sku_id = str(row["sku_id"] or "").strip()
    offer_name = str(row["kaspi_offer_name"] or "").strip()

    if not sku_key and sku_id and "_" in sku_id:
        base = sku_id.rsplit("_", 1)[0]
        sku_key = normalize_sku_key(base)
    if not sku_key:
        return None, "missing_sku_key"

    product_type = _product_type(sku_key, sku_id)
    offer_key = (sku_key, _offer_key(offer_name))
    candidates: list[tuple[str | None, str]] = [
        (lookups.offer_mode.get(offer_key), "offer_map"),
        (normalize_size(row["my_size"], product_type=product_type), "my_size"),
        (normalize_size(infer_size_from_sku_id(sku_id), product_type=product_type), "sku_id_suffix"),
        (infer_size_from_offer_name(offer_name, product_type=product_type), "offer_text"),
        (lookups.hist_mode_offer.get(offer_key), "hist_offer_mode"),
        (lookups.hist_mode_sku.get(sku_key), "hist_sku_mode"),
    ]
    catalog_sizes = lookups.dim_sizes_by_key.get(sku_key) or []
    if catalog_sizes:
        candidates.append((catalog_sizes[0], "catalog_fallback"))

    for size, source in candidates:
        if size and size in VALID_SIZES:
            return size, source
    return None, "unresolved"


def _merge_rows(
    conn,
    table: str,
    cfg: dict[str, Any],
    keep_rid: int,
    drop_rid: int,
    size: str,
    sku_id: str,
) -> None:
    cols = [cfg["qty_col"], cfg["price_col"], *cfg["sum_cols"]]
    select_cols = ", ".join(cols)
    keep_row = conn.execute(
        f"SELECT {select_cols} FROM {table} WHERE rowid = ?",
        (keep_rid,),
    ).fetchone()
    drop_row = conn.execute(
        f"SELECT {select_cols} FROM {table} WHERE rowid = ?",
        (drop_rid,),
    ).fetchone()
    keep_qty = _coerce_int(keep_row[cfg["qty_col"]])
    drop_qty = _coerce_int(drop_row[cfg["qty_col"]])
    total_qty = keep_qty + drop_qty

    keep_price = keep_row[cfg["price_col"]]
    drop_price = drop_row[cfg["price_col"]]
    if total_qty > 0:
        weighted_price = (
            (_coerce_float(keep_price) * keep_qty) + (_coerce_float(drop_price) * drop_qty)
        ) / total_qty
    else:
        weighted_price = _coerce_float(keep_price) or _coerce_float(drop_price)

    sum_updates = {
        col: _coerce_float(keep_row[col]) + _coerce_float(drop_row[col])
        for col in cfg["sum_cols"]
    }
    set_parts = [f"{cfg['qty_col']} = ?", f"{cfg['price_col']} = ?", "my_size = ?", "sku_id = ?"]
    values: list[Any] = [total_qty, weighted_price, size, sku_id]
    for col in cfg["sum_cols"]:
        set_parts.append(f"{col} = ?")
        values.append(sum_updates[col])
    values.append(keep_rid)
    conn.execute(
        f"UPDATE {table} SET {', '.join(set_parts)} WHERE rowid = ?",
        tuple(values),
    )
    conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (drop_rid,))


def _fix_table(conn, table: str, lookups: Lookups, apply: bool, verbose: bool) -> dict[str, Any]:
    cfg = TABLE_CONFIG[table]
    rows = conn.execute(
        f"""
        SELECT
            rowid AS rid,
            {cfg['pk']} AS pk,
            order_id,
            store_code,
            kaspi_offer_name,
            sku_key,
            sku_id,
            my_size,
            {cfg['qty_col']} AS qty
        FROM {table}
        """
    ).fetchall()

    stats = {
        "scanned": 0,
        "updated": 0,
        "merged": 0,
        "unchanged": 0,
        "unresolved": 0,
        "source_counts": Counter(),
    }

    for row in rows:
        stats["scanned"] += 1
        sku_key = str(row["sku_key"] or "").strip()
        sku_id = str(row["sku_id"] or "").strip()
        product_type = _product_type(sku_key, sku_id)
        raw_size = str(row["my_size"] or "").strip()
        current_size = normalize_size(raw_size, product_type=product_type)
        raw_is_canonical = bool(current_size) and raw_size == current_size

        if current_size and raw_is_canonical:
            stats["unchanged"] += 1
            continue

        if current_size and not raw_is_canonical:
            chosen_size = current_size
            source = "my_size_canonicalized"
        else:
            chosen_size, source = _choose_size_for_invalid_row(row, lookups)
        stats["source_counts"][source] += 1

        if not chosen_size:
            stats["unresolved"] += 1
            continue
        if not sku_key and sku_id and "_" in sku_id:
            sku_key = normalize_sku_key(sku_id.rsplit("_", 1)[0])
        if not sku_key:
            stats["unresolved"] += 1
            continue

        new_sku_id = _canonical_sku_id(lookups, sku_key, chosen_size)
        if apply:
            _ensure_dim_sku_size(conn, lookups, sku_key, chosen_size, new_sku_id)

        existing = conn.execute(
            f"""
            SELECT rowid AS rid
            FROM {table}
            WHERE order_id = ? AND store_code = ? AND kaspi_offer_name = ? AND sku_id = ?
              AND rowid != ?
            """,
            (
                row["order_id"],
                row["store_code"],
                row["kaspi_offer_name"],
                new_sku_id,
                row["rid"],
            ),
        ).fetchone()

        if apply:
            if existing:
                _merge_rows(
                    conn=conn,
                    table=table,
                    cfg=cfg,
                    keep_rid=int(existing["rid"]),
                    drop_rid=int(row["rid"]),
                    size=chosen_size,
                    sku_id=new_sku_id,
                )
                stats["merged"] += 1
            else:
                conn.execute(
                    f"UPDATE {table} SET sku_key = ?, sku_id = ?, my_size = ? WHERE rowid = ?",
                    (sku_key, new_sku_id, chosen_size, row["rid"]),
                )
                stats["updated"] += 1
        else:
            if existing:
                stats["merged"] += 1
            else:
                stats["updated"] += 1

    if verbose:
        print(
            f"{table}: scanned={stats['scanned']} updated={stats['updated']} "
            f"merged={stats['merged']} unresolved={stats['unresolved']}"
        )
    return stats


def _print_source_breakdown(stats: dict[str, Any], table: str) -> None:
    top = sorted(
        stats["source_counts"].items(),
        key=lambda item: (-item[1], item[0]),
    )
    print(f"\n{table} size source breakdown:")
    for source, count in top:
        print(f"  - {source}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair invalid size values in sales tables.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to SQLite DB")
    parser.add_argument(
        "--tables",
        type=str,
        default="sales_fact_v2,fact_sales",
        help="Comma-separated tables to repair",
    )
    parser.add_argument("--apply", action="store_true", help="Apply writes (default: dry-run)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    tables = [t.strip() for t in args.tables.split(",") if t.strip()]
    for table in tables:
        if table not in TABLE_CONFIG:
            raise ValueError(f"Unsupported table: {table}")

    with get_db(args.db) as conn:
        lookups = _build_lookups(conn)
        all_stats: dict[str, dict[str, Any]] = {}
        for table in tables:
            stats = _fix_table(conn, table, lookups=lookups, apply=args.apply, verbose=True)
            all_stats[table] = stats
        if not args.apply:
            conn.rollback()

    print(f"\nMode: {'APPLY' if args.apply else 'DRY-RUN'}")
    for table in tables:
        stats = all_stats[table]
        _print_source_breakdown(stats, table)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
