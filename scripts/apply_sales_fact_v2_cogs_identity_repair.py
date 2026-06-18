#!/usr/bin/env python3
"""Apply a narrow sales_fact_v2 identity repair for historical COGS completeness.

This writer only updates selected ``sales_fact_v2`` identity columns for rows
that are already present in the sales table and currently unresolved in
``view_sales_line_truth``. It does not create stock, COGS overrides, article-map
rows, workbook rows, or external-system writes.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
ENV_GATE = "ENABLE_SALES_FACT_V2_COGS_IDENTITY_REPAIR"
DEFAULT_START = "2026-03-01"
DEFAULT_END = "2026-06-14"
TARGET_SKU_KEYS = {"CL", "116515378", "132822924"}
SIZE_ORDER = ("4XL", "3XL", "2XL", "XL", "L", "M", "S", "XS")
NUMERIC_SIZE_MAP = {
    "42": "S",
    "44": "M",
    "46": "L",
    "48": "XL",
    "50": "XL",
    "52": "2XL",
    "54": "2XL",
    "56": "4XL",
    "58": "4XL",
    "60": "4XL",
}


class SalesIdentityRepairError(RuntimeError):
    """Raised when the sales identity repair is not safe."""


@dataclass(frozen=True)
class Candidate:
    sale_id: int
    order_id: str
    store_code: str
    order_date: str
    kaspi_offer_name: str
    old_sku_key: str
    old_sku_id: str
    old_my_size: str
    new_sku_key: str
    new_sku_id: str
    new_my_size: str
    evidence_source: str
    priority: int
    evidence_value: str = ""
    name_size: str = ""
    offer_size: str = ""
    old_size: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "sale_id": self.sale_id,
            "order_id": self.order_id,
            "store_code": self.store_code,
            "order_date": self.order_date,
            "kaspi_offer_name": self.kaspi_offer_name,
            "old_sku_key": self.old_sku_key,
            "old_sku_id": self.old_sku_id,
            "old_my_size": self.old_my_size,
            "new_sku_key": self.new_sku_key,
            "new_sku_id": self.new_sku_id,
            "new_my_size": self.new_my_size,
            "evidence_source": self.evidence_source,
            "priority": self.priority,
            "evidence_value": self.evidence_value,
            "name_size": self.name_size,
            "offer_size": self.offer_size,
            "old_size": self.old_size,
        }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_integrity_check(path: Path) -> str:
    conn = _connect(path, readonly=True)
    try:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    finally:
        conn.close()
    return str(row[0] if row else "")


def _sqlite_backup(src_path: Path, dst_path: Path) -> Path:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src = _connect(src_path, readonly=True)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    integrity = _sqlite_integrity_check(dst_path)
    if integrity.lower() != "ok":
        raise SalesIdentityRepairError(f"backup integrity_check failed for {dst_path}: {integrity}")
    return dst_path


def _dict_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames or []})


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm_size(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = text.replace("XXXL", "3XL").replace("XXL", "2XL")
    return text.strip("()[]{}")


def _size_from_name(value: Any) -> str:
    text = str(value or "").upper()
    for size in SIZE_ORDER:
        if re.search(r"(^|[\s_/()-])" + re.escape(size) + r"($|[\s_/()-])", text):
            return size
    nums = re.findall(r"(?<!\d)(42|44|46|48|50|52|54|56|58|60)(?!\d)", text)
    return NUMERIC_SIZE_MAP.get(nums[-1], "") if nums else ""


def _size_from_old_row(row: dict[str, Any]) -> str:
    for field in ("my_size", "sku_id"):
        value = _norm_size(row.get(field))
        if value in SIZE_ORDER:
            return value
        raw = str(row.get(field) or "")
        if "_" in raw:
            tail = _norm_size(raw.rsplit("_", 1)[-1])
            if tail in SIZE_ORDER:
                return tail
    return ""


def _size_from_offer_id(value: Any, ready_sku_keys: list[str]) -> str:
    text = str(value or "").upper()
    match = re.search(r"K-O_(?:ST|TRM)_((?:[234]XL)|XL|L|M|S)(?:_|$)", text)
    if match:
        return match.group(1)
    matches = re.findall(r"\(((?:[234]XL)|XL|L|M|S|XS)\)", text)
    if matches:
        return matches[-1]
    for sku_key in ready_sku_keys:
        prefix = sku_key.upper() + "_"
        if text.startswith(prefix):
            token = _norm_size(text[len(prefix) :].split("_", 1)[0])
            if token in SIZE_ORDER:
                return token
    for size in SIZE_ORDER:
        if re.search(r"(^|[_\s/()-])" + re.escape(size) + r"($|[_\s/()-])", text):
            return size
    return ""


def _ready_prefix(value: Any, ready_sku_keys: list[str]) -> str:
    text = str(value or "").upper()
    matches = [sku_key for sku_key in ready_sku_keys if text.startswith(sku_key.upper() + "_")]
    return max(matches, key=len) if matches else ""


def _load_ready_sku_keys(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT sku_key
        FROM dim_sku
        WHERE ((COALESCE(base_cost_cny, 0) > 0 AND COALESCE(weight_kg, 0) > 0)
               OR COALESCE(cogs_kzt, 0) > 0)
        ORDER BY LENGTH(sku_key) DESC
        """
    ).fetchall()
    return [str(row["sku_key"]) for row in rows]


