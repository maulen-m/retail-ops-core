#!/usr/bin/env python3
"""Materialize compact C3 ads source rows from local marketing evidence.

This imports exact campaign-product rows and, for completed full-store
aggregate windows, can materialize no-spend rows for delivered sale SKUs that
are absent from the aggregate product universe or have aggregate zero spend.
Positive aggregate spend is never fanned out to daily SKU coverage. Apply
requires ENABLE_C3_ADS_SOURCE_WRITE=1. Production DB apply also requires
ALLOW_PRODUCTION_C3_ADS_SOURCE_WRITE=1.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH
from core.ads.active_scope import is_store_active_on
from scripts.backup_db import backup_database

ENV_GATE = "ENABLE_C3_ADS_SOURCE_WRITE"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_C3_ADS_SOURCE_WRITE"
DELIVERED_SALES_STATUSES = {"COMPLETED", "DELIVERED", "SOLD"}


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _date_key(value: Any) -> str:
    return str(value or "").strip()[:10]


def _parse_date(value: Any) -> date | None:
    text = _date_key(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _date_in_range(value: str, start: str, end: str) -> bool:
    day = _parse_date(value)
    start_day = _parse_date(start)
    end_day = _parse_date(end)
    if day is None or start_day is None or end_day is None:
        return False
    return start_day <= day <= end_day


def _span_days(start: str, end: str) -> int:
    start_day = _parse_date(start)
    end_day = _parse_date(end)
    if start_day is None or end_day is None:
        return 999999
    return max(0, (end_day - start_day).days)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_meta(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "source_path": str(path),
        "source_sha256": _sha256(path),
        "source_mtime": int(stat.st_mtime),
        "source_size_bytes": stat.st_size,
    }


def _normalize_store(source_store: Any, merchant_id: Any) -> str:
    store = _upper(source_store)
    merchant = str(merchant_id or "").strip()
    if store in {"30137883", "ACMEWEAR"} or merchant == "759051":
        return "ACMEWEAR"
    if store in {"30000002", "STORE-B", "STOREB"} or merchant == "1065684":
        return "STOREB"
    return store or "UNKNOWN"


def _load_article_map(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "dim_kaspi_article_map"):
        return {}
    rows = conn.execute(
        """
        SELECT kaspi_article, sku_key
        FROM dim_kaspi_article_map
        WHERE COALESCE(kaspi_article, '') <> ''
          AND COALESCE(sku_key, '') <> ''
        """
    ).fetchall()
    return {_upper(row["kaspi_article"]): str(row["sku_key"]) for row in rows}


def _load_owner_product_code_map(path: Path | None) -> dict[tuple[str, str], dict[str, str]]:
    if path is None:
        return {}
    if not path.exists():
        raise RuntimeError(f"owner product-code map not found: {path}")
    out: dict[tuple[str, str], dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            store = _upper(
                row.get("business_store_code")
                or row.get("store_code")
                or row.get("store")
                or "STOREB"
            )
            product_code = _upper(
                row.get("kaspi_product_code")
                or row.get("product_code")
                or row.get("kaspi_article")
            )
            sku_key = str(
                row.get("owner_selected_sku_key")
                or row.get("sku_key")
                or row.get("selected_sku_key")
                or ""
            ).strip()
            if not product_code:
                continue
            if not sku_key or sku_key in {"OWNER_DECISION_REQUIRED", "KEEP_BLOCKED"}:
                continue
            key = (store, product_code)
            existing = out.get(key)
            if existing and existing["sku_key"] != sku_key:
                raise RuntimeError(
                    f"conflicting owner mapping for {store}/{product_code} in {path} line {line_number}"
                )
            out[key] = {
                "business_store_code": store,
                "kaspi_product_code": product_code,
                "sku_key": sku_key,
                "mapping_method": str(
                    row.get("mapping_method") or "OWNER_CONFIRMED_PRODUCT_CODE_MAP"
                ).strip(),
                "decision_token": str(row.get("decision_token") or "").strip(),
                "owner_response_quote": str(row.get("owner_response_quote") or "").strip(),
                "source_path": str(path),
                "line_number": str(line_number),
            }
    return out


def _assert_owner_map_non_conflicting(
    *,
    owner_product_code_map: dict[tuple[str, str], dict[str, str]],
    article_map: dict[str, str],
) -> None:
    for (_store, product_code), mapping in owner_product_code_map.items():
        article_sku = article_map.get(product_code)
        owner_sku = str(mapping.get("sku_key") or "").strip()
        if article_sku and owner_sku and article_sku != owner_sku:
            raise RuntimeError(
                "owner product-code map conflicts with dim_kaspi_article_map "
                f"for {product_code}: owner={owner_sku} article_map={article_sku}"
            )


def _add_token_source(
    sources: dict[str, list[dict[str, Any]]],
    *,
    token: Any,
    sku_key: Any,
    store_code: Any,
    method: str,
    source_table: str,
    evidence_rows: int,
) -> None:
    token_key = _upper(token)
    sku = str(sku_key or "").strip()
    if not token_key or not sku:
        return
    sources.setdefault(token_key, []).append(
        {
            "sku_key": sku,
            "store_code": _normalize_store(store_code, None),
            "method": method,
            "source_table": source_table,
            "evidence_rows": int(evidence_rows or 0),
        }
    )


def _load_exact_token_sources(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    sources: dict[str, list[dict[str, Any]]] = {}
    if _table_exists(conn, "dim_kaspi_article_map"):
        cols = _columns(conn, "dim_kaspi_article_map")
        active_filter = "AND COALESCE(active_flag, 1) = 1" if "active_flag" in cols else ""
        rows = conn.execute(
            f"""
            SELECT kaspi_article, sku_key, store_code, COUNT(*) AS evidence_rows
            FROM dim_kaspi_article_map
            WHERE COALESCE(kaspi_article, '') <> ''
              AND COALESCE(sku_key, '') <> ''
              {active_filter}
            GROUP BY kaspi_article, sku_key, store_code
            """
        ).fetchall()
        for row in rows:
            _add_token_source(
                sources,
                token=row["kaspi_article"],
                sku_key=row["sku_key"],
                store_code=row["store_code"],
                method="EXACT_RELATED_ARTICLE_MAP",
                source_table="dim_kaspi_article_map",
                evidence_rows=row["evidence_rows"],
            )

    if _table_exists(conn, "fact_order_entries_kaspi") and _table_exists(conn, "fact_orders_kaspi"):
        entry_cols = _columns(conn, "fact_order_entries_kaspi")
        order_cols = _columns(conn, "fact_orders_kaspi")
        required = {"order_id", "store_code"}
        if required.issubset(entry_cols) and required.issubset(order_cols) and "sku_key" in order_cols:
            for token_col in ("offer_id", "product_id"):
                if token_col not in entry_cols:
                    continue
                rows = conn.execute(
                    f"""
                    SELECT
                        e.{token_col} AS token,
                        o.sku_key AS sku_key,
                        e.store_code AS store_code,
                        COUNT(*) AS evidence_rows
                    FROM fact_order_entries_kaspi e
                    JOIN fact_orders_kaspi o
                      ON o.order_id = e.order_id
                     AND o.store_code = e.store_code
                    WHERE COALESCE(e.{token_col}, '') <> ''
                      AND COALESCE(o.sku_key, '') <> ''
                    GROUP BY e.{token_col}, o.sku_key, e.store_code
                    """
                ).fetchall()
                for row in rows:
                    _add_token_source(
                        sources,
                        token=row["token"],
                        sku_key=row["sku_key"],
                        store_code=row["store_code"],
                        method="EXACT_ORDER_ENTRY_SALES_JOIN",
                        source_table=f"fact_order_entries_kaspi.{token_col}+fact_orders_kaspi",
                        evidence_rows=row["evidence_rows"],
                    )
    return sources


def _resolve_sku_key(row: dict[str, Any], article_map: dict[str, str]) -> str | None:
    resolved = str(row.get("resolved_sku_key") or "").strip()
    if resolved:
        return resolved
    for key in (
        "json_merchant_sku",
        "merchant_article",
        "merchant_sku",
        "sku_key",
        "json_sku",
        "kaspi_product_code",
    ):
        token = _upper(row.get(key))
        if token and token in article_map:
            return article_map[token]
    return None


def _split_related_order_products(value: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in str(value or "").split(","):
        clean = token.strip()
        if not clean:
            continue
        key = _upper(clean)
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _resolve_related_token(
    *,
    token: str,
    business_store: str,
    token_sources: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    candidates = token_sources.get(_upper(token), [])
    if not candidates:
        return {
            "token": token,
            "status": "UNRESOLVED",
            "sku_key": "",
            "sources": [],
        }
    store_candidates = [
        row for row in candidates if _normalize_store(row.get("store_code"), None) == business_store
    ]
    usable = store_candidates or candidates
    sku_keys = sorted({str(row.get("sku_key") or "").strip() for row in usable if row.get("sku_key")})
    if len(sku_keys) != 1:
        return {
            "token": token,
            "status": "CONFLICT",
            "sku_key": "",
            "sources": usable,
        }
    return {
        "token": token,
        "status": "RESOLVED",
        "sku_key": sku_keys[0],
        "sources": usable,
    }


def _build_product_code_enrichment(
    *,
    source_rows: list[dict[str, Any]],
    token_sources: dict[str, list[dict[str, Any]]],
    owner_product_code_map: dict[tuple[str, str], dict[str, str]],
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in source_rows:
        business_store = str(row.get("business_store_code") or "")
        product_code = str(row.get("kaspi_product_code") or "").strip()
        if business_store != "STOREB" or not product_code:
            continue
        key = (business_store, product_code)
        item = grouped.setdefault(
            key,
            {
                "business_store_code": business_store,
                "kaspi_product_code": product_code,
                "product_name": str(row.get("product_name") or ""),
                "campaign_id": str(row.get("campaign_id") or ""),
                "campaign_name": str(row.get("campaign_name") or ""),
                "access_store_code": str(row.get("access_store_code") or ""),
                "source_path": str(row.get("source_path") or ""),
                "tokens": [],
                "source_row_count": 0,
            },
        )
        item["source_row_count"] += 1
        for token in _split_related_order_products(row.get("related_order_products")):
            if _upper(token) not in {_upper(existing) for existing in item["tokens"]}:
                item["tokens"].append(token)

    rows: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for key, item in sorted(grouped.items(), key=lambda entry: entry[0]):
        owner_mapping = owner_product_code_map.get((_upper(key[0]), _upper(key[1])))
        tokens = item["tokens"]
        resolved_tokens = [
            _resolve_related_token(
                token=token,
                business_store=item["business_store_code"],
                token_sources=token_sources,
            )
            for token in tokens
        ]
        unresolved = [row for row in resolved_tokens if row["status"] == "UNRESOLVED"]
        token_conflicts = [row for row in resolved_tokens if row["status"] == "CONFLICT"]
        sku_keys = sorted(
            {
                str(row.get("sku_key") or "").strip()
                for row in resolved_tokens
                if row.get("sku_key")
            }
        )
        method_set = sorted(
            {
                str(source.get("method") or "")
                for row in resolved_tokens
                for source in row.get("sources", [])
                if source.get("method")
            }
        )
        if owner_mapping:
            mapping_status = "MAPPED"
            reason = ""
            sku_key = str(owner_mapping["sku_key"])
            if token_conflicts or (sku_keys and set(sku_keys) != {sku_key}):
                raise RuntimeError(
                    "owner product-code map conflicts with deterministic related-token evidence "
                    f"for {item['business_store_code']}/{item['kaspi_product_code']}"
                )
            sku_keys = [sku_key]
            method_set = [str(owner_mapping.get("mapping_method") or "OWNER_CONFIRMED_PRODUCT_CODE_MAP")]
            resolved_tokens = [
                {
                    "token": item["kaspi_product_code"],
                    "status": "OWNER_CONFIRMED",
                    "sku_key": sku_key,
                    "sources": [
                        {
                            "method": method_set[0],
                            "source_table": "owner_product_code_map_csv",
                            "source_path": owner_mapping.get("source_path"),
                            "decision_token": owner_mapping.get("decision_token"),
                            "owner_response_quote": owner_mapping.get("owner_response_quote"),
                            "line_number": owner_mapping.get("line_number"),
                        }
                    ],
                }
            ]
        elif not tokens:
            mapping_status = "BLOCKED_NO_RELATED_PRODUCTS"
            reason = "ADS_MAPPING_MISSING"
            sku_key = ""
        elif unresolved:
            mapping_status = "BLOCKED_UNRESOLVED_RELATED_PRODUCTS"
            reason = "ADS_MAPPING_MISSING"
            sku_key = ""
        elif token_conflicts or len(sku_keys) > 1:
            mapping_status = "BLOCKED_CONFLICT"
            reason = "ADS_MAPPING_CONFLICT"
            sku_key = ""
        else:
            mapping_status = "MAPPED"
            reason = ""
            sku_key = sku_keys[0]

        mapping_method = "+".join(method_set) if mapping_status == "MAPPED" else ""
        mapping = {
            **item,
            "sku_key": sku_key,
            "mapping_status": mapping_status,
            "mapping_method": mapping_method,
            "unmapped_reason": reason,
            "related_order_products": ", ".join(tokens),
            "related_order_products_json": json.dumps(tokens, ensure_ascii=False, sort_keys=True),
            "resolved_token_evidence_json": json.dumps(
                resolved_tokens,
                ensure_ascii=False,
                sort_keys=True,
            ),
            "candidate_sku_keys_json": json.dumps(sku_keys, sort_keys=True),
        }
        rows.append(mapping)
        by_key[key] = mapping
    return {"rows": rows, "by_key": by_key}


def _select_existing_columns(conn: sqlite3.Connection, table: str, wanted: list[str]) -> list[str]:
    cols = _columns(conn, table)
    return [col for col in wanted if col in cols]


def _load_standard_daily_source_rows(
    conn: sqlite3.Connection,
    path: Path,
    *,
    table: str,
    start: str,
    end: str,
    stores: set[str],
    meta: dict[str, Any],
) -> list[dict[str, Any]]:
    wanted = [
        "date",
        "merchant_id",
        "store_code",
        "campaign_id",
        "campaign_name",
        "sku_key",
        "json_sku",
        "json_merchant_sku",
        "views",
        "clicks",
        "cost",
    ]
    select_cols = _select_existing_columns(conn, table, wanted)
    if not select_cols:
        return []
    if table == "campaign_product_rows":
        date_filter = (
            "COALESCE(TRIM(date), '') <> '' "
            "AND date(date) >= date(?) AND date(date) <= date(?)"
        )
    else:
        date_filter = "date(date) >= date(?) AND date(date) <= date(?)"
    query_rows = conn.execute(
        f"""
        SELECT {", ".join(select_cols)}
        FROM {table}
        WHERE {date_filter}
        ORDER BY date, store_code, campaign_id, sku_key
        """,
        (start, end),
    ).fetchall()
    rows_out: list[dict[str, Any]] = []
    for raw in query_rows:
        row = dict(raw)
        business_store = _normalize_store(row.get("store_code"), row.get("merchant_id"))
        if business_store not in stores:
            continue
        rows_out.append(
            {
                **row,
                "business_store_code": business_store,
                "access_store_code": str(row.get("store_code") or ""),
                "source_table": table,
                **meta,
            }
        )
    return rows_out


def _load_live_chrome_source_rows(
    conn: sqlite3.Connection,
    path: Path,
    *,
    start: str,
    end: str,
    stores: set[str],
    meta: dict[str, Any],
) -> list[dict[str, Any]]:
    table = "campaign_product_report_daily_live_chrome"
    if not _table_exists(conn, table):
        return []
    wanted = [
        "business_store_code",
        "access_store_code",
        "api_merchant_id",
        "campaign_id",
        "campaign_name",
        "date",
        "kaspi_product_code",
        "merchant_article",
        "merchant_sku",
        "product_name",
        "related_order_products",
        "views",
        "clicks",
        "ad_cost_kzt",
        "raw_payload_path",
        "normalized_csv_path",
        "source_captured_at",
        "coverage_classification_source_grain",
    ]
    select_cols = _select_existing_columns(conn, table, wanted)
    if not select_cols:
        return []
    query_rows = conn.execute(
        f"""
        SELECT {", ".join(select_cols)}
        FROM {table}
        WHERE date(date) >= date(?) AND date(date) <= date(?)
        ORDER BY date, business_store_code, campaign_id, kaspi_product_code
        """,
        (start, end),
    ).fetchall()
    rows_out: list[dict[str, Any]] = []
    for raw in query_rows:
        row = dict(raw)
        business_store = _normalize_store(row.get("business_store_code"), row.get("api_merchant_id"))
        if business_store not in stores:
            continue
        product_code = str(row.get("kaspi_product_code") or "").strip()
        rows_out.append(
            {
                "date": row.get("date"),
                "merchant_id": row.get("api_merchant_id"),
                "store_code": business_store,
                "campaign_id": row.get("campaign_id"),
                "campaign_name": row.get("campaign_name"),
                "sku_key": product_code,
                "json_sku": product_code,
                "json_merchant_sku": row.get("merchant_sku"),
                "merchant_article": row.get("merchant_article"),
                "merchant_sku": row.get("merchant_sku"),
                "kaspi_product_code": product_code,
                "product_name": row.get("product_name"),
                "related_order_products": row.get("related_order_products"),
                "views": row.get("views"),
                "clicks": row.get("clicks"),
                "cost": row.get("ad_cost_kzt"),
                "business_store_code": business_store,
                "access_store_code": str(row.get("access_store_code") or ""),
                "source_table": table,
                "source_raw_payload_path": row.get("raw_payload_path"),
                "source_normalized_csv_path": row.get("normalized_csv_path"),
                "source_captured_at": row.get("source_captured_at"),
                "source_coverage_classification": row.get("coverage_classification_source_grain"),
                **meta,
            }
        )
    return rows_out


def _load_acmewear_sku_daily_classification_rows(
    conn: sqlite3.Connection,
    path: Path,
    *,
    start: str,
    end: str,
    stores: set[str],
    meta: dict[str, Any],
) -> list[dict[str, Any]]:
    table = "sku_daily_evidence_classification"
    if "ACMEWEAR" not in stores or not _table_exists(conn, table):
        return []
    wanted = [
        "date",
        "required_window",
        "target_sku_key",
        "target_group",
        "classification",
        "supports_clear",
        "evidence_source",
        "matched_rows",
        "matched_campaign_ids",
        "matched_json_merchant_skus",
        "cost_sum",
        "views_sum",
        "clicks_sum",
        "raw_paths",
        "notes",
    ]
    select_cols = _select_existing_columns(conn, table, wanted)
    required = {"date", "target_sku_key", "classification", "supports_clear"}
    if not required.issubset(set(select_cols)):
        return []
    query_rows = conn.execute(
        f"""
        SELECT {", ".join(select_cols)}
        FROM {table}
        WHERE date(date) >= date(?) AND date(date) <= date(?)
        ORDER BY date, target_sku_key
        """,
        (start, end),
    ).fetchall()
    rows_out: list[dict[str, Any]] = []
    clear_zero_classes = {
        "ABSENT_FROM_FULL_STORE_DAILY_PRODUCT_UNIVERSE",
        "NO_SPEND_VERIFIED_PRODUCT_ZERO",
    }
    for raw in query_rows:
        row = dict(raw)
        classification = _upper(row.get("classification"))
        if classification not in clear_zero_classes:
            continue
        if not _supports_absence_no_spend(row.get("supports_clear")):
            continue
        target_sku = str(row.get("target_sku_key") or "").strip()
        date_key = _date_key(row.get("date"))
        if not target_sku or not date_key:
            continue
        required_window = str(row.get("required_window") or date_key).strip() or date_key
        rows_out.append(
            {
                "date": date_key,
                "merchant_id": "759051",
                "store_code": "ACMEWEAR",
                "campaign_id": f"CLASSIFICATION:{classification}:{required_window}",
                "campaign_name": "Full-store SKU no-spend classification",
                "sku_key": target_sku,
                "resolved_sku_key": target_sku,
                "json_sku": target_sku,
                "json_merchant_sku": row.get("matched_json_merchant_skus"),
                "views": row.get("views_sum"),
                "clicks": row.get("clicks_sum"),
                "cost": 0.0,
                "business_store_code": "ACMEWEAR",
                "access_store_code": "ACMEWEAR",
                "source_table": table,
                "source_required_window": required_window,
                "source_classification": classification,
                "source_raw_paths": row.get("raw_paths"),
                "source_notes": row.get("notes"),
                **meta,
            }
        )
    return rows_out


def _load_campaign_daily_refresh_only_rows(
    conn: sqlite3.Connection,
    path: Path,
    *,
    start: str,
    end: str,
    stores: set[str],
    meta: dict[str, Any],
) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for table in ("campaign_daily_current", "campaign_daily_history"):
        if not _table_exists(conn, table):
            continue
        cols = _columns(conn, table)
        if "date" not in cols:
            continue
        select_cols = _select_existing_columns(
            conn,
            table,
            ["date", "merchant_id", "store_code", "campaign_id", "cost", "record_timestamp", "ingested_at"],
        )
        if "date" not in select_cols:
            continue
        rows = conn.execute(
            f"""
            SELECT {", ".join(select_cols)}
            FROM {table}
            WHERE date(date) >= date(?) AND date(date) <= date(?)
            ORDER BY date
            """,
            (start, end),
        ).fetchall()
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for raw in rows:
            row = dict(raw)
            date_key = _date_key(row.get("date"))
            business_store = _normalize_store(row.get("store_code"), row.get("merchant_id"))
            if not date_key or business_store not in stores or not is_store_active_on(business_store, date_key):
                continue
            key = (business_store, date_key)
            current = grouped.setdefault(
                key,
                {
                    "date": date_key,
                    "business_store_code": business_store,
                    "merchant_id": str(row.get("merchant_id") or ""),
                    "source_table": table,
                    "refresh_only": True,
                    "refresh_row_count": 0,
                    "campaign_ids": set(),
                    "cost_sum": 0.0,
                    **meta,
                },
            )
            current["refresh_row_count"] += 1
            if row.get("campaign_id"):
                current["campaign_ids"].add(str(row["campaign_id"]))
            current["cost_sum"] = round(float(current["cost_sum"]) + _to_float(row.get("cost")), 6)
        for item in grouped.values():
            item["campaign_ids_json"] = json.dumps(sorted(item.pop("campaign_ids")), sort_keys=True)
            rows_out.append(item)
        if rows_out:
            break
    return rows_out


def _source_rows_from_db(
    path: Path,
    *,
    start: str,
    end: str,
    stores: set[str],
    allow_campaign_daily_refresh_only: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows_out: list[dict[str, Any]] = []
    unmapped_source: list[dict[str, Any]] = []
    if not path.exists():
        return rows_out, [{"source_path": str(path), "reason": "SOURCE_DB_MISSING"}]
    with _connect(path) as conn:
        source_tables_seen = False
        meta = _source_meta(path)
        for table in ("campaign_product_daily_current", "campaign_product_rows", "campaign_product_daily"):
            if not _table_exists(conn, table):
                continue
            source_tables_seen = True
            rows_out.extend(
                _load_standard_daily_source_rows(
                    conn,
                    path,
                    table=table,
                    start=start,
                    end=end,
                    stores=stores,
                    meta=meta,
                )
            )
        if _table_exists(conn, "sku_daily_evidence_classification"):
            source_tables_seen = True
            rows_out.extend(
                _load_acmewear_sku_daily_classification_rows(
                    conn,
                    path,
                    start=start,
                    end=end,
                    stores=stores,
                    meta=meta,
                )
            )
        if _table_exists(conn, "campaign_product_report_daily_live_chrome"):
            source_tables_seen = True
            rows_out.extend(
                _load_live_chrome_source_rows(
                    conn,
                    path,
                    start=start,
                    end=end,
                    stores=stores,
                    meta=meta,
                )
            )
        if allow_campaign_daily_refresh_only:
            refresh_only = _load_campaign_daily_refresh_only_rows(
                conn,
                path,
                start=start,
                end=end,
                stores=stores,
                meta=meta,
            )
            if refresh_only:
                source_tables_seen = True
                rows_out.extend(refresh_only)
        if not source_tables_seen:
            return rows_out, [{"source_path": str(path), "reason": "SOURCE_TABLE_MISSING"}]
    return rows_out, unmapped_source


def _source_rows_from_child_registry(
    path: Path | None,
    *,
    start: str,
    end: str,
    stores: set[str],
) -> list[dict[str, Any]]:
    if path is None or not path.exists() or "ACMEWEAR" not in stores:
        return []
    meta = _source_meta(path)
    out: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            created = str(row.get("created_at_utc") or "")[:10]
            if not created or created < start or created > end:
                continue
            out.append(
                {
                    "date": created,
                    "merchant_id": "759051",
                    "store_code": "ACMEWEAR",
                    "campaign_id": row.get("campaign_id"),
                    "campaign_name": row.get("campaign_name"),
                    "sku_key": row.get("campaign_product_sku"),
                    "json_sku": row.get("campaign_product_sku"),
                    "json_merchant_sku": row.get("merchant_article"),
                    "merchant_article": row.get("merchant_article"),
                    "views": 0,
                    "clicks": 0,
                    "cost": 0.0,
                    "business_store_code": "ACMEWEAR",
                    "access_store_code": "ACMEWEAR",
                    "source_table": "acmewear_child_bundle_campaign_registry.csv",
                    **meta,
                }
            )
    return out


def _supports_absence_no_spend(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith("yes") or text in {"1", "true", "y"}


def _aggregate_refresh_run_id(store_code: str, window_id: str) -> str:
    safe_window = str(window_id or "unknown").strip().replace(" ", "_")
    return f"agent20-ads-source-{store_code.lower()}-{safe_window}"


def _load_active_sale_keys(
    conn: sqlite3.Connection,
    *,
    start: str,
    end: str,
    stores: set[str],
) -> list[dict[str, str]]:
    if not _table_exists(conn, "sales_fact_v2"):
        return []
    cols = _columns(conn, "sales_fact_v2")
    if "order_date" not in cols or "sku_key" not in cols:
        return []

    clauses = [
        "date(order_date) >= date(?)",
        "date(order_date) <= date(?)",
        f"UPPER(COALESCE(status, '')) IN ({','.join(repr(s) for s in sorted(DELIVERED_SALES_STATUSES))})",
        "COALESCE(sku_key, '') <> ''",
    ]
    if "return_flag" in cols:
        clauses.append("COALESCE(return_flag, 0) = 0")
    rows = conn.execute(
        f"""
        SELECT DISTINCT
            date(order_date) AS sale_date,
            COALESCE(store_code, 'UNIVERSAL') AS store_code,
            COALESCE(sku_key, '') AS sku_key
        FROM sales_fact_v2
        WHERE {' AND '.join(clauses)}
        ORDER BY sale_date, store_code, sku_key
        """,
        (start, end),
    ).fetchall()
    out: list[dict[str, str]] = []
    for row in rows:
        sale_date = _date_key(row["sale_date"])
        store_code = _normalize_store(row["store_code"], None)
        sku_key = str(row["sku_key"] or "").strip()
        if store_code not in stores or not sale_date or not sku_key:
            continue
        if not is_store_active_on(store_code, sale_date):
            continue
        out.append({"date": sale_date, "store_code": store_code, "sku_key": sku_key})
    return out


def _load_completed_aggregate_windows(
    path: Path,
    *,
    article_map: dict[str, str],
    stores: set[str],
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with _connect(path) as conn:
        if not _table_exists(conn, "window_completeness") or not _table_exists(conn, "campaign_product_rows"):
            return []
        windows = conn.execute(
            """
            SELECT *
            FROM window_completeness
            WHERE COALESCE(window_id, '') <> ''
            ORDER BY start_date, end_date, window_id
            """
        ).fetchall()
        product_cols = _columns(conn, "campaign_product_rows")
        wanted = [
            "window_id",
            "window_type",
            "date",
            "start_date",
            "end_date",
            "merchant_id",
            "store_code",
            "campaign_id",
            "campaign_name",
            "sku_key",
            "json_sku",
            "json_merchant_sku",
            "views",
            "clicks",
            "cost",
            "raw_path",
        ]
        select_cols = [col for col in wanted if col in product_cols]
        if not select_cols:
            return []
        meta = _source_meta(path)
        out: list[dict[str, Any]] = []
        for raw_window in windows:
            window = dict(raw_window)
            window_id = str(window.get("window_id") or "").strip()
            date_start = _date_key(window.get("start_date"))
            date_end = _date_key(window.get("end_date"))
            if _upper(window.get("window_type")) != "AGGREGATE":
                continue
            if _upper(window.get("completeness_status")) != "FULL_STORE_PRODUCT_ROWS_COMPLETE":
                continue
            if not _supports_absence_no_spend(window.get("supports_absence_no_spend_verified")):
                continue
            if not date_start or not date_end:
                continue
            query_rows = conn.execute(
                f"""
                SELECT {", ".join(select_cols)}
                FROM campaign_product_rows
                WHERE window_id = ?
                  AND COALESCE(TRIM(date), '') = ''
                ORDER BY store_code, campaign_id, sku_key
                """,
                (window_id,),
            ).fetchall()
            by_store: dict[str, dict[str, Any]] = {}
            for raw_row in query_rows:
                row = dict(raw_row)
                business_store = _normalize_store(row.get("store_code"), row.get("merchant_id"))
                if business_store not in stores:
                    continue
                store_window = by_store.setdefault(
                    business_store,
                    {
                        "window_id": window_id,
                        "store_code": business_store,
                        "merchant_id": "759051"
                        if business_store == "ACMEWEAR"
                        else "1065684"
                        if business_store == "STOREB"
                        else str(row.get("merchant_id") or ""),
                        "date_start": date_start,
                        "date_end": date_end,
                        "fetched_at": str(window.get("fetched_at") or ""),
                        "product_rows_total": 0,
                        "sku_cost": {},
                        "sku_source_paths": {},
                        "raw_paths": set(),
                        "unmapped_product_rows": 0,
                        **meta,
                    },
                )
                store_window["product_rows_total"] += 1
                raw_path = str(row.get("raw_path") or "").strip()
                if raw_path:
                    store_window["raw_paths"].add(raw_path)
                sku_key = _resolve_sku_key(row, article_map)
                if not sku_key:
                    store_window["unmapped_product_rows"] += 1
                    continue
                store_window["sku_cost"][sku_key] = (
                    _to_float(store_window["sku_cost"].get(sku_key)) + _to_float(row.get("cost"))
                )
                store_window["sku_source_paths"].setdefault(sku_key, set())
                if raw_path:
                    store_window["sku_source_paths"][sku_key].add(raw_path)
            for store_window in by_store.values():
                raw_paths = sorted(store_window["raw_paths"])
                sku_paths = {
                    sku_key: sorted(paths)
                    for sku_key, paths in store_window["sku_source_paths"].items()
                }
                store_window["raw_paths"] = raw_paths
                store_window["sku_source_paths"] = sku_paths
                out.append(store_window)
        return out


def _aggregate_refresh_row(window: dict[str, Any]) -> dict[str, Any]:
    store_code = str(window["store_code"])
    window_id = str(window["window_id"])
    date_start = str(window["date_start"])
    date_end = str(window["date_end"])
    finished_at = str(window.get("fetched_at") or "").strip() or f"{date_end}T23:59:59+05:00"
    notes = {
        "materializer": "materialize_ads_campaign_product_daily",
        "source_evidence": "full_store_aggregate_product_universe",
        "source_window_id": window_id,
        "source_path": window.get("source_path"),
        "source_sha256": window.get("source_sha256"),
        "source_raw_paths": window.get("raw_paths") or [],
        "no_fake_zero_spend": True,
        "positive_aggregate_spend_not_fanned_out": True,
        "unmapped_product_rows": int(window.get("unmapped_product_rows") or 0),
    }
    return {
        "run_id": _aggregate_refresh_run_id(store_code, window_id),
        "started_at": f"{date_start}T00:00:00+05:00",
        "finished_at": finished_at,
        "merchant_id": str(window.get("merchant_id") or ""),
        "store_code": store_code,
        "date_start": date_start,
        "date_end": date_end,
        "product_rows_total": int(window.get("product_rows_total") or 0),
        "status": "SUCCESS",
        "notes_json": json.dumps(notes, sort_keys=True),
    }


def _build_aggregate_no_spend_rows(
    *,
    windows: list[dict[str, Any]],
    sale_keys: list[dict[str, str]],
    covered_keys: set[tuple[str, str, str]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    generated: list[dict[str, Any]] = []
    counters = {
        "aggregate_windows_used": 0,
        "aggregate_no_spend_rows": 0,
        "aggregate_absence_rows": 0,
        "aggregate_zero_rows": 0,
        "aggregate_positive_spend_blocked": 0,
    }
    if not windows or not sale_keys:
        return generated, counters

    sorted_windows = sorted(
        windows,
        key=lambda window: (
            _span_days(str(window["date_start"]), str(window["date_end"])),
            str(window["date_start"]),
            str(window["window_id"]),
        ),
    )
    used_windows: set[str] = set()
    generated_keys: set[tuple[str, str, str]] = set()
    for sale in sale_keys:
        sale_date = sale["date"]
        store_code = sale["store_code"]
        sku_key = sale["sku_key"]
        sale_key = (sale_date, store_code, sku_key)
        if sale_key in covered_keys or sale_key in generated_keys:
            continue
        for window in sorted_windows:
            if store_code != window["store_code"]:
                continue
            if not _date_in_range(sale_date, str(window["date_start"]), str(window["date_end"])):
                continue
            sku_cost = window["sku_cost"]
            source_paths = [str(window.get("source_path") or "")]
            if sku_key in sku_cost:
                if _to_float(sku_cost[sku_key]) > 0:
                    counters["aggregate_positive_spend_blocked"] += 1
                    break
                evidence_type = "AGGREGATE_ZERO_PRODUCT_ROWS"
                campaign_id = f"AGGREGATE_ZERO:{window['window_id']}"
                campaign_name = "Full-store aggregate zero-spend proof"
                source_paths.extend(window.get("sku_source_paths", {}).get(sku_key, []))
                counters["aggregate_zero_rows"] += 1
            else:
                evidence_type = "ABSENT_FROM_FULL_STORE_PRODUCT_UNIVERSE"
                campaign_id = f"AGGREGATE_ABSENCE:{window['window_id']}"
                campaign_name = "Full-store aggregate absence proof"
                source_paths.extend(window.get("raw_paths") or [])
                counters["aggregate_absence_rows"] += 1

            source_run_id = _aggregate_refresh_run_id(store_code, str(window["window_id"]))
            source_paths = [path for path in source_paths if path]
            generated.append(
                {
                    "date": sale_date,
                    "store_code": store_code,
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "source_sku_key": "",
                    "json_merchant_sku": "",
                    "merchant_id": str(window.get("merchant_id") or ""),
                    "access_store_code": store_code,
                    "source_table": "window_completeness+campaign_product_rows",
                    "source_path": window.get("source_path"),
                    "source_sha256": window.get("source_sha256"),
                    "source_mtime": window.get("source_mtime"),
                    "source_size_bytes": window.get("source_size_bytes"),
                    "sku_key": sku_key,
                    "cost_kzt": 0.0,
                    "impressions": 0,
                    "clicks": 0,
                    "coverage_status": "NO_SPEND_VERIFIED",
                    "source_run_id": source_run_id,
                    "source_window_id": window["window_id"],
                    "source_window_start": window["date_start"],
                    "source_window_end": window["date_end"],
                    "aggregate_evidence_type": evidence_type,
                    "source_paths_json": json.dumps(sorted(set(source_paths)), sort_keys=True),
                }
            )
            generated_keys.add(sale_key)
            used_windows.add(str(window["window_id"]))
            counters["aggregate_no_spend_rows"] += 1
            break
    counters["aggregate_windows_used"] = len(used_windows)
    return generated, counters


def _coalesce_mapped_product_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["date"]),
            str(row["store_code"]),
            str(row["campaign_id"]),
            str(row["sku_key"]),
        )
        target = grouped.setdefault(
            key,
            {
                **row,
                "cost_kzt": 0.0,
                "impressions": 0,
                "clicks": 0,
                "source_row_count": 0,
                "_source_sku_keys": set(),
                "_json_merchant_skus": set(),
                "_mapping_methods": set(),
                "_source_paths": set(),
            },
        )
        target["cost_kzt"] = round(_to_float(target["cost_kzt"]) + _to_float(row.get("cost_kzt")), 2)
        target["impressions"] = _to_int(target["impressions"]) + _to_int(row.get("impressions"))
        target["clicks"] = _to_int(target["clicks"]) + _to_int(row.get("clicks"))
        target["source_row_count"] += 1
        for field, bucket in (
            ("source_sku_key", "_source_sku_keys"),
            ("json_merchant_sku", "_json_merchant_skus"),
            ("mapping_method", "_mapping_methods"),
            ("source_path", "_source_paths"),
        ):
            value = str(row.get(field) or "").strip()
            if value:
                target[bucket].add(value)

    out: list[dict[str, Any]] = []
    for row in grouped.values():
        row["coverage_status"] = (
            "COVERED" if _to_float(row.get("cost_kzt")) > 0 else "NO_SPEND_VERIFIED"
        )
        row["source_sku_key"] = ",".join(sorted(row.pop("_source_sku_keys")))
        row["json_merchant_sku"] = ",".join(sorted(row.pop("_json_merchant_skus")))
        row["mapping_method"] = "+".join(sorted(row.pop("_mapping_methods")))
        row["source_paths_json"] = json.dumps(sorted(row.pop("_source_paths")), sort_keys=True)
        out.append(row)
    return sorted(
        out,
        key=lambda row: (
            str(row.get("date")),
            str(row.get("store_code")),
            str(row.get("campaign_id")),
            str(row.get("sku_key")),
        ),
    )


def _build_plan(
    *,
    app_db: Path,
    source_dbs: list[Path],
    child_registry: Path | None,
    stores: list[str],
    start: str,
    end: str,
    owner_product_code_map_path: Path | None,
    allow_campaign_daily_refresh_only: bool,
) -> dict[str, Any]:
    with _connect(app_db) as app:
        article_map = _load_article_map(app)
        owner_product_code_map = _load_owner_product_code_map(owner_product_code_map_path)
        _assert_owner_map_non_conflicting(
            owner_product_code_map=owner_product_code_map,
            article_map=article_map,
        )
        token_sources = _load_exact_token_sources(app)
        store_set = {_upper(store) for store in stores if _upper(store)}
        sale_keys = _load_active_sale_keys(app, start=start, end=end, stores=store_set)

    source_rows: list[dict[str, Any]] = []
    source_issues: list[dict[str, Any]] = []
    aggregate_windows: list[dict[str, Any]] = []
    for source_db in source_dbs:
        rows, issues = _source_rows_from_db(
            source_db,
            start=start,
            end=end,
            stores=store_set,
            allow_campaign_daily_refresh_only=allow_campaign_daily_refresh_only,
        )
        source_rows.extend(rows)
        source_issues.extend(issues)
        aggregate_windows.extend(
            _load_completed_aggregate_windows(source_db, article_map=article_map, stores=store_set)
        )
    source_rows.extend(_source_rows_from_child_registry(child_registry, start=start, end=end, stores=store_set))

    product_code_enrichment = _build_product_code_enrichment(
        source_rows=source_rows,
        token_sources=token_sources,
        owner_product_code_map=owner_product_code_map,
    )

    mapped_source_rows: list[dict[str, Any]] = []
    unmapped_rows: list[dict[str, Any]] = []
    refresh_key_counts: dict[tuple[str, str], int] = {}
    refresh_only_rows = 0
    for row in source_rows:
        if row.get("refresh_only"):
            business_store = str(row["business_store_code"])
            date_key = str(row.get("date") or "")[:10]
            if business_store and date_key:
                refresh_key_counts[(business_store, date_key)] = (
                    refresh_key_counts.get((business_store, date_key), 0)
                    + _to_int(row.get("refresh_row_count"))
                )
                refresh_only_rows += 1
            continue
        sku_key = _resolve_sku_key(row, article_map)
        business_store = row["business_store_code"]
        date_key = str(row.get("date") or "")[:10]
        product_code = str(row.get("kaspi_product_code") or "").strip()
        product_mapping = product_code_enrichment["by_key"].get((business_store, product_code))
        mapping_method = "DIRECT_ARTICLE_MAP" if sku_key else ""
        unmapped_reason = "ADS_MAPPING_MISSING"
        if not sku_key and product_mapping:
            if product_mapping["mapping_status"] == "MAPPED":
                sku_key = str(product_mapping["sku_key"])
                mapping_method = str(product_mapping.get("mapping_method") or "")
            else:
                unmapped_reason = str(product_mapping.get("unmapped_reason") or "ADS_MAPPING_MISSING")
        refresh_key_counts[(business_store, date_key)] = refresh_key_counts.get((business_store, date_key), 0) + 1
        base = {
            "date": date_key,
            "store_code": business_store,
            "campaign_id": str(row.get("campaign_id") or ""),
            "campaign_name": str(row.get("campaign_name") or ""),
            "source_sku_key": str(row.get("sku_key") or ""),
            "json_merchant_sku": str(row.get("json_merchant_sku") or ""),
            "kaspi_product_code": product_code,
            "product_name": str(row.get("product_name") or ""),
            "related_order_products": str(row.get("related_order_products") or ""),
            "mapping_method": mapping_method,
            "merchant_id": str(row.get("merchant_id") or ""),
            "access_store_code": str(row.get("access_store_code") or ""),
            "source_table": row.get("source_table"),
            "source_path": row.get("source_path"),
            "source_sha256": row.get("source_sha256"),
            "source_mtime": row.get("source_mtime"),
            "source_size_bytes": row.get("source_size_bytes"),
        }
        if not sku_key:
            unmapped_rows.append({**base, "reason": unmapped_reason})
            continue
        cost = _to_float(row.get("cost"))
        mapped_source_rows.append(
            {
                **base,
                "sku_key": sku_key,
                "cost_kzt": round(cost, 2),
                "impressions": _to_int(row.get("views")),
                "clicks": _to_int(row.get("clicks")),
                "coverage_status": "COVERED" if cost > 0 else "NO_SPEND_VERIFIED",
            }
        )

    mapped_rows = _coalesce_mapped_product_rows(mapped_source_rows)
    covered_keys = {
        (str(row["date"]), str(row["store_code"]), str(row["sku_key"]))
        for row in mapped_rows
    }
    aggregate_rows, aggregate_counters = _build_aggregate_no_spend_rows(
        windows=aggregate_windows,
        sale_keys=sale_keys,
        covered_keys=covered_keys,
    )
    mapped_rows.extend(aggregate_rows)

    refresh_rows = [
        {
            "run_id": f"agent12-ads-source-{store.lower()}-{date_key}",
            "started_at": f"{date_key}T00:00:00+05:00",
            "finished_at": f"{date_key}T23:59:59+05:00",
            "merchant_id": "759051" if store == "ACMEWEAR" else "1065684" if store == "STOREB" else "",
            "store_code": store,
            "date_start": date_key,
            "date_end": date_key,
            "product_rows_total": count,
            "status": "SUCCESS",
            "notes_json": json.dumps(
                {
                    "materializer": "materialize_ads_campaign_product_daily",
                    "source_evidence": "exact_campaign_product_rows_only",
                    "no_fake_zero_spend": True,
                },
                sort_keys=True,
            ),
        }
        for (store, date_key), count in sorted(refresh_key_counts.items())
        if date_key
    ]
    aggregate_refresh_rows = {
        row["run_id"]: row for row in (_aggregate_refresh_row(window) for window in aggregate_windows)
    }
    aggregate_refresh_run_ids = {
        str(row.get("source_run_id"))
        for row in aggregate_rows
        if str(row.get("source_run_id") or "")
    }
    refresh_rows.extend(
        row
        for run_id, row in sorted(aggregate_refresh_rows.items())
        if run_id in aggregate_refresh_run_ids
    )
    summary = {
        "source_rows": len(source_rows),
        "refresh_only_rows": refresh_only_rows,
        "mapped_rows": len(mapped_rows),
        "mapped_source_rows": len(mapped_source_rows),
        "unmapped_rows": len(unmapped_rows),
        "refresh_rows": len(refresh_rows),
        "stores": sorted(store_set),
        "start": start,
        "end": end,
        "source_issues": source_issues,
        "storeb_product_code_mappings_total": len(product_code_enrichment["rows"]),
        "owner_product_code_mappings_loaded": len(owner_product_code_map),
        "storeb_product_code_mappings_mapped": sum(
            1
            for row in product_code_enrichment["rows"]
            if row.get("mapping_status") == "MAPPED"
        ),
        "storeb_product_code_mappings_blocked": sum(
            1
            for row in product_code_enrichment["rows"]
            if row.get("mapping_status") != "MAPPED"
        ),
        "aggregate_windows_available": len(aggregate_windows),
        **aggregate_counters,
    }
    return {
        "summary": summary,
        "refresh_rows": refresh_rows,
        "mapped_rows": mapped_rows,
        "unmapped_rows": unmapped_rows,
        "product_code_mapping_rows": product_code_enrichment["rows"],
    }


def _insert_refresh(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO ads_source_refresh_runs (
            run_id, started_at, finished_at, merchant_id, store_code, date_start,
            date_end, product_rows_total, status, notes_json
        ) VALUES (
            :run_id, :started_at, :finished_at, :merchant_id, :store_code, :date_start,
            :date_end, :product_rows_total, :status, :notes_json
        )
        """,
        row,
    )


