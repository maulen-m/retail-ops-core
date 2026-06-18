#!/usr/bin/env python3
"""Build the 2026-06-04 pre-shipment manual stock anchor and dry-run replay."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ops.manual_stock_count_manifest import (  # noqa: E402
    aggregate_manual_stock_counts,
    validate_manual_stock_manifest,
    write_manual_stock_aggregate_csv,
)


BATCH_ID = "ASTANA_WAREHOUSE_MANUAL_COUNT_2026_06_04_PRE_SHIPMENTS"
ANCHOR_TIMESTAMP = "2026-06-04T14:00:23+05:00"
ANCHOR_SQLITE_TS = "2026-06-04 14:00:23"
TIMESTAMP_FOLDER = "04.06.2026_14_00_23"
ALMATY = ZoneInfo("Asia/Almaty")
MANIFEST_PATH = (
    PROJECT_ROOT
    / "config/anchors/manual_stock_counts/"
    "astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved.json"
)
AGGREGATE_CSV_PATH = MANIFEST_PATH.with_name(
    "astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved_aggregate.csv"
)
DOC_PATH = PROJECT_ROOT / "docs/inventory/ASTANA_WAREHOUSE_MANUAL_STOCK_COUNT_2026_06_04_PRE_SHIPMENTS.md"
DB_PATH = PROJECT_ROOT / "db/app.db"
SOURCE_REPORT = (
    Path.home()
    / "Downloads/Stock_ingestion_from_warehouse_counting/warehouse_stock_count_manual_results/"
    "images/04.06.2026_14_00_23/stock_count_04.06.2026_14_00.md"
)
TOTAL_REPORT = (
    Path.home()
    / "Downloads/Stock_ingestion_from_warehouse_counting/warehouse_stock_count_manual_results/"
    "TOTAL_stock_count_all.md"
)
SOURCE_IMAGE_ROOT = (
    Path.home()
    / "Downloads/Stock_ingestion_from_warehouse_counting/warehouse_stock_count_manual_results/"
    "images/04.06.2026_14_00_23"
)

TRUSTED_SHIPMENT_STATUSES = {"SHIPPED", "COMPLETED"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_evidence(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "sha256": sha256_file(path) if path.exists() and path.is_file() else "",
    }


def add_rows(
    rows: list[dict[str, Any]],
    *,
    row_prefix: str,
    model_label: str,
    sku_key: str,
    color_or_pattern: str,
    source_image: str,
    source_event_type: str,
    quantities: dict[str, int],
    ocr_labels: dict[str, str] | None = None,
    source_deltas: dict[str, int] | None = None,
    prior_source: str = "",
    counting_policy: str = "single_sku_pool",
    source_label: str = "",
) -> None:
    for idx, (size, qty) in enumerate(quantities.items(), start=1):
        sku_id = f"{sku_key}_{size}"
        rows.append(
            {
                "row_id": f"{row_prefix}-{idx:03d}",
                "count_timestamp_at_almaty": ANCHOR_TIMESTAMP,
                "timestamp_folder": TIMESTAMP_FOLDER,
                "source_image": source_image,
                "model_label": model_label,
                "sku_key": sku_key,
                "sku_id": sku_id,
                "applies_to_sku_ids": [sku_id],
                "stock_pool_id": sku_id,
                "ocr_size_label": (ocr_labels or {}).get(size, size),
                "canonical_size": size,
                "color_or_pattern": color_or_pattern,
                "quantity": qty,
                "counting_policy": counting_policy,
                "source_event_type": source_event_type,
                "source_delta": (source_deltas or {}).get(size),
                "prior_source": prior_source,
                "source_label": source_label,
                "timing_policy": "pre_2026_06_04_daily_kaspi_shipments",
            }
        )


def materialized_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    add_rows(
        rows,
        row_prefix="ASTANA-20260604-LINE52",
        model_label="Line52",
        sku_key="CL_OC_MEN_LINE52_BLACK",
        color_or_pattern="black",
        source_image="PHOTO-2026-06-11-14-28-06 copy 4.jpg",
        source_event_type="update_replacement",
        source_label="line52 update",
        quantities={"M": 42, "L": 129, "2XL": 4, "3XL": 83, "4XL": 32},
        prior_source="replaces prior latest Line52 count of 85 units",
    )
    add_rows(
        rows,
        row_prefix="ASTANA-20260604-ROMBIK-MEN",
        model_label="Rombik_men",
        sku_key="CL_NEW-CLO_MEN_ROMBIK_BLACK",
        color_or_pattern="romb",
        source_image="PHOTO-2026-06-11-14-28-06 copy 7.jpg",
        source_event_type="addition_effective_materialized",
        source_label="Rombik_men addition",
        quantities={"M": 21, "L": 45, "XL": 5, "2XL": 29, "3XL": 21, "4XL": 17},
        source_deltas={"M": 1, "L": 0, "XL": 5, "2XL": 4, "3XL": 0, "4XL": 1},
        prior_source="adds to latest approved Rombik men non-shared pool",
    )
    rows.append(
        {
            "row_id": "ASTANA-20260604-ROMBIK-S-001",
            "count_timestamp_at_almaty": ANCHOR_TIMESTAMP,
            "timestamp_folder": TIMESTAMP_FOLDER,
            "source_image": "PHOTO-2026-06-11-14-28-06 copy 7.jpg",
            "model_label": "Rombik_S_shared_men_kids",
            "sku_key": "CL_NEW-CLO_MEN_ROMBIK_BLACK",
            "sku_id": "CL_NEW-CLO_MEN_ROMBIK_BLACK_S",
            "applies_to_sku_ids": ["CL_NEW-CLO_MEN_ROMBIK_BLACK_S", "CL_NEW-CLO_KID_ROMBIK_BLACK_S"],
            "stock_pool_id": "SHARED_ROMBIK_BLACK_S_MEN_KIDS",
            "ocr_size_label": "S",
            "canonical_size": "S",
            "color_or_pattern": "romb",
            "quantity": 75,
            "counting_policy": "shared_pool_override_do_not_double_count_aliases",
            "source_event_type": "addition_effective_materialized",
            "source_delta": 1,
            "prior_source": "adds to latest approved shared Rombik S pool of 74 units",
            "source_label": "Rombik_men addition",
            "timing_policy": "pre_2026_06_04_daily_kaspi_shipments",
        }
    )
    add_rows(
        rows,
        row_prefix="ASTANA-20260604-LINE61",
        model_label="Line61",
        sku_key="CL_NEW-CLO2_MEN_SUIT-61_BLACK",
        color_or_pattern="black",
        source_image="PHOTO-2026-06-11-14-28-06 copy 5.jpg",
        source_event_type="addition_effective_materialized",
        source_label="Line61 addition",
        quantities={"S": 43, "M": 96, "L": 143, "XL": 93, "2XL": 69, "3XL": 24, "4XL": 9},
        source_deltas={"S": 0, "M": 1, "L": 5, "XL": 10, "2XL": 8, "3XL": 8, "4XL": 0},
        prior_source="adds to latest approved Line61 count of 445 units",
    )
    add_rows(
        rows,
        row_prefix="ASTANA-20260604-LEG-WHITE",
        model_label="Leggings_white",
        sku_key="CL_NEW-CLO_MEN_LEG_WHITE",
        color_or_pattern="white",
        source_image="PHOTO-2026-06-11-13-58-44 2.jpg",
        source_event_type="addition_effective_materialized",
        source_label="Leggings white addition",
        quantities={"S": 19, "M": 34, "L": 97, "XL": 118, "2XL": 79, "3XL": 86},
        source_deltas={"S": 0, "M": 10, "L": 10, "XL": 30, "2XL": 0, "3XL": 3},
        prior_source="adds to latest OCR leggings white supersession count",
    )
    add_rows(
        rows,
        row_prefix="ASTANA-20260604-LEG-BLACK",
        model_label="Leggings_black",
        sku_key="CL_NEW-CLO_MEN_LEG_BLACK",
        color_or_pattern="black",
        source_image="PHOTO-2026-06-11-13-58-44 2.jpg",
        source_event_type="effective_rollup_from_prior_source",
        source_label="Leggings white addition context",
        quantities={"S": 16, "M": 17, "L": 56, "XL": 57, "2XL": 52, "3XL": 36},
        source_deltas={"S": 0, "M": 0, "L": 0, "XL": 0, "2XL": 0, "3XL": 0},
        prior_source="carried from latest OCR leggings black supersession count",
    )
    add_rows(
        rows,
        row_prefix="ASTANA-20260604-KIDS31",
        model_label="kids31_black",
        sku_key="CL_NEW-CLO_KIDS_KID-31_BLACK",
        color_or_pattern="black",
        source_image="PHOTO-2026-06-11-13-58-44 3.jpg",
        source_event_type="replacement",
        source_label="kids 3 in 1",
        quantities={"22": 12, "24": 9, "26": 54, "28": 33, "30": 29},
        ocr_labels={"22": "110/22", "24": "120/24", "26": "130/26", "28": "140/28", "30": "150/30"},
        prior_source="replaces prior latest kids31 count of 74 units",
    )
    for color, qtys in {
        "WHITE": {"S": 33, "M": 78, "L": 101, "XL": 51, "2XL": 50, "3XL": 22},
        "BLACK": {"S": 46, "M": 21, "L": 153, "XL": 17, "2XL": 47, "3XL": 91},
        "GREY": {"S": 23, "M": 67, "L": 105, "XL": 80, "2XL": 40, "3XL": 22},
    }.items():
        add_rows(
            rows,
            row_prefix=f"ASTANA-20260604-NIKE-{color}",
            model_label=f"Nike_shirt_{color.lower()}",
            sku_key=f"CL_NEW-CLO_MEN_NIKE-SHIRT_{color}",
            color_or_pattern=color.lower(),
            source_image=(
                "PHOTO-2026-06-11-13-58-44.jpg"
                if color != "BLACK"
                else "PHOTO-2026-06-11-13-58-44.jpg;PHOTO-2026-06-11-14-28-06 copy 6.jpg"
            ),
            source_event_type="replacement_plus_addition_effective_materialized"
            if color == "BLACK"
            else "replacement_effective_materialized",
            source_label="Nike t-shirt replacement plus black addition",
            quantities=qtys,
            source_deltas={"XL": 1, "2XL": 3} if color == "BLACK" else None,
            prior_source="new/replacement OCR materialization",
        )
    add_rows(
        rows,
        row_prefix="ASTANA-20260604-SHORTS",
        model_label="Shorts_black",
        sku_key="CL_NC_MEN_SHORTS_BLACK",
        color_or_pattern="black",
        source_image="PHOTO-2026-06-11-14-28-06 copy 3.jpg",
        source_event_type="replacement_new_product",
        source_label="Shorts",
        quantities={"S": 20, "M": 40, "L": 79, "XL": 111, "2XL": 80, "3XL": 58, "4XL": 20},
        prior_source="new/replacement OCR materialization",
    )
    add_rows(
        rows,
        row_prefix="ASTANA-20260604-LINE51",
        model_label="LINE51_black_white_set",
        sku_key="CL_OC_MEN_LINE51_WHITE",
        color_or_pattern="black_white",
        source_image="PHOTO-2026-06-11-14-28-06 copy.jpg",
        source_event_type="replacement_provided_sizes_only",
        source_label="LINE51 black/white set",
        quantities={"M": 105, "L": 190, "XL": 216, "2XL": 145, "3XL": 94},
        prior_source="S not re-provided; no LINE51 S row is materialized",
    )
    return rows


def quarantine_rows() -> list[dict[str, Any]]:
    return [
        {
            "source_label": "3_in_1_men_sets",
            "source_image": "3_in_1_men_sets.jpg",
            "source_sku_key": "UNMAPPED_3_IN_1_MEN_SETS",
            "canonical_size": size,
            "quantity": qty,
            "quarantine_reason": "canonical SKU/card mapping pending",
            "status": "QUARANTINED_NOT_MATERIALIZED",
        }
        for size, qty in {"S": 58, "M": 30, "L": 45, "XL": 65, "2XL": 47, "3XL": 28}.items()
    ]


def build_manifest() -> dict[str, Any]:
    rows = materialized_rows()
    product_totals: dict[str, int] = defaultdict(int)
    for row in rows:
        product_totals[str(row["model_label"])] += int(row["quantity"])
    manifest = {
        "schema_version": "manual_warehouse_stock_count_manifest_v1",
        "batch_id": BATCH_ID,
        "status": "OWNER_APPROVED",
        "location": {
            "warehouse": "Astana warehouse",
            "city": "Astana",
            "country": "Kazakhstan",
            "timezone": "Asia/Almaty",
        },
        "approval": {
            "counted_by": "warehouse_employee",
            "approved_by": "owner_handoff",
            "approved_at": "2026-06-11T00:00:00+05:00",
            "approval_basis": "Owner handoff for 2026-06-04 pre-shipment warehouse OCR/manual stock records.",
        },
        "count_scope": {
            "method": "manual_human_count_before_2026_06_04_daily_kaspi_shipments",
            "covered_inventory_state": "visible Astana warehouse units for materialized product/color/size rows only",
            "quarantine_returns_included": False,
            "cancellation_units_included": False,
            "quarantine_returns_status": "not_counted_pending_employee_count",
            "cancellation_units_status": "not_counted_pending_employee_count",
            "missing_size_policy": "do_not_infer_zero_for_sizes_absent_from_this_manifest",
            "duplicate_size_policy": "materialized_effective_quantity_per_sku_size_after_update_or_addition_semantics",
            "line51_s_policy": "do_not_overwrite_zero_or_unknown_CL_OC_MEN_LINE51_WHITE_S",
            "mapping_pending_policy": "quarantine_unmapped_3_in_1_men_sets_until_canonical_sku_card_mapping_is_proven",
        },
        "source_artifacts": {
            "primary_ocr_report": str(SOURCE_REPORT),
            "merged_total_append": str(TOTAL_REPORT),
            "source_image_root": str(SOURCE_IMAGE_ROOT),
            "source_folders": [str(SOURCE_IMAGE_ROOT)],
        },
        "known_corrections": [],
        "precedence": {
            "rank": 20,
            "rule": (
                "For SKU-size or shared stock-pool rows covered by this approved pre-shipment "
                "manual count, use this count before older covered manual anchors."
            ),
            "post_count_motion_rule": (
                "After 2026-06-04T14:00:23+05:00, subtract trusted 2026-06-04 daily "
                "Kaspi shipments and later shipped/order movements exactly once."
            ),
            "scope_limit": (
                "This manifest only overrides rows explicitly covered here; it does not alter "
                "LINE51 S, absent sizes, quarantine returns, cancellations, or unmapped 3_in_1 rows."
            ),
        },
        "expected_totals": {
            "raw_row_count": len(rows),
            "aggregate_stock_pool_row_count": len(rows),
            "total_units": sum(int(row["quantity"]) for row in rows),
            "folder_totals": {TIMESTAMP_FOLDER: sum(int(row["quantity"]) for row in rows)},
            "product_totals": dict(sorted(product_totals.items())),
            "known_rollup_reference_total_excluding_line51_s": 5786,
            "quarantined_mapping_pending_units": 273,
            "materialized_units_excluding_quarantine_and_line51_s": sum(int(row["quantity"]) for row in rows),
        },
        "quarantine": {
            "mapping_pending_rows": quarantine_rows(),
            "mapping_pending_units": sum(row["quantity"] for row in quarantine_rows()),
        },
        "rows": rows,
    }
    validate_manual_stock_manifest(manifest)
    return manifest


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def sqlite_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def validate_mapping(conn: sqlite3.Connection, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in manifest["rows"]:
        for applies_to in row["applies_to_sku_ids"]:
            match = conn.execute(
                """
                SELECT s.sku_id, s.sku_key, s.my_size, s.active_flag, z.model, z.color, z.active_flag AS sku_active
                FROM dim_sku_size s
                LEFT JOIN dim_sku z ON z.sku_key = s.sku_key
                WHERE s.sku_id = ?
                """,
                (applies_to,),
            ).fetchone()
            active_article_rows = conn.execute(
                "SELECT COUNT(*) FROM dim_kaspi_article_map WHERE sku_id = ? AND active_flag = 1",
                (applies_to,),
            ).fetchone()[0]
            relation = "primary" if applies_to == row["sku_id"] else "shared_pool_alias"
            status = "PASS"
            reason = ""
            if match is None:
                status = "FAIL"
                reason = "missing_dim_sku_size"
            elif int(match["active_flag"] or 0) != 1:
                status = "FAIL"
                reason = "inactive_dim_sku_size"
            elif str(match["my_size"]) != str(row["canonical_size"]):
                status = "FAIL"
                reason = "size_mismatch"
            elif relation == "primary" and str(match["sku_key"]) != str(row["sku_key"]):
                status = "FAIL"
                reason = "sku_key_mismatch"
            records.append(
                {
                    "row_id": row["row_id"],
                    "relation": relation,
                    "expected_sku_key": row["sku_key"],
                    "expected_sku_id": applies_to,
                    "expected_size": row["canonical_size"],
                    "actual_sku_key": "" if match is None else match["sku_key"],
                    "actual_size": "" if match is None else match["my_size"],
                    "dim_sku_size_active": "" if match is None else match["active_flag"],
                    "dim_sku_active": "" if match is None else match["sku_active"],
                    "article_map_active_rows": active_article_rows,
                    "status": status,
                    "reason": reason,
                }
            )
    return records


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            return datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def build_pool_indexes(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    by_sku_id: dict[str, dict[str, Any]] = {}
    by_sku_size: dict[tuple[str, str], dict[str, Any]] = {}
    for aggregate in aggregate_manual_stock_counts(manifest):
        row = {
            "stock_pool_id": aggregate.stock_pool_id,
            "sku_key": aggregate.sku_key,
            "sku_id": aggregate.sku_id,
            "canonical_size": aggregate.canonical_size,
            "anchor_quantity": aggregate.quantity,
            "applies_to_sku_ids": aggregate.applies_to_sku_ids,
        }
        by_sku_size[(aggregate.sku_key, aggregate.canonical_size)] = row
        for sku_id in aggregate.applies_to_sku_ids:
            by_sku_id[sku_id] = row
    return by_sku_id, by_sku_size


def shipment_replay(
    conn: sqlite3.Connection,
    manifest: dict[str, Any],
    *,
    as_of_date: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    by_sku_id, by_sku_size = build_pool_indexes(manifest)
    sku_keys = sorted({row["sku_key"] for row in manifest["rows"]} | {"CL_NEW-CLO_KID_ROMBIK_BLACK"})
    placeholders = ",".join("?" for _ in sku_keys)
    rows = sqlite_rows(
        conn,
        f"""
        SELECT
          order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size, assigned_size,
          quantity, created_at, planned_shipment_date, actual_shipment_date,
          courier_transmission_date, kaspi_status, internal_status, kaspi_status_detail,
          waybill_number, source, source_file
        FROM fact_orders_kaspi
        WHERE (
          sku_key IN ({placeholders})
          OR sku_id IN ({",".join("?" for _ in by_sku_id)})
        )
          AND COALESCE(courier_transmission_date, actual_shipment_date) IS NOT NULL
          AND datetime(COALESCE(courier_transmission_date, actual_shipment_date)) > datetime(?)
          AND date(COALESCE(courier_transmission_date, actual_shipment_date)) <= date(?)
        ORDER BY datetime(COALESCE(courier_transmission_date, actual_shipment_date)), store_code, order_id
        """,
        tuple(sku_keys) + tuple(by_sku_id) + (ANCHOR_SQLITE_TS, as_of_date),
    )
    trusted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    deduction_by_pool: dict[str, int] = defaultdict(int)
    for record in rows:
        size = str(record.get("my_size") or record.get("assigned_size") or "").strip()
        pool = by_sku_id.get(str(record.get("sku_id") or "")) or by_sku_size.get((str(record.get("sku_key") or ""), size))
        if pool is None:
            continue
        ship_dt = parse_dt(record.get("courier_transmission_date")) or parse_dt(record.get("actual_shipment_date"))
        status = str(record.get("internal_status") or "").upper()
        qty = int(record.get("quantity") or 0)
        mapping_blockers: list[str] = []
        if size and size != pool["canonical_size"]:
            mapping_blockers.append("ORDER_SIZE_MISMATCH_SKU_ID_VS_ASSIGNED_SIZE")
        out = {
            "stock_pool_id": pool["stock_pool_id"],
            "anchor_sku_id": pool["sku_id"],
            "anchor_sku_key": pool["sku_key"],
            "anchor_size": pool["canonical_size"],
            "order_id": record.get("order_id", ""),
            "store_code": record.get("store_code", ""),
            "order_sku_key": record.get("sku_key", ""),
            "order_sku_id": record.get("sku_id", ""),
            "order_size": size,
            "quantity": qty,
            "ship_datetime": ship_dt.isoformat(sep=" ") if ship_dt else "",
            "ship_datetime_source": "courier_transmission_date"
            if str(record.get("courier_transmission_date") or "").strip()
            else "actual_shipment_date",
            "planned_shipment_date": record.get("planned_shipment_date", ""),
            "kaspi_status": record.get("kaspi_status", ""),
            "internal_status": record.get("internal_status", ""),
            "kaspi_status_detail": record.get("kaspi_status_detail", ""),
            "kaspi_offer_name": record.get("kaspi_offer_name", ""),
            "source": record.get("source", ""),
            "source_file": record.get("source_file", ""),
            "mapping_blocker": "; ".join(mapping_blockers),
        }
        if status in TRUSTED_SHIPMENT_STATUSES:
            trusted.append(out)
            deduction_by_pool[pool["stock_pool_id"]] += qty
        else:
            out["exclude_reason"] = "internal_status_not_trusted_shipped_or_completed"
            excluded.append(out)
    return trusted, excluded, dict(deduction_by_pool)


def latest_snapshot_by_pool(conn: sqlite3.Connection, manifest: dict[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    latest = conn.execute("SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size").fetchone()[0] or ""
    out: dict[str, dict[str, Any]] = {}
    for aggregate in aggregate_manual_stock_counts(manifest):
        alias_values = []
        for sku_id in aggregate.applies_to_sku_ids:
            row = conn.execute(
                """
                SELECT sku_id, sku_key, my_size, current_stock
                FROM fact_inventory_snapshot_size
                WHERE snapshot_date = ? AND sku_id = ?
                """,
                (latest, sku_id),
            ).fetchone()
            if row is not None:
                alias_values.append(
                    {
                        "sku_id": row["sku_id"],
                        "sku_key": row["sku_key"],
                        "my_size": row["my_size"],
                        "current_stock": int(row["current_stock"] or 0),
                    }
                )
        primary = next((item for item in alias_values if item["sku_id"] == aggregate.sku_id), None)
        out[aggregate.stock_pool_id] = {
            "latest_snapshot_date": latest,
            "primary_current_stock": "" if primary is None else primary["current_stock"],
            "alias_values": alias_values,
        }
    return latest, out


def build_replay_rows(
    manifest: dict[str, Any],
    deductions: dict[str, int],
    snapshot: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_by_pool = {row["stock_pool_id"]: row for row in manifest["rows"]}
    for aggregate in aggregate_manual_stock_counts(manifest):
        shipped_qty = int(deductions.get(aggregate.stock_pool_id, 0))
        estimated = int(aggregate.quantity) - shipped_qty
        before = snapshot.get(aggregate.stock_pool_id, {})
        current = before.get("primary_current_stock", "")
        rows.append(
            {
                "stock_pool_id": aggregate.stock_pool_id,
                "sku_key": aggregate.sku_key,
                "sku_id": aggregate.sku_id,
                "applies_to_sku_ids": ";".join(aggregate.applies_to_sku_ids),
                "canonical_size": aggregate.canonical_size,
                "anchor_timestamp_at_almaty": aggregate.count_timestamp_at_almaty,
                "pre_shipment_anchor_qty": aggregate.quantity,
                "trusted_post_anchor_shipped_qty": shipped_qty,
                "estimated_current_stock_dry_run": estimated,
                "negative_stock_flag": str(estimated < 0).lower(),
                "latest_db_snapshot_date": before.get("latest_snapshot_date", ""),
                "latest_db_current_stock": current,
                "dry_run_delta_vs_latest_db_snapshot": "" if current == "" else estimated - int(current),
                "source_event_type": source_by_pool.get(aggregate.stock_pool_id, {}).get("source_event_type", ""),
                "source_delta": source_by_pool.get(aggregate.stock_pool_id, {}).get("source_delta", ""),
                "source_images": ";".join(aggregate.source_images),
                "alias_snapshot_values_json": json.dumps(before.get("alias_values", []), ensure_ascii=False),
            }
        )
    return rows


def write_doc(manifest: dict[str, Any], summary: dict[str, Any]) -> None:
    lines = [
        "# Astana Warehouse Manual Stock Count - 2026-06-04 Pre-Shipments",
        "",
        "Status: owner-approved local physical stock count for mapped rows; DB apply not included.",
        "",
        "Canonical machine-readable source:",
        "",
        f"- `config/anchors/manual_stock_counts/{MANIFEST_PATH.name}`",
        f"- `config/anchors/manual_stock_counts/{AGGREGATE_CSV_PATH.name}`",
        "",
        "Timing:",
        "",
        f"- Effective anchor timestamp: `{ANCHOR_TIMESTAMP}`.",
        "- Counted before the 04.06.2026 daily Kaspi shipments.",
        "- Replay must subtract trusted 04.06 daily shipments and later shipped/order movements after the anchor.",
        "",
        "Scope notes:",
        "",
        "- `3_in_1_men_sets` is quarantined because canonical SKU/card mapping is pending.",
        "- `CL_OC_MEN_LINE51_WHITE_S` is not materialized, overwritten, zeroed, or unknown-filled.",
        "- Rombik `S` remains one shared men/kids stock pool.",
        "",
        "Totals:",
        "",
        f"- Materialized rows: `{manifest['expected_totals']['raw_row_count']}`.",
        f"- Materialized units: `{manifest['expected_totals']['total_units']}`.",
        f"- Quarantined mapping-pending units: `{summary['quarantine']['units']}`.",
        f"- OCR roll-up reference total excluding LINE51 S: `{manifest['expected_totals']['known_rollup_reference_total_excluding_line51_s']}`.",
        "",
        "Dry-run replay:",
        "",
        f"- Evidence folder: `{summary['run_dir']}`.",
        f"- Trusted post-anchor shipped quantity on materialized rows: `{summary['shipments']['trusted_quantity']}`.",
        f"- Latest DB snapshot compared as before-state: `{summary['latest_snapshot_date']}`.",
        "- No DB write was performed.",
        "",
        "Validation:",
        "",
        "Use:",
        "",
        "```bash",
        f"python3 -m core.ops.manual_stock_count_manifest --manifest {MANIFEST_PATH}",
        "```",
    ]
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_closeout(summary: dict[str, Any]) -> str:
    stock_mismatch_lines = [
        f"- Negative dry-run stock rows: `{summary['stock_mismatches']['negative_rows']}`.",
        f"- Shipment size-conflict rows: `{summary['shipments']['trusted_size_conflict_rows']}`.",
    ]
    if summary["stock_mismatches"]["samples"]:
        stock_mismatch_lines.append("- First mismatch sample:")
        sample = summary["stock_mismatches"]["samples"][0]
        stock_mismatch_lines.append(
            f"  `{sample['sku_id']}` anchor `{sample['pre_shipment_anchor_qty']}`, "
            f"trusted shipped `{sample['trusted_post_anchor_shipped_qty']}`, "
            f"dry-run estimate `{sample['estimated_current_stock_dry_run']}`."
        )
    return "\n".join(
        [
            "# 2026-06-04 Manual Stock Pre-Shipment Ingest Dry-Run Closeout",
            "",
            f"Gate: {summary['gate']}",
            "",
            f"Reason: {summary['gate_reason']}",
            "",
            "## Artifacts",
            "",
            f"- Manifest: `{summary['manifest_path']}`",
            f"- Aggregate CSV: `{summary['aggregate_csv_path']}`",
            f"- Quarantine sidecar: `{summary['quarantine_path']}`",
            f"- Dry-run replay CSV: `{summary['replay_csv_path']}`",
            f"- Trusted shipments CSV: `{summary['trusted_shipments_csv_path']}`",
            f"- Mapping evidence CSV: `{summary['mapping_csv_path']}`",
            "",
            "## Handling Proof",
            "",
            f"- `3_in_1_men_sets`: quarantined rows `{summary['quarantine']['rows']}`, units `{summary['quarantine']['units']}`.",
            f"- LINE51 S row materialized: `{str(summary['line51_s']['manifest_row_present']).lower()}`.",
            f"- LINE51 S latest DB snapshot value preserved/read-only: `{summary['line51_s']['latest_db_current_stock']}` on `{summary['latest_snapshot_date']}`.",
            f"- Rombik shared S stock pool row count: `{summary['shared_pool']['rombik_s_rows']}`.",
            "",
            "## Shipment Replay",
            "",
            f"- Query window: `{summary['shipments']['query_window']}`.",
            f"- Trusted shipment rows: `{summary['shipments']['trusted_rows']}`.",
            f"- Trusted shipped quantity: `{summary['shipments']['trusted_quantity']}`.",
            f"- Excluded non-shipped/cancelled rows: `{summary['shipments']['excluded_rows']}`.",
            f"- Existing DB stock_anchor rows for this batch: `{summary['db_anchor_existing_rows']}`.",
            "",
            "## Stoplines",
            "",
            *stock_mismatch_lines,
            "",
            "## DB Boundary",
            "",
            "- No `db/app.db` mutation was performed.",
            "- No DB backup was created because there was no apply attempt.",
            "- Rollback for this dry-run is file-level removal of the generated manifest/evidence artifacts only.",
            "",
            "## Commands",
            "",
            "Command outputs are recorded in `.claude/SESSION_LOG.md` by the execution agent.",
        ]
    ) + "\n"


def build(args: argparse.Namespace) -> dict[str, Any]:
    manifest = build_manifest()
    write_json(MANIFEST_PATH, manifest)
    write_manual_stock_aggregate_csv(manifest, AGGREGATE_CSV_PATH)

    run_id = args.run_id or f"manual_stock_20260604_pre_shipments_dryrun_{datetime.now(ALMATY).strftime('%Y%m%d_%H%M%S')}"
    run_dir = PROJECT_ROOT / "exports/validation" / run_id
    quarantine_path = run_dir / "3_in_1_men_sets_quarantine.csv"
    write_csv(
        quarantine_path,
        quarantine_rows(),
        ["source_label", "source_image", "source_sku_key", "canonical_size", "quantity", "quarantine_reason", "status"],
    )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        mapping = validate_mapping(conn, manifest)
        mapping_path = run_dir / "canonical_mapping_check.csv"
        write_csv(
            mapping_path,
            mapping,
            [
                "row_id",
                "relation",
                "expected_sku_key",
                "expected_sku_id",
                "expected_size",
                "actual_sku_key",
                "actual_size",
                "dim_sku_size_active",
                "dim_sku_active",
                "article_map_active_rows",
                "status",
                "reason",
            ],
        )
        trusted, excluded, deductions = shipment_replay(conn, manifest, as_of_date=args.as_of_date)
        trusted_path = run_dir / "trusted_post_anchor_shipments.csv"
        excluded_path = run_dir / "excluded_post_anchor_order_movements.csv"
        shipment_fields = [
            "stock_pool_id",
            "anchor_sku_id",
            "anchor_sku_key",
            "anchor_size",
            "order_id",
            "store_code",
            "order_sku_key",
            "order_sku_id",
            "order_size",
            "quantity",
            "ship_datetime",
            "ship_datetime_source",
            "planned_shipment_date",
            "kaspi_status",
            "internal_status",
            "kaspi_status_detail",
            "kaspi_offer_name",
            "source",
            "source_file",
            "mapping_blocker",
            "exclude_reason",
        ]
        write_csv(trusted_path, trusted, shipment_fields)
        write_csv(excluded_path, excluded, shipment_fields)
        latest_snapshot_date, snapshot = latest_snapshot_by_pool(conn, manifest)
        replay_rows = build_replay_rows(manifest, deductions, snapshot)
        replay_path = run_dir / "current_stock_replay_dry_run.csv"
        write_csv(
            replay_path,
            replay_rows,
            [
                "stock_pool_id",
                "sku_key",
                "sku_id",
                "applies_to_sku_ids",
                "canonical_size",
                "anchor_timestamp_at_almaty",
                "pre_shipment_anchor_qty",
                "trusted_post_anchor_shipped_qty",
                "estimated_current_stock_dry_run",
                "negative_stock_flag",
                "latest_db_snapshot_date",
                "latest_db_current_stock",
                "dry_run_delta_vs_latest_db_snapshot",
                "source_event_type",
                "source_delta",
                "source_images",
                "alias_snapshot_values_json",
            ],
        )
        db_anchor_existing_rows = conn.execute(
            "SELECT COUNT(*) FROM stock_anchor WHERE anchor_id = ? OR source_path = ?",
            (BATCH_ID, str(MANIFEST_PATH)),
        ).fetchone()[0]
        line51_s = conn.execute(
            """
            SELECT current_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ? AND sku_id = 'CL_OC_MEN_LINE51_WHITE_S'
            """,
            (latest_snapshot_date,),
        ).fetchone()
    finally:
        conn.close()

    mapping_failures = [row for row in mapping if row["status"] != "PASS"]
    size_conflicts = [row for row in trusted if row.get("mapping_blocker")]
    negative_rows = [row for row in replay_rows if row["negative_stock_flag"] == "true"]
    gate = "GREEN"
    gate_reasons = []
    if mapping_failures:
        gate = "RED"
        gate_reasons.append("canonical dim_sku_size mapping failures")
    if size_conflicts:
        gate = "RED"
        gate_reasons.append("post-anchor shipment size conflicts")
    if negative_rows:
        gate = "RED"
        gate_reasons.append("negative dry-run current stock rows")
    if gate != "RED":
        gate = "YELLOW"
        gate_reasons.append("DB apply not authorized and 3_in_1_men_sets quarantined")
    summary = {
        "generated_at": datetime.now(ALMATY).isoformat(timespec="seconds"),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "manifest_path": str(MANIFEST_PATH),
        "aggregate_csv_path": str(AGGREGATE_CSV_PATH),
        "doc_path": str(DOC_PATH),
        "quarantine_path": str(quarantine_path),
        "mapping_csv_path": str(mapping_path),
        "trusted_shipments_csv_path": str(trusted_path),
        "excluded_shipments_csv_path": str(excluded_path),
        "replay_csv_path": str(replay_path),
        "source_evidence": {
            "primary_ocr_report": file_evidence(SOURCE_REPORT),
            "merged_total_append": file_evidence(TOTAL_REPORT),
            "db_app": file_evidence(DB_PATH),
        },
        "manifest": {
            "batch_id": BATCH_ID,
            "rows": len(manifest["rows"]),
            "aggregate_rows": len(aggregate_manual_stock_counts(manifest)),
            "units": manifest["expected_totals"]["total_units"],
        },
        "mapping": {
            "rows_checked": len(mapping),
            "failures": len(mapping_failures),
        },
        "quarantine": {
            "rows": len(quarantine_rows()),
            "units": sum(row["quantity"] for row in quarantine_rows()),
            "reason": "canonical SKU/card mapping pending",
        },
        "line51_s": {
            "manifest_row_present": any(row["sku_id"] == "CL_OC_MEN_LINE51_WHITE_S" for row in manifest["rows"]),
            "latest_db_current_stock": "" if line51_s is None else int(line51_s["current_stock"] or 0),
        },
        "shared_pool": {
            "rombik_s_rows": sum(1 for row in manifest["rows"] if row["stock_pool_id"] == "SHARED_ROMBIK_BLACK_S_MEN_KIDS"),
        },
        "shipments": {
            "query_window": f"{ANCHOR_TIMESTAMP} < ship_datetime <= {args.as_of_date} 23:59:59 Asia/Almaty",
            "trusted_rows": len(trusted),
            "trusted_quantity": sum(int(row["quantity"] or 0) for row in trusted),
            "trusted_size_conflict_rows": len(size_conflicts),
            "excluded_rows": len(excluded),
        },
        "stock_mismatches": {
            "negative_rows": len(negative_rows),
            "samples": negative_rows[:5],
        },
        "latest_snapshot_date": latest_snapshot_date,
        "db_anchor_existing_rows": int(db_anchor_existing_rows),
        "db_write": {
            "performed": False,
            "backup_path": "",
            "rollback": "No DB write performed. Remove generated artifacts only if this dry-run should be discarded.",
        },
        "gate": gate,
        "gate_reason": "; ".join(gate_reasons),
    }
    write_json(run_dir / "summary.json", summary)
    write_doc(manifest, summary)
    closeout_path = run_dir / "closeout.md"
    closeout_path.write_text(render_closeout(summary), encoding="utf-8")
    summary["closeout_path"] = str(closeout_path)
    write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of-date", default="2026-06-11", help="Replay through this date, inclusive")
    parser.add_argument("--run-id", default="", help="Optional deterministic validation run id")
    args = parser.parse_args()
    summary = build(args)
    if summary["gate"] == "RED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