def _load_size_by_key(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    return {
        (str(row["sku_key"]), _norm_size(row["my_size"])): str(row["sku_id"])
        for row in conn.execute(
            """
            SELECT sku_key, sku_id, my_size
            FROM dim_sku_size
            WHERE COALESCE(active_flag, 1) = 1
            """
        )
    }


def _sku_id_for(size_by_key: dict[tuple[str, str], str], sku_key: str, size: str) -> str:
    return (
        size_by_key.get((sku_key, size))
        or size_by_key.get((sku_key, "NAN"))
        or size_by_key.get((sku_key, "0"))
        or (f"{sku_key}_{size}" if size else sku_key)
    )


def _target_rows(conn: sqlite3.Connection, *, start: str, end: str) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in TARGET_SKU_KEYS)
    sql = f"""
        SELECT *
        FROM sales_fact_v2
        WHERE sale_id IN (
            SELECT DISTINCT sf.sale_id
            FROM sales_fact_v2 sf
            JOIN view_sales_line_truth v
              ON v.order_id = sf.order_id
             AND v.store_code = sf.store_code
             AND date(v.sale_date) = date(sf.order_date)
             AND v.sku_key = sf.sku_key
            WHERE date(v.sale_date) BETWEEN ? AND ?
              AND v.cogs_kzt IS NULL
              AND sf.sku_key IN ({placeholders})
              AND UPPER(COALESCE(sf.status, 'DELIVERED')) = 'DELIVERED'
              AND COALESCE(sf.return_flag, 0) = 0
        )
        ORDER BY order_date, order_id, sale_id
    """
    return _dict_rows(conn, sql, (start, end, *sorted(TARGET_SKU_KEYS)))


def _active_article_map(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[str, str]]:
    rows = _dict_rows(
        conn,
        """
        WITH raw AS (
            SELECT UPPER(TRIM(COALESCE(kaspi_article, ''))) AS article_norm,
                   UPPER(TRIM(COALESCE(store_code, ''))) AS store_norm,
                   sku_key,
                   sku_id,
                   COUNT(*) AS row_count
            FROM dim_kaspi_article_map
            WHERE COALESCE(active_flag, 1) = 1
              AND COALESCE(kaspi_article, '') <> ''
              AND COALESCE(sku_key, '') <> ''
              AND COALESCE(sku_id, '') <> ''
            GROUP BY 1, 2, 3, 4
        ),
        grouped AS (
            SELECT article_norm, store_norm,
                   COUNT(*) AS identity_count,
                   MAX(sku_key) AS sku_key,
                   MAX(sku_id) AS sku_id
            FROM raw
            GROUP BY 1, 2
        )
        SELECT article_norm, store_norm, sku_key, sku_id
        FROM grouped
        WHERE identity_count = 1
        """,
    )
    return {
        (str(row["article_norm"]), str(row["store_norm"])): (str(row["sku_key"]), str(row["sku_id"]))
        for row in rows
    }