def _insert_product(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    source_run_id = str(
        row.get("source_run_id") or f"agent12-ads-source-{row['store_code'].lower()}-{row['date']}"
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO ads_campaign_product_daily (
            date, store_code, campaign_id, campaign_name, sku_key, cost_kzt,
            impressions, clicks, source_run_id, coverage_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["date"],
            row["store_code"],
            row["campaign_id"],
            row["campaign_name"],
            row["sku_key"],
            row["cost_kzt"],
            row["impressions"],
            row["clicks"],
            source_run_id,
            row["coverage_status"],
        ),
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _assert_apply_allowed(app_db: Path, *, env_gate_value: str | None) -> None:
    value = env_gate_value if env_gate_value is not None else os.environ.get(ENV_GATE)
    if value != "1":
        raise RuntimeError(f"{ENV_GATE}=1 is required for apply")
    if app_db.resolve() == DEFAULT_DB_PATH.resolve() and os.environ.get(PRODUCTION_ENV_GATE) != "1":
        raise RuntimeError(f"{PRODUCTION_ENV_GATE}=1 is required for production DB apply")


def materialize_ads_campaign_product_daily(
    *,
    app_db: Path,
    source_dbs: list[Path],
    child_registry: Path | None,
    stores: list[str],
    start: str,
    end: str,
    output_root: Path,
    apply: bool = False,
    env_gate_value: str | None = None,
    owner_product_code_map_path: Path | None = None,
    allow_campaign_daily_refresh_only: bool = False,
) -> dict[str, Any]:
    backup_path: Path | None = None
    if apply:
        _assert_apply_allowed(app_db, env_gate_value=env_gate_value)
        backup_path = backup_database(app_db, output_root / "backups", compress=False)

    plan = _build_plan(
        app_db=app_db,
        source_dbs=source_dbs,
        child_registry=child_registry,
        stores=stores,
        start=start,
        end=end,
        owner_product_code_map_path=owner_product_code_map_path,
        allow_campaign_daily_refresh_only=allow_campaign_daily_refresh_only,
    )
    if apply:
        with _connect(app_db) as conn:
            for row in plan["refresh_rows"]:
                _insert_refresh(conn, row)
            for row in plan["mapped_rows"]:
                _insert_product(conn, row)
            conn.commit()

    payload = {
        "summary": {**plan["summary"], "applied": apply},
        "app_db": str(app_db),
        "backup_path": str(backup_path) if backup_path else None,
        "outputs": {
            "mapped_rows_csv": str(output_root / "ads_campaign_product_daily_mapped.csv"),
            "unmapped_rows_csv": str(output_root / "ads_campaign_product_daily_unmapped.csv"),
            "refresh_rows_csv": str(output_root / "ads_source_refresh_runs.csv"),
            "storeb_product_code_mapping_csv": str(output_root / "storeb_product_code_mapping.csv"),
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "ads_materializer_summary.json", payload)
    _write_csv(output_root / "ads_campaign_product_daily_mapped.csv", plan["mapped_rows"])
    _write_csv(output_root / "ads_campaign_product_daily_unmapped.csv", plan["unmapped_rows"])
    _write_csv(output_root / "ads_source_refresh_runs.csv", plan["refresh_rows"])
    _write_csv(output_root / "storeb_product_code_mapping.csv", plan["product_code_mapping_rows"])
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize compact C3 ads campaign-product rows")
    parser.add_argument("--app-db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--external-marketing-db", type=Path, action="append", default=[])
    parser.add_argument("--webauto-marketing-db", type=Path, action="append", default=[])
    parser.add_argument("--child-registry", type=Path, default=None)
    parser.add_argument("--child-run-root", type=Path, default=None, help="Accepted for provenance compatibility")
    parser.add_argument("--stores", default="ACMEWEAR,STOREB")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--owner-product-code-map-csv", type=Path, default=None)
    parser.add_argument(
        "--allow-campaign-daily-refresh-only",
        action="store_true",
        help="Allow campaign_daily_current/history rows to create refresh coverage only.",
    )
    parser.add_argument("--report-path", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    source_dbs = [*args.external_marketing_db, *args.webauto_marketing_db]
    stores = [part.strip() for part in args.stores.split(",") if part.strip()]
    try:
        result = materialize_ads_campaign_product_daily(
            app_db=args.app_db,
            source_dbs=source_dbs,
            child_registry=args.child_registry,
            stores=stores,
            start=args.start,
            end=args.end,
            output_root=args.output_root,
            apply=args.apply,
            owner_product_code_map_path=args.owner_product_code_map_csv,
            allow_campaign_daily_refresh_only=args.allow_campaign_daily_refresh_only,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.report_path:
        _write_json(args.report_path, result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
