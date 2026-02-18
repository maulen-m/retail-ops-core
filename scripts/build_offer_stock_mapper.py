#!/usr/bin/env python3
"""Build current offer->SKU mapper for pricelist stock/price sync."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, get_db
from core.utils.sku_normalize import normalize_size

DEFAULT_CONFIG = PROJECT_ROOT / "config" / "kaspi_stores.yaml"
DEFAULT_TABLE = "fact_offer_stock_mapper_current"
DEFAULT_STORES = ("UNIVERSAL", "STOREB")


@dataclass(frozen=True)
class MappingDecision:
    sku_id: str | None
    sku_key: str | None
    my_size: str | None
    mapping_method: str
    mapping_confidence: str
    is_ambiguous: int


def _safe_table_name(table_name: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table_name):
        raise ValueError(f"Unsafe table name: {table_name}")
    return table_name


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r["name"]) for r in rows}


def _normalize_store_codes(stores: list[str] | tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for value in stores:
        code = str(value or "").strip().upper()
        if code and code not in out:
            out.append(code)
    return out


def _load_merchant_ids(config_path: Path) -> dict[str, str]:
    if not config_path.exists():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    stores = data.get("stores", {}) if isinstance(data, dict) else {}
    out: dict[str, str] = {}
    for store_code, info in stores.items():
        if not isinstance(info, dict):
            continue
        merchant_uid = info.get("merchant_uid")
        if merchant_uid:
            out[str(store_code).upper()] = str(merchant_uid)
    return out


def _parse_article_size(kaspi_article: str | None) -> str | None:
    article = str(kaspi_article or "").strip()
    if not article:
        return None
    tokens = [tok for tok in article.split("_") if tok]
    if len(tokens) < 2:
        return None
    last = tokens[-1]
    raw_size = tokens[-2] if last.isdigit() else last
    return normalize_size(raw_size)


def _confidence_from_share(share: float | None) -> str:
    if share is None:
        return "LOW"
    if share >= 0.6:
        return "HIGH"
    if share >= 0.4:
        return "MEDIUM"
    return "LOW"


def _build_sku_index(conn: sqlite3.Connection) -> tuple[dict[str, tuple[str, str | None]], dict[str, list[tuple[str, str | None]]]]:
    if not _table_exists(conn, "dim_sku_size"):
        raise RuntimeError("dim_sku_size table is required")

    size_cols = _table_columns(conn, "dim_sku_size")
    sku_cols = _table_columns(conn, "dim_sku") if _table_exists(conn, "dim_sku") else set()
    has_size_active = "active_flag" in size_cols
    has_sku_active = "active_flag" in sku_cols

    join_dim_sku = "LEFT JOIN dim_sku d ON d.sku_key = s.sku_key" if _table_exists(conn, "dim_sku") else ""
    where_parts = ["COALESCE(TRIM(s.sku_id), '') != ''", "COALESCE(TRIM(s.sku_key), '') != ''"]
    if has_size_active:
        where_parts.append("COALESCE(s.active_flag, 1) = 1")
    if has_sku_active:
        where_parts.append("COALESCE(d.active_flag, 1) = 1")

    rows = conn.execute(
        f"""
        SELECT s.sku_id, s.sku_key, s.my_size
        FROM dim_sku_size s
        {join_dim_sku}
        WHERE {" AND ".join(where_parts)}
        """
    ).fetchall()

    by_id: dict[str, tuple[str, str | None]] = {}
    by_key: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    for row in rows:
        sku_id = str(row["sku_id"]).strip()
        sku_key = str(row["sku_key"]).strip()
        my_size = normalize_size(row["my_size"])
        by_id[sku_id] = (sku_key, my_size)
        by_key[sku_key].append((sku_id, my_size))
    return by_id, dict(by_key)


def _pick_sku_by_key_size(
    sku_rows_by_key: dict[str, list[tuple[str, str | None]]],
    sku_key: str | None,
    my_size: str | None,
) -> tuple[str | None, str | None, int]:
    if not sku_key:
        return None, None, 0
    rows = sku_rows_by_key.get(sku_key, [])
    if not rows:
        return None, None, 0

    if my_size:
        size_norm = normalize_size(my_size)
        matched = [row for row in rows if row[1] == size_norm]
        if not matched:
            return None, None, 0
        if len(matched) == 1:
            return matched[0][0], matched[0][1], 0
        matched.sort(key=lambda v: v[0])
        return matched[0][0], matched[0][1], 1

    if len(rows) == 1:
        return rows[0][0], rows[0][1], 0
    rows_sorted = sorted(rows, key=lambda v: v[0])
    return rows_sorted[0][0], rows_sorted[0][1], 1


def _ensure_mapper_table(conn: sqlite3.Connection, table_name: str) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            store_code TEXT NOT NULL,
            merchant_uid TEXT,
            kaspi_article TEXT NOT NULL,
            kaspi_offer_name TEXT,
            sku_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            mapping_method TEXT NOT NULL,
            mapping_confidence TEXT NOT NULL,
            is_ambiguous INTEGER NOT NULL DEFAULT 0,
            source_updated_at TEXT,
            UNIQUE(store_code, kaspi_article)
        )
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table_name}_store ON {table_name}(store_code)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table_name}_sku_id ON {table_name}(sku_id)"
    )


def _load_offer_size_stats(
    conn: sqlite3.Connection,
    offer_name: str,
    cache: dict[str, dict[str, Any] | None],
) -> dict[str, Any] | None:
    if offer_name in cache:
        return cache[offer_name]

    if not _table_exists(conn, "kaspi_offer_size_stats"):
        cache[offer_name] = None
        return None

    cols = _table_columns(conn, "kaspi_offer_size_stats")
    required = {"kaspi_offer_name", "sku_id_final"}
    if not required.issubset(cols):
        cache[offer_name] = None
        return None

    units_expr = "COALESCE(units, 0)" if "units" in cols else "1"
    total_units_expr = "COALESCE(total_units, 0)" if "total_units" in cols else "0"
    share_expr = "COALESCE(share, 0)" if "share" in cols else "0"
    rows = conn.execute(
        f"""
        SELECT
            sku_id_final AS sku_id,
            sku_key_final AS sku_key,
            my_size_final AS my_size,
            {units_expr} AS units,
            {total_units_expr} AS total_units,
            {share_expr} AS share
        FROM kaspi_offer_size_stats
        WHERE kaspi_offer_name = ?
          AND COALESCE(TRIM(sku_id_final), '') != ''
        """,
        (offer_name,),
    ).fetchall()
    if not rows:
        cache[offer_name] = None
        return None

    rows_sorted = sorted(
        rows,
        key=lambda r: (
            -float(r["units"] or 0),
            -float(r["share"] or 0),
            str(r["sku_id"]),
        ),
    )
    top = rows_sorted[0]
    top_units = float(top["units"] or 0)
    top_share = float(top["share"] or 0)
    if top_share <= 0:
        total_units = float(top["total_units"] or 0)
        top_share = top_units / total_units if total_units > 0 else 0.0
    ambiguous = int(
        any(
            float(row["units"] or 0) == top_units and str(row["sku_id"]) != str(top["sku_id"])
            for row in rows_sorted[1:]
        )
    )
    result = {
        "sku_id": str(top["sku_id"]).strip(),
        "sku_key": str(top["sku_key"]).strip() if top["sku_key"] else None,
        "my_size": normalize_size(top["my_size"]),
        "share": top_share,
        "is_ambiguous": ambiguous,
    }
    cache[offer_name] = result
    return result


def _load_recent_offer_mode(
    conn: sqlite3.Connection,
    store_code: str,
    offer_name: str,
    window_days: int,
    cache: dict[tuple[str, str, int], dict[str, Any] | None],
) -> dict[str, Any] | None:
    key = (store_code, offer_name, window_days)
    if key in cache:
        return cache[key]

    if not _table_exists(conn, "fact_sales"):
        cache[key] = None
        return None

    window_modifier = f"-{int(window_days)} day"
    rows = conn.execute(
        """
        SELECT
            sku_id,
            sku_key,
            my_size,
            SUM(COALESCE(quantity, 0)) AS units
        FROM fact_sales
        WHERE store_code = ?
          AND kaspi_offer_name = ?
          AND order_date >= date('now', ?)
          AND COALESCE(TRIM(sku_id), '') != ''
        GROUP BY sku_id, sku_key, my_size
        """,
        (store_code, offer_name, window_modifier),
    ).fetchall()
    if not rows:
        cache[key] = None
        return None

    rows_sorted = sorted(
        rows,
        key=lambda r: (-float(r["units"] or 0), str(r["sku_id"])),
    )
    top = rows_sorted[0]
    top_units = float(top["units"] or 0)
    total_units = sum(float(row["units"] or 0) for row in rows_sorted)
    share = top_units / total_units if total_units > 0 else 0.0
    ambiguous = int(
        any(
            float(row["units"] or 0) == top_units and str(row["sku_id"]) != str(top["sku_id"])
            for row in rows_sorted[1:]
        )
    )
    result = {
        "sku_id": str(top["sku_id"]).strip(),
        "sku_key": str(top["sku_key"]).strip() if top["sku_key"] else None,
        "my_size": normalize_size(top["my_size"]),
        "share": share,
        "is_ambiguous": ambiguous,
    }
    cache[key] = result
    return result


def _load_offer_best_sku_key(
    conn: sqlite3.Connection,
    offer_name: str,
    cache: dict[str, tuple[str | None, int]],
) -> tuple[str | None, int]:
    if offer_name in cache:
        return cache[offer_name]
    if not _table_exists(conn, "kaspi_offer_map"):
        cache[offer_name] = (None, 0)
        return cache[offer_name]
    cols = _table_columns(conn, "kaspi_offer_map")
    if "kaspi_offer_name" not in cols or "sku_key" not in cols:
        cache[offer_name] = (None, 0)
        return cache[offer_name]

    count_expr = "COALESCE(count_total, 0)" if "count_total" in cols else "0"
    share_expr = "COALESCE(share_total, 0)" if "share_total" in cols else "0"
    rows = conn.execute(
        f"""
        SELECT sku_key, {count_expr} AS count_total, {share_expr} AS share_total
        FROM kaspi_offer_map
        WHERE kaspi_offer_name = ?
          AND COALESCE(TRIM(sku_key), '') != ''
        ORDER BY count_total DESC, share_total DESC, sku_key ASC
        """,
        (offer_name,),
    ).fetchall()
    if not rows:
        cache[offer_name] = (None, 0)
        return cache[offer_name]

    top = rows[0]
    top_count = float(top["count_total"] or 0)
    top_share = float(top["share_total"] or 0)
    ambiguous = int(
        any(
            float(row["count_total"] or 0) == top_count
            and float(row["share_total"] or 0) == top_share
            and str(row["sku_key"]) != str(top["sku_key"])
            for row in rows[1:]
        )
    )
    cache[offer_name] = (str(top["sku_key"]).strip(), ambiguous)
    return cache[offer_name]


def _load_size_probability(
    conn: sqlite3.Connection,
    level: str,
    key_value: str,
    cache: dict[tuple[str, str], tuple[str | None, str | None]],
) -> tuple[str | None, str | None]:
    cache_key = (level, key_value)
    if cache_key in cache:
        return cache[cache_key]
    if not _table_exists(conn, "dim_size_probability"):
        cache[cache_key] = (None, None)
        return cache[cache_key]

    rows = conn.execute(
        """
        SELECT mode_size, confidence
        FROM dim_size_probability
        WHERE level = ? AND key_value = ?
        LIMIT 1
        """,
        (level, key_value),
    ).fetchone()
    if not rows:
        cache[cache_key] = (None, None)
        return cache[cache_key]
    mode_size = normalize_size(rows["mode_size"])
    confidence = str(rows["confidence"] or "").strip().upper() or None
    cache[cache_key] = (mode_size, confidence)
    return cache[cache_key]


def _resolve_mapping(
    *,
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    sku_by_id: dict[str, tuple[str, str | None]],
    sku_rows_by_key: dict[str, list[tuple[str, str | None]]],
    window_days: int,
    offer_stats_cache: dict[str, dict[str, Any] | None],
    recent_sales_cache: dict[tuple[str, str, int], dict[str, Any] | None],
    offer_map_cache: dict[str, tuple[str | None, int]],
    size_prob_cache: dict[tuple[str, str], tuple[str | None, str | None]],
) -> MappingDecision:
    store_code = str(row["store_code"]).strip().upper()
    kaspi_article = str(row["kaspi_article"] or "").strip()
    offer_name = str(row["kaspi_offer_name"] or "").strip()
    source_sku_key = str(row["sku_key"] or "").strip() or None
    source_sku_id = str(row["sku_id"] or "").strip() or None
    ambiguous_hint = 0

    if source_sku_id and source_sku_id in sku_by_id:
        sku_key, my_size = sku_by_id[source_sku_id]
        return MappingDecision(
            sku_id=source_sku_id,
            sku_key=sku_key,
            my_size=my_size,
            mapping_method="article_map_sku_id",
            mapping_confidence="HIGH",
            is_ambiguous=0,
        )

    article_size = _parse_article_size(kaspi_article)
    if source_sku_key and article_size:
        sku_id, my_size, ambiguous = _pick_sku_by_key_size(
            sku_rows_by_key,
            source_sku_key,
            article_size,
        )
        if sku_id:
            return MappingDecision(
                sku_id=sku_id,
                sku_key=source_sku_key,
                my_size=my_size,
                mapping_method="article_map_article_size",
                mapping_confidence="HIGH",
                is_ambiguous=ambiguous,
            )
        ambiguous_hint = max(ambiguous_hint, ambiguous)

    if source_sku_key:
        sku_id, my_size, ambiguous = _pick_sku_by_key_size(
            sku_rows_by_key,
            source_sku_key,
            None,
        )
        if sku_id and ambiguous == 0:
            return MappingDecision(
                sku_id=sku_id,
                sku_key=source_sku_key,
                my_size=my_size,
                mapping_method="article_map_sku_key_single",
                mapping_confidence="HIGH",
                is_ambiguous=0,
            )
        ambiguous_hint = max(ambiguous_hint, ambiguous)

    if offer_name:
        stats_row = _load_offer_size_stats(conn, offer_name, offer_stats_cache)
        if stats_row and stats_row["sku_id"] in sku_by_id:
            sku_key, my_size = sku_by_id[stats_row["sku_id"]]
            return MappingDecision(
                sku_id=stats_row["sku_id"],
                sku_key=sku_key,
                my_size=my_size,
                mapping_method="offer_size_stats",
                mapping_confidence=_confidence_from_share(stats_row.get("share")),
                is_ambiguous=max(ambiguous_hint, int(stats_row.get("is_ambiguous") or 0)),
            )

    if offer_name:
        sales_row = _load_recent_offer_mode(
            conn,
            store_code,
            offer_name,
            window_days,
            recent_sales_cache,
        )
        if sales_row and sales_row["sku_id"] in sku_by_id:
            sku_key, my_size = sku_by_id[sales_row["sku_id"]]
            return MappingDecision(
                sku_id=sales_row["sku_id"],
                sku_key=sku_key,
                my_size=my_size,
                mapping_method="recent_sales_offer_mode",
                mapping_confidence=_confidence_from_share(sales_row.get("share")),
                is_ambiguous=max(ambiguous_hint, int(sales_row.get("is_ambiguous") or 0)),
            )

    offer_map_sku_key: str | None = None
    offer_map_ambiguous = 0
    if offer_name:
        offer_map_sku_key, offer_map_ambiguous = _load_offer_best_sku_key(
            conn,
            offer_name,
            offer_map_cache,
        )
        ambiguous_hint = max(ambiguous_hint, offer_map_ambiguous)

    sku_key_for_prob = source_sku_key or offer_map_sku_key
    if offer_name and sku_key_for_prob:
        mode_size, confidence = _load_size_probability(
            conn,
            "OFFER",
            offer_name,
            size_prob_cache,
        )
        if mode_size:
            sku_id, my_size, ambiguous = _pick_sku_by_key_size(
                sku_rows_by_key,
                sku_key_for_prob,
                mode_size,
            )
            if sku_id:
                return MappingDecision(
                    sku_id=sku_id,
                    sku_key=sku_key_for_prob,
                    my_size=my_size,
                    mapping_method="size_probability_offer",
                    mapping_confidence=confidence or "MEDIUM",
                    is_ambiguous=max(ambiguous_hint, ambiguous),
                )
            ambiguous_hint = max(ambiguous_hint, ambiguous)

    if sku_key_for_prob:
        mode_size, confidence = _load_size_probability(
            conn,
            "STYLE",
            sku_key_for_prob,
            size_prob_cache,
        )
        if mode_size:
            sku_id, my_size, ambiguous = _pick_sku_by_key_size(
                sku_rows_by_key,
                sku_key_for_prob,
                mode_size,
            )
            if sku_id:
                return MappingDecision(
                    sku_id=sku_id,
                    sku_key=sku_key_for_prob,
                    my_size=my_size,
                    mapping_method="size_probability_style",
                    mapping_confidence=confidence or "MEDIUM",
                    is_ambiguous=max(ambiguous_hint, ambiguous),
                )
            ambiguous_hint = max(ambiguous_hint, ambiguous)

    return MappingDecision(
        sku_id=None,
        sku_key=source_sku_key or offer_map_sku_key,
        my_size=None,
        mapping_method="unresolved",
        mapping_confidence="LOW",
        is_ambiguous=int(ambiguous_hint > 0),
    )


def build_offer_stock_mapper(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    stores: list[str] | tuple[str, ...] = DEFAULT_STORES,
    config_path: Path = DEFAULT_CONFIG,
    table_name: str = DEFAULT_TABLE,
    window_days: int = 90,
    dry_run: bool = False,
) -> dict[str, Any]:
    selected_stores = _normalize_store_codes(stores)
    if not selected_stores:
        raise ValueError("stores list is empty")
    mapper_table = _safe_table_name(table_name)
    merchant_ids = _load_merchant_ids(config_path)
    generated_at = datetime.now(timezone.utc).isoformat()

    with get_db(db_path) as conn:
        if not _table_exists(conn, "dim_kaspi_article_map"):
            raise RuntimeError("dim_kaspi_article_map table is required")
        _ensure_mapper_table(conn, mapper_table)

        map_cols = _table_columns(conn, "dim_kaspi_article_map")
        has_active = "active_flag" in map_cols
        select_offer = "kaspi_offer_name" if "kaspi_offer_name" in map_cols else "NULL AS kaspi_offer_name"
        select_sku_key = "sku_key" if "sku_key" in map_cols else "NULL AS sku_key"
        select_sku_id = "sku_id" if "sku_id" in map_cols else "NULL AS sku_id"
        select_updated = "updated_at" if "updated_at" in map_cols else "NULL AS updated_at"
        active_clause = "AND COALESCE(active_flag, 1) = 1" if has_active else ""

        placeholders = ",".join("?" for _ in selected_stores)
        source_rows = conn.execute(
            f"""
            SELECT *
            FROM (
                SELECT
                    id,
                    store_code,
                    kaspi_article,
                    {select_offer},
                    {select_sku_key},
                    {select_sku_id},
                    {select_updated},
                    ROW_NUMBER() OVER (
                        PARTITION BY store_code, kaspi_article
                        ORDER BY COALESCE(updated_at, '') DESC, id DESC
                    ) AS rn
                FROM dim_kaspi_article_map
                WHERE store_code IN ({placeholders})
                  AND COALESCE(TRIM(kaspi_article), '') != ''
                  {active_clause}
            ) latest
            WHERE rn = 1
            ORDER BY store_code, kaspi_article
            """,
            tuple(selected_stores),
        ).fetchall()

        sku_by_id, sku_rows_by_key = _build_sku_index(conn)
        offer_stats_cache: dict[str, dict[str, Any] | None] = {}
        recent_sales_cache: dict[tuple[str, str, int], dict[str, Any] | None] = {}
        offer_map_cache: dict[str, tuple[str | None, int]] = {}
        size_prob_cache: dict[tuple[str, str], tuple[str | None, str | None]] = {}

        rows_to_insert: list[tuple[Any, ...]] = []
        method_counter: Counter[str] = Counter()
        confidence_counter: Counter[str] = Counter()

        for row in source_rows:
            decision = _resolve_mapping(
                conn=conn,
                row=row,
                sku_by_id=sku_by_id,
                sku_rows_by_key=sku_rows_by_key,
                window_days=window_days,
                offer_stats_cache=offer_stats_cache,
                recent_sales_cache=recent_sales_cache,
                offer_map_cache=offer_map_cache,
                size_prob_cache=size_prob_cache,
            )
            store_code = str(row["store_code"]).strip().upper()
            kaspi_article = str(row["kaspi_article"]).strip()
            offer_name = str(row["kaspi_offer_name"] or "").strip() or None
            source_updated_at = str(row["updated_at"] or "").strip() or None
            rows_to_insert.append(
                (
                    generated_at,
                    store_code,
                    merchant_ids.get(store_code),
                    kaspi_article,
                    offer_name,
                    decision.sku_id,
                    decision.sku_key,
                    decision.my_size,
                    decision.mapping_method,
                    decision.mapping_confidence,
                    int(decision.is_ambiguous),
                    source_updated_at,
                )
            )
            method_counter[decision.mapping_method] += 1
            confidence_counter[decision.mapping_confidence] += 1

        if not dry_run:
            del_placeholders = ",".join("?" for _ in selected_stores)
            conn.execute(
                f"DELETE FROM {mapper_table} WHERE store_code IN ({del_placeholders})",
                tuple(selected_stores),
            )
            conn.executemany(
                f"""
                INSERT INTO {mapper_table} (
                    generated_at,
                    store_code,
                    merchant_uid,
                    kaspi_article,
                    kaspi_offer_name,
                    sku_id,
                    sku_key,
                    my_size,
                    mapping_method,
                    mapping_confidence,
                    is_ambiguous,
                    source_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )

        unresolved_count = int(method_counter.get("unresolved", 0))
        ambiguous_count = sum(1 for row in rows_to_insert if int(row[10]) == 1)
        return {
            "db_path": str(db_path),
            "table_name": mapper_table,
            "stores": selected_stores,
            "window_days": int(window_days),
            "dry_run": bool(dry_run),
            "rows_total": len(rows_to_insert),
            "unresolved_rows": unresolved_count,
            "ambiguous_rows": ambiguous_count,
            "by_method": dict(method_counter),
            "by_confidence": dict(confidence_counter),
            "generated_at": generated_at,
        }


def _print_summary(summary: dict[str, Any]) -> None:
    print(f"Mapper table: {summary['table_name']}")
    print(f"Stores: {', '.join(summary['stores'])}")
    print(f"Rows: {summary['rows_total']}")
    print(f"Unresolved: {summary['unresolved_rows']}")
    print(f"Ambiguous: {summary['ambiguous_rows']}")
    print("Methods:")
    for key in sorted(summary["by_method"].keys()):
        print(f"  {key}: {summary['by_method'][key]}")
    print("Confidence:")
    for key in sorted(summary["by_confidence"].keys()):
        print(f"  {key}: {summary['by_confidence'][key]}")
    print(f"Dry run: {summary['dry_run']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build offer->SKU mapper table for stock/price sync")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--store",
        action="append",
        dest="stores",
        help="Store code (repeatable). Default: UNIVERSAL + STOREB",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="kaspi_stores.yaml path")
    parser.add_argument("--table-name", default=DEFAULT_TABLE)
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stores = args.stores if args.stores else list(DEFAULT_STORES)
    summary = build_offer_stock_mapper(
        db_path=args.db,
        stores=stores,
        config_path=args.config,
        table_name=args.table_name,
        window_days=args.window_days,
        dry_run=args.dry_run,
    )
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