def _active_offer_name_map(conn: sqlite3.Connection) -> dict[tuple[str, str], tuple[str, str]]:
    rows = _dict_rows(
        conn,
        """
        WITH raw AS (
            SELECT UPPER(TRIM(COALESCE(kaspi_offer_name, ''))) AS offer_name_norm,
                   UPPER(TRIM(COALESCE(store_code, ''))) AS store_norm,
                   sku_key,
                   sku_id,
                   COUNT(*) AS row_count
            FROM dim_kaspi_article_map
            WHERE COALESCE(active_flag, 1) = 1
              AND COALESCE(kaspi_offer_name, '') <> ''
              AND COALESCE(sku_key, '') <> ''
              AND COALESCE(sku_id, '') <> ''
            GROUP BY 1, 2, 3, 4
        ),
        grouped AS (
            SELECT offer_name_norm, store_norm,
                   COUNT(*) AS identity_count,
                   MAX(sku_key) AS sku_key,
                   MAX(sku_id) AS sku_id
            FROM raw
            GROUP BY 1, 2
        )
        SELECT offer_name_norm, store_norm, sku_key, sku_id
        FROM grouped
        WHERE identity_count = 1
        """,
    )
    return {
        (str(row["offer_name_norm"]), str(row["store_norm"])): (str(row["sku_key"]), str(row["sku_id"]))
        for row in rows
    }


def _entries_by_order(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _dict_rows(conn, "SELECT * FROM fact_order_entries_kaspi"):
        key = (str(row.get("order_id")), str(row.get("store_code")))
        grouped.setdefault(key, []).append(row)
    return grouped


def _orders_by_order(conn: sqlite3.Connection) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _dict_rows(conn, "SELECT * FROM fact_orders_kaspi"):
        key = (str(row.get("order_id")), str(row.get("store_code")))
        grouped.setdefault(key, []).append(row)
    return grouped


def _dim_sku_ready(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["sku_key"])
        for row in conn.execute(
            """
            SELECT sku_key
            FROM dim_sku
            WHERE ((COALESCE(base_cost_cny, 0) > 0 AND COALESCE(weight_kg, 0) > 0)
                   OR COALESCE(cogs_kzt, 0) > 0)
            """
        )
    }


def _make_candidate(
    row: dict[str, Any],
    *,
    new_sku_key: str,
    new_sku_id: str,
    new_my_size: str,
    evidence_source: str,
    priority: int,
    evidence_value: str = "",
    name_size: str = "",
    offer_size: str = "",
    old_size: str = "",
) -> Candidate:
    return Candidate(
        sale_id=int(row["sale_id"]),
        order_id=str(row["order_id"]),
        store_code=str(row.get("store_code") or "UNIVERSAL"),
        order_date=str(row.get("order_date") or ""),
        kaspi_offer_name=str(row.get("kaspi_offer_name") or ""),
        old_sku_key=str(row.get("sku_key") or ""),
        old_sku_id=str(row.get("sku_id") or ""),
        old_my_size=str(row.get("my_size") or ""),
        new_sku_key=new_sku_key,
        new_sku_id=new_sku_id,
        new_my_size=new_my_size,
        evidence_source=evidence_source,
        priority=priority,
        evidence_value=evidence_value,
        name_size=name_size,
        offer_size=offer_size,
        old_size=old_size,
    )


def _primary_candidates(conn: sqlite3.Connection, targets: list[dict[str, Any]]) -> tuple[list[Candidate], list[dict[str, Any]]]:
    article_map = _active_article_map(conn)
    offer_name_map = _active_offer_name_map(conn)
    entries = _entries_by_order(conn)
    orders = _orders_by_order(conn)
    ready = _dim_sku_ready(conn)
    raw: list[Candidate] = []
    conflicts: list[dict[str, Any]] = []

    for row in targets:
        row_key = (str(row["order_id"]), str(row.get("store_code") or "UNIVERSAL"))
        store_norm = row_key[1].upper().strip()
        row_entries = entries.get(row_key, [])
        row_orders = orders.get(row_key, [])

        if str(row.get("sku_key")) in {"116515378", "132822924"}:
            for entry in row_entries:
                offer_id = str(entry.get("offer_id") or "")
                article_key = (offer_id.upper().strip(), store_norm)
                mapped = article_map.get(article_key)
                offer_norm = offer_id.upper().strip()
                old_sku_key = str(row.get("sku_key") or "").upper().strip()
                old_sku_id = str(row.get("sku_id") or "").upper().strip()
                if mapped and (
                    offer_norm == old_sku_key
                    or offer_norm == old_sku_id
                    or offer_norm.startswith(old_sku_key + "_")
                ):
                    raw.append(
                        _make_candidate(
                            row,
                            new_sku_key=mapped[0],
                            new_sku_id=mapped[1],
                            new_my_size=str(row.get("my_size") or ""),
                            evidence_source="entry_offer_matches_old_identity",
                            priority=5,
                            evidence_value=offer_id,
                        )
                    )

        if len(row_entries) == 1:
            offer_id = str(row_entries[0].get("offer_id") or "")
            mapped = article_map.get((offer_id.upper().strip(), store_norm))
            if mapped:
                raw.append(
                    _make_candidate(
                        row,
                        new_sku_key=mapped[0],
                        new_sku_id=mapped[1],
                        new_my_size=str(row.get("my_size") or ""),
                        evidence_source="single_entry_offer_article_map",
                        priority=10,
                        evidence_value=offer_id,
                    )
                )

        offer_name_norm = str(row.get("kaspi_offer_name") or "").upper().strip()
        mapped_by_name = offer_name_map.get((offer_name_norm, store_norm))
        if mapped_by_name:
            raw.append(
                _make_candidate(
                    row,
                    new_sku_key=mapped_by_name[0],
                    new_sku_id=mapped_by_name[1],
                    new_my_size=str(row.get("my_size") or ""),
                    evidence_source="sales_offer_name_article_map",
                    priority=20,
                    evidence_value=str(row.get("kaspi_offer_name") or ""),
                )
            )

        non_generic_orders = [
            order
            for order in row_orders
            if str(order.get("sku_key") or "").upper().strip()
            not in {"", "CL", "UNKNOWN", "116515378", "132822924"}
            and str(order.get("sku_key")) in ready
        ]
        for order in non_generic_orders:
            if str(order.get("kaspi_offer_name") or "").upper().strip() == offer_name_norm:
                raw.append(
                    _make_candidate(
                        row,
                        new_sku_key=str(order.get("sku_key") or ""),
                        new_sku_id=str(order.get("sku_id") or ""),
                        new_my_size=str(order.get("assigned_size") or order.get("my_size") or row.get("my_size") or ""),
                        evidence_source="fact_orders_offer_name_identity",
                        priority=30,
                        evidence_value=str(order.get("kaspi_offer_name") or ""),
                    )
                )
        if len(non_generic_orders) == 1:
            order = non_generic_orders[0]
            raw.append(
                _make_candidate(
                    row,
                    new_sku_key=str(order.get("sku_key") or ""),
                    new_sku_id=str(order.get("sku_id") or ""),
                    new_my_size=str(order.get("assigned_size") or order.get("my_size") or row.get("my_size") or ""),
                    evidence_source="fact_orders_single_identity",
                    priority=40,
                    evidence_value=str(order.get("sku_id") or ""),
                )
            )

    by_sale: dict[int, list[Candidate]] = {}
    for candidate in raw:
        by_sale.setdefault(candidate.sale_id, []).append(candidate)

    chosen: list[Candidate] = []
    for sale_id, candidates in by_sale.items():
        min_priority = min(candidate.priority for candidate in candidates)
        top = [candidate for candidate in candidates if candidate.priority == min_priority]
        sku_keys = {candidate.new_sku_key for candidate in top}
        if len(sku_keys) > 1:
            conflicts.append(
                {
                    "sale_id": sale_id,
                    "conflict_type": "primary_sku_key_conflict",
                    "evidence_sources": ";".join(sorted({candidate.evidence_source for candidate in top})),
                    "identities": ";".join(sorted({f"{c.new_sku_key}/{c.new_sku_id}" for c in top})),
                }
            )
            continue
        chosen.append(sorted(top, key=lambda c: (c.priority, c.evidence_source, c.new_sku_key, c.new_sku_id))[0])
    return chosen, conflicts


def _derived_candidate(
    row: dict[str, Any],
    *,
    entries: list[dict[str, Any]],
    ready_sku_keys: list[str],
    size_by_key: dict[tuple[str, str], str],
) -> Candidate | None:
    name_size = _size_from_name(row.get("kaspi_offer_name"))
    old_size = _size_from_old_row(row)
    desired_size = name_size or old_size
    possible: list[tuple[str, str, str, str, str]] = []
    for entry in entries:
        offer_id = str(entry.get("offer_id") or "")
        sku_key = _ready_prefix(offer_id, ready_sku_keys)
        if not sku_key:
            continue
        offer_size = _size_from_offer_id(offer_id, ready_sku_keys)
        if len(entries) > 1 and desired_size and offer_size and offer_size != desired_size:
            continue
        final_size = name_size or offer_size or old_size
        possible.append(
            (
                sku_key,
                _sku_id_for(size_by_key, sku_key, final_size),
                final_size or str(row.get("my_size") or ""),
                offer_id,
                offer_size,
            )
        )
    unique = sorted(set(possible))
    identities = sorted({(item[0], item[1], item[2]) for item in unique})
    if len(identities) != 1:
        return None
    sku_key, sku_id, my_size = identities[0]
    return _make_candidate(
        row,
        new_sku_key=sku_key,
        new_sku_id=sku_id,
        new_my_size=my_size,
        evidence_source="ready_prefix_derived",
        priority=50,
        evidence_value=";".join(item[3] for item in unique),
        name_size=name_size,
        offer_size=unique[0][4] if unique else "",
        old_size=old_size,
    )


def build_candidates(conn: sqlite3.Connection, *, start: str, end: str) -> tuple[list[Candidate], list[dict[str, Any]], list[dict[str, Any]]]:
    targets = _target_rows(conn, start=start, end=end)
    primary, conflicts = _primary_candidates(conn, targets)
    primary_by_sale = {candidate.sale_id: candidate for candidate in primary}
    entries = _entries_by_order(conn)
    ready_sku_keys = _load_ready_sku_keys(conn)
    size_by_key = _load_size_by_key(conn)

    combined = list(primary_by_sale.values())
    unresolved_after_primary: list[dict[str, Any]] = []
    for row in targets:
        sale_id = int(row["sale_id"])
        if sale_id in primary_by_sale:
            continue
        candidate = _derived_candidate(
            row,
            entries=entries.get((str(row["order_id"]), str(row.get("store_code") or "UNIVERSAL")), []),
            ready_sku_keys=ready_sku_keys,
            size_by_key=size_by_key,
        )
        if candidate is None:
            unresolved_after_primary.append(
                {
                    "sale_id": sale_id,
                    "order_id": row.get("order_id"),
                    "store_code": row.get("store_code"),
                    "kaspi_offer_name": row.get("kaspi_offer_name"),
                    "reason": "no_deterministic_derived_identity",
                }
            )
        else:
            combined.append(candidate)

    final, unique_conflicts = _resolve_unique_collisions(combined, conn, size_by_key)
    excluded = conflicts + unresolved_after_primary + unique_conflicts
    return final, excluded, targets


def _resolve_unique_collisions(
    candidates: list[Candidate],
    conn: sqlite3.Connection,
    size_by_key: dict[tuple[str, str], str],
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    by_unique: dict[tuple[str, str, str, str], list[Candidate]] = {}
    for candidate in candidates:
        key = (
            candidate.order_id,
            candidate.store_code.upper().strip(),
            candidate.new_sku_id,
            candidate.kaspi_offer_name,
        )
        by_unique.setdefault(key, []).append(candidate)

    split: list[Candidate] = []
    conflicts: list[dict[str, Any]] = []
    for key, items in by_unique.items():
        if len(items) == 1:
            split.extend(items)
            continue
        sku_keys = {item.new_sku_key for item in items}
        old_sizes = [item.old_size or _norm_size(item.old_my_size) for item in items]
        if (
            len(sku_keys) == 1
            and len(set(old_sizes)) == len(items)
            and all((next(iter(sku_keys)), size) in size_by_key for size in old_sizes)
        ):
            sku_key = next(iter(sku_keys))
            for item, old_size in zip(items, old_sizes, strict=True):
                split.append(
                    Candidate(
                        **{
                            **item.as_dict(),
                            "new_sku_id": _sku_id_for(size_by_key, sku_key, old_size),
                            "new_my_size": old_size,
                            "evidence_source": "ready_prefix_duplicate_split_by_sales_row_size",
                            "priority": 55,
                        }
                    )
                )
            continue
        conflicts.append(
            {
                "sale_id": ";".join(str(item.sale_id) for item in items),
                "order_id": key[0],
                "store_code": key[1],
                "kaspi_offer_name": key[3],
                "conflict_type": "candidate_unique_key_collision",
                "identities": ";".join(sorted({f"{item.new_sku_key}/{item.new_sku_id}" for item in items})),
            }
        )

    sale_ids = {candidate.sale_id for candidate in split}
    final: list[Candidate] = []
    for candidate in split:
        row = conn.execute(
            """
            SELECT sale_id
            FROM sales_fact_v2
            WHERE sale_id <> ?
              AND order_id = ?
              AND UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) = UPPER(TRIM(COALESCE(?, 'UNIVERSAL')))
              AND kaspi_offer_name = ?
              AND sku_id = ?
            """,
            (
                candidate.sale_id,
                candidate.order_id,
                candidate.store_code,
                candidate.kaspi_offer_name,
                candidate.new_sku_id,
            ),
        ).fetchone()
        if row and int(row["sale_id"]) not in sale_ids:
            conflicts.append(
                {
                    "sale_id": candidate.sale_id,
                    "order_id": candidate.order_id,
                    "store_code": candidate.store_code,
                    "kaspi_offer_name": candidate.kaspi_offer_name,
                    "conflict_type": "existing_unique_key_collision",
                    "existing_sale_id": int(row["sale_id"]),
                }
            )
        else:
            final.append(candidate)
    return final, conflicts


def _before_rows(conn: sqlite3.Connection, candidates: list[Candidate]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    ids = [candidate.sale_id for candidate in candidates]
    placeholders = ",".join("?" for _ in ids)
    return _dict_rows(
        conn,
        f"""
        SELECT sale_id, order_id, store_code, order_date, sku_key, sku_id,
               my_size, kaspi_offer_name, cogs, profit
        FROM sales_fact_v2
        WHERE sale_id IN ({placeholders})
        ORDER BY sale_id
        """,
        tuple(ids),
    )


def _apply_candidates(conn: sqlite3.Connection, candidates: list[Candidate]) -> int:
    count = 0
    for candidate in candidates:
        cur = conn.execute(
            """
            UPDATE sales_fact_v2
            SET sku_key = ?,
                sku_id = ?,
                my_size = ?,
                cogs = NULL,
                profit = NULL
            WHERE sale_id = ?
            """,
            (candidate.new_sku_key, candidate.new_sku_id, candidate.new_my_size, candidate.sale_id),
        )
        count += cur.rowcount
    return count


def _run_on_path(
    db_path: Path,
    *,
    start: str,
    end: str,
    output_dir: Path,
    apply: bool,
    expected_count: int | None = None,
) -> dict[str, Any]:
    conn = _connect(db_path)
    try:
        candidates, excluded, targets = build_candidates(conn, start=start, end=end)
        before = _before_rows(conn, candidates)
        candidate_rows = [candidate.as_dict() for candidate in candidates]
        _write_csv(output_dir / "target_rows.csv", targets)
        _write_csv(output_dir / "candidate_rows.csv", candidate_rows)
        _write_csv(output_dir / "excluded_rows.csv", excluded)
        _write_csv(output_dir / "before_rows.csv", before)
        if expected_count is not None and len(candidates) != expected_count:
            raise SalesIdentityRepairError(
                f"candidate count mismatch: expected {expected_count}, got {len(candidates)}"
            )
        if excluded:
            raise SalesIdentityRepairError(
                f"excluded rows remain: {len(excluded)} (see {output_dir / 'excluded_rows.csv'})"
            )
        rows_updated = 0
        if apply:
            rows_updated = _apply_candidates(conn, candidates)
            conn.commit()
        after = _before_rows(conn, candidates)
        _write_csv(output_dir / "after_rows.csv", after)
    finally:
        conn.close()

    by_source: dict[str, int] = {}
    for candidate in candidates:
        by_source[candidate.evidence_source] = by_source.get(candidate.evidence_source, 0) + 1
    return {
        "target_count": len(targets),
        "candidate_count": len(candidates),
        "excluded_count": len(excluded),
        "rows_updated": rows_updated,
        "by_source": by_source,
    }


def run_repair(
    *,
    db_path: Path,
    output_dir: Path,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    apply: bool = False,
    backup_dir: Path | None = None,
    expected_pre_sha256: str | None = None,
    expected_count: int | None = None,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pre_sha = _sha256_file(db_path)
    if expected_pre_sha256 and expected_pre_sha256 != pre_sha:
        raise SalesIdentityRepairError(
            f"pre-SHA mismatch: expected {expected_pre_sha256}, got {pre_sha}"
        )

    backup_path = None
    if apply:
        if os.environ.get(ENV_GATE) != "1":
            raise SalesIdentityRepairError(f"{ENV_GATE}=1 is required with --apply")
        if backup_dir is None:
            raise SalesIdentityRepairError("--backup-dir is required with --apply")
        backup_path = _sqlite_backup(
            db_path,
            backup_dir / f"app_before_sales_fact_v2_cogs_identity_repair_{pre_sha[:12]}.db",
        )
        work_db_path = db_path
        status = "APPLIED"
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix="sales_identity_repair_", dir=str(output_dir)))
        work_db_path = temp_dir / "app.simulation.db"
        shutil.copy2(db_path, work_db_path)
        status = "DRY_RUN"

    summary = _run_on_path(
        work_db_path,
        start=start,
        end=end,
        output_dir=output_dir,
        apply=True,
        expected_count=expected_count,
    )
    if summary["rows_updated"] != summary["candidate_count"]:
        raise SalesIdentityRepairError(
            f"rows_updated mismatch: updated {summary['rows_updated']} for {summary['candidate_count']} candidates"
        )

    post_sha = _sha256_file(db_path)
    report = {
        "status": status,
        "db_path": str(db_path),
        "start": start,
        "end": end,
        "pre_sha256": pre_sha,
        "post_sha256": post_sha,
        "db_sha256_changed": pre_sha != post_sha,
        "backup_path": str(backup_path) if backup_path else None,
        **summary,
        "outputs": {
            "target_rows_csv": str(output_dir / "target_rows.csv"),
            "candidate_rows_csv": str(output_dir / "candidate_rows.csv"),
            "excluded_rows_csv": str(output_dir / "excluded_rows.csv"),
            "before_rows_csv": str(output_dir / "before_rows.csv"),
            "after_rows_csv": str(output_dir / "after_rows.csv"),
        },
    }
    if not apply and report["db_sha256_changed"]:
        raise SalesIdentityRepairError("dry-run mutated source DB")
    _write_json(output_dir / "sales_fact_v2_cogs_identity_repair_report.json", report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--expected-count", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_repair(
            db_path=args.db_path,
            output_dir=args.output_dir,
            start=args.start,
            end=args.end,
            apply=args.apply,
            backup_dir=args.backup_dir,
            expected_pre_sha256=args.expected_pre_sha256,
            expected_count=args.expected_count,
        )
    except SalesIdentityRepairError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
