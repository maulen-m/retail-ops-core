#!/usr/bin/env python3
"""Materialize owner-approved temporary OCR stock overrides.

This is intentionally temporary. It prioritizes owner-approved warehouse OCR and
manual count surfaces while the main stock-truth refactor is happening in a
separate worktree. Dry-run is the default.

Apply gates:
  ENABLE_TEMP_OCR_STOCK_OVERRIDE_WRITE=1
  ALLOW_PRODUCTION_TEMP_OCR_STOCK_OVERRIDE_WRITE=1 for db/app.db
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH  # noqa: E402
from core.db.ledger import rebuild_snapshot_from_ledger  # noqa: E402
from core.ops.manual_stock_count_manifest import (  # noqa: E402
    APPROVED_MANIFEST_DIR,
    aggregate_manual_stock_counts,
    load_approved_manual_stock_manifest,
)
from scripts.backup_db import backup_database  # noqa: E402


ALMATY = ZoneInfo("Asia/Almaty")
ENV_GATE = "ENABLE_TEMP_OCR_STOCK_OVERRIDE_WRITE"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_TEMP_OCR_STOCK_OVERRIDE_WRITE"
INPUT_SOURCE = "OWNER_APPROVED_TEMP_OCR_OVERRIDE"
CREATED_BY = "codex_temp_ocr_stock_override_2026_06_16"
EVENT_TYPE = "ADJUSTMENT"
STORE_CODE = "UNIVERSAL"
JUNE11_BATCH_ID = "ASTANA_WAREHOUSE_OCR_2026_06_11_AFTER_DAILY_SHIPPING"
JUNE11_EVENT_TS = "2026-06-11T22:00:00+05:00"
JUNE11_EVENT_DATE = "2026-06-11"
SNAPSHOT_SOURCE_DOC = (
    PROJECT_ROOT
    / "docs/plan/green_path_2026-06/reconciliation/"
    "count_batch_2026-06-11_2200/count_batch_canonical_DRAFT.md"
)
OWNER_DECISION_DOC = PROJECT_ROOT / "docs/plan/green_path_2026-06/OWNER_DECISIONS_RECORDED.yaml"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports/validation/temporary_ocr_stock_override"
CURRENT_DIR = PROJECT_ROOT / "exports/current/temporary_ocr_stock_override"
TEMPORARY_UNTIL = (
    "temporary_until_main_orchestrator_refactor_returns_conflict_free_single_source_of_truth"
)
SUPERSESSION_POLICY = (
    "future_main_refactor_results_may_override_this_temporary_owner_approved_stock_layer"
)

PARKED_JUNE11_ROWS: list[dict[str, Any]] = [
    {
        "batch_id": JUNE11_BATCH_ID,
        "source_image": "3_in_1_with_logotypes_complete_stock_snapshot.JPG",
        "family_guess": "3_in_1_with_logotypes",
        "reason": "F-1 mapping pending; may be distinct from 2026-06-04 unmapped 3_in_1_men_sets",
        "mode": "FULL_SUPERSEDE_SNAPSHOT",
        "rows": "L=20;XL=44;2XL=55;3XL=43;4XL=30;S=NOT_CAPTURED;M=NOT_CAPTURED",
    },
    {
        "batch_id": JUNE11_BATCH_ID,
        "source_image": "rush_white_and_rush_black.JPG",
        "family_guess": "RUSH_WHITE / RUSH_BLACK",
        "reason": "F-2 mapping flag; do not merge into Berserk/Nike/Rush families without catalog proof",
        "mode": "ADDITION",
        "rows": "white S+1 M+1 L+2 2XL+1 3XL+1; black L+1 XL+1",
    },
    {
        "batch_id": JUNE11_BATCH_ID,
        "source_image": "t-shirts_white_and_t-shirts_black.JPG",
        "family_guess": "T-SHIRT short-sleeve WHITE / BLACK",
        "reason": "F-3 mapping flag; do not merge into Berserk/Nike/T-shirt families without catalog proof",
        "mode": "ADDITION",
        "rows": "white L+5 XL+1 2XL+1; black L+3 XL+2",
    },
]

OWNER_CONFLICT_HOLD_ROWS: list[dict[str, Any]] = [
    {
        "sku_key": "CL_OC_MEN_LINE52_BLACK",
        "sku_id": "CL_OC_MEN_LINE52_BLACK_XL",
        "my_size": "XL",
        "stock_pool_id": "CL_OC_MEN_LINE52_BLACK_XL",
        "source_image": "line52_additions_but-S-full.JPG",
        "source_doc": str(SNAPSHOT_SOURCE_DOC),
        "source_event_ts": JUNE11_EVENT_TS,
        "reason": (
            "owner challenged >100 temporary stock on 2026-06-16; human/OCR "
            "understanding is approximately 13 total warehouse units, not "
            "old-ledger balance plus addition"
        ),
    },
]


@dataclass(frozen=True)
class SourceRow:
    row_id: str
    batch_id: str
    event_ts: str
    event_date: str
    boundary_inclusive: bool
    semantic: str
    sku_key: str
    my_size: str
    sku_id: str
    stock_pool_id: str
    applies_to_sku_ids: tuple[str, ...]
    quantity: int
    source_image: str
    source_doc: str
    mode: str
    confidence: str = ""
    notes: str = ""


@dataclass
class EventCandidate:
    row_id: str
    batch_id: str
    event_date: str
    semantic: str
    sku_key: str
    my_size: str
    sku_id: str
    primary_write_sku_id: str
    stock_pool_id: str
    applies_to_sku_ids: tuple[str, ...]
    source_quantity: int
    balance_before_override: int
    qty_change: int
    predicted_balance_after_override: int
    source_image: str
    source_doc: str
    mode: str
    boundary: str
    idempotency_key: str
    action: str
    reference_type: str
    notes: str
    confidence: str = ""


@dataclass
class Plan:
    candidates: list[EventCandidate] = field(default_factory=list)
    blocked_rows: list[dict[str, Any]] = field(default_factory=list)
    parked_rows: list[dict[str, Any]] = field(default_factory=list)
    owner_hold_rows: list[dict[str, Any]] = field(default_factory=list)
    existing_rows: list[dict[str, Any]] = field(default_factory=list)
    report_rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def insert_candidates(self) -> list[EventCandidate]:
        return [row for row in self.candidates if row.action == "INSERT"]


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    with _connect(path, readonly=True) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "")


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(f"{db_path}-wal"), Path(f"{db_path}-shm"), Path(f"{db_path}-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise RuntimeError(f"refusing production apply while SQLite sidecars exist: {joined}")


def _is_production_db(path: Path) -> bool:
    try:
        return path.resolve() == DEFAULT_DB_PATH.resolve()
    except FileNotFoundError:
        return path.absolute() == DEFAULT_DB_PATH.absolute()


def _normalize_size(size: str) -> str:
    text = str(size).strip()
    if "/" in text:
        return text.split("/")[-1].strip()
    return text


def _iso_date(timestamp_text: str) -> str:
    return timestamp_text[:10]


def _source_rows_from_approved_manifests() -> list[SourceRow]:
    manifest_pairs = [
        (path, load_approved_manual_stock_manifest(path))
        for path in sorted(APPROVED_MANIFEST_DIR.glob("*.approved.json"))
    ]
    source_rows: list[SourceRow] = []
    for manifest_path, manifest in sorted(
        manifest_pairs,
        key=lambda item: int(item[1]["precedence"]["rank"]),
    ):
        count_scope = manifest.get("count_scope") or {}
        method = str(count_scope.get("method") or "").lower()
        aggregates = aggregate_manual_stock_counts(manifest)
        for aggregate in aggregates:
            timing_policy = ""
            source_event_type = ""
            # Aggregates are materialized owner-approved counts. If the source
            # said "addition", that addition was already folded into quantity.
            event_date = _iso_date(aggregate.count_timestamp_at_almaty)
            boundary_inclusive = "before" not in method and "pre" not in method
            matching_rows = [
                row
                for row in manifest.get("rows") or []
                if row.get("stock_pool_id") == aggregate.stock_pool_id
                and row.get("sku_id") == aggregate.sku_id
                and row.get("canonical_size") == aggregate.canonical_size
            ]
            if matching_rows:
                timing_policy = str(matching_rows[0].get("timing_policy") or "")
                source_event_type = str(matching_rows[0].get("source_event_type") or "")
                if "pre_" in timing_policy:
                    boundary_inclusive = False
            row_id = (
                matching_rows[0].get("row_id")
                if len(matching_rows) == 1
                else f"{aggregate.batch_id}:{aggregate.stock_pool_id}"
            )
            source_rows.append(
                SourceRow(
                    row_id=str(row_id),
                    batch_id=aggregate.batch_id,
                    event_ts=aggregate.count_timestamp_at_almaty,
                    event_date=event_date,
                    boundary_inclusive=boundary_inclusive,
                    semantic="FULL_SUPERSEDE",
                    sku_key=aggregate.sku_key,
                    my_size=aggregate.canonical_size,
                    sku_id=aggregate.sku_id,
                    stock_pool_id=aggregate.stock_pool_id,
                    applies_to_sku_ids=tuple(aggregate.applies_to_sku_ids),
                    quantity=int(aggregate.quantity),
                    source_image=";".join(aggregate.source_images),
                    source_doc=str(manifest_path),
                    mode=source_event_type or "approved_manual_effective_count",
                    confidence="OWNER_APPROVED",
                    notes=timing_policy,
                )
            )
    return source_rows


def _make_sku_id(sku_key: str, size: str) -> str:
    return f"{sku_key}_{_normalize_size(size)}"


def _june11_row(
    row_id: str,
    *,
    sku_key: str,
    size: str,
    units: int,
    semantic: str,
    image: str,
    mode: str,
    confidence: str,
    notes: str = "",
    stock_pool_id: str | None = None,
    applies_to_sku_ids: tuple[str, ...] | None = None,
) -> SourceRow:
    my_size = _normalize_size(size)
    sku_id = _make_sku_id(sku_key, my_size)
    return SourceRow(
        row_id=row_id,
        batch_id=JUNE11_BATCH_ID,
        event_ts=JUNE11_EVENT_TS,
        event_date=JUNE11_EVENT_DATE,
        boundary_inclusive=True,
        semantic=semantic,
        sku_key=sku_key,
        my_size=my_size,
        sku_id=sku_id,
        stock_pool_id=stock_pool_id or sku_id,
        applies_to_sku_ids=applies_to_sku_ids or (sku_id,),
        quantity=units,
        source_image=image,
        source_doc=str(SNAPSHOT_SOURCE_DOC),
        mode=mode,
        confidence=confidence,
        notes=notes,
    )


def _source_rows_from_june11_consensus() -> list[SourceRow]:
    rows: list[SourceRow] = []

    for idx, (size, units) in enumerate(
        [("110/22", 12), ("120/24", 9), ("130/26", 54), ("140/28", 32), ("150/30", 28)],
        start=1,
    ):
        rows.append(
            _june11_row(
                f"JUNE11-KIDS31-FULL-{idx:03d}",
                sku_key="CL_NEW-CLO_KIDS_KID-31_BLACK",
                size=size,
                units=units,
                semantic="FULL_SUPERSEDE",
                image="3_in_1_kids_complete_stock_snapshot.JPG",
                mode="FULL_SUPERSEDE_SNAPSHOT",
                confidence="HIGH" if size != "120/24" else "OWNER_CONFIRMED",
            )
        )

    for idx, (size, units) in enumerate([("XL", 1), ("2XL", 1)], start=1):
        rows.append(
            _june11_row(
                f"JUNE11-HUS-ADD-{idx:03d}",
                sku_key="CL_NEW-CLO2_MEN_HUS_GREEN",
                size=size,
                units=units,
                semantic="ADDITION",
                image="HUS_addition.JPG",
                mode="ADDITION",
                confidence="HIGH",
                notes="color inferred from 2026-06-04 family table",
            )
        )

    rows.append(
        _june11_row(
            "JUNE11-ROMBIK-SHARED-S-ADD-001",
            sku_key="CL_NEW-CLO_MEN_ROMBIK_BLACK",
            size="S",
            units=1,
            semantic="ADDITION",
            image="Rombik_men_and_kids_all-addtions.JPG",
            mode="ADDITION",
            confidence="HIGH",
            notes="shared men/kids S pool per approved convention",
            stock_pool_id="SHARED_ROMBIK_BLACK_S_MEN_KIDS",
            applies_to_sku_ids=(
                "CL_NEW-CLO_MEN_ROMBIK_BLACK_S",
                "CL_NEW-CLO_KID_ROMBIK_BLACK_S",
            ),
        )
    )
    for idx, (size, units) in enumerate([("XL", 3), ("2XL", 2)], start=1):
        rows.append(
            _june11_row(
                f"JUNE11-ROMBIK-MEN-ADD-{idx:03d}",
                sku_key="CL_NEW-CLO_MEN_ROMBIK_BLACK",
                size=size,
                units=units,
                semantic="ADDITION",
                image="Rombik_men_and_kids_all-addtions.JPG",
                mode="ADDITION",
                confidence="HIGH",
            )
        )
    rows.append(
        _june11_row(
            "JUNE11-ROMBIK-KIDS-28-ADD-001",
            sku_key="CL_NEW-CLO_KID_ROMBIK_BLACK",
            size="140/28",
            units=2,
            semantic="ADDITION",
            image="Rombik_men_and_kids_all-addtions.JPG",
            mode="ADDITION",
            confidence="HIGH",
            notes="kids ROMBIK 140/28 row",
        )
    )

    mixed_specs = [
        (
            "LINE51",
            "CL_OC_MEN_LINE51_WHITE",
            "line51_additions_but-S-full.JPG",
            [("S", 82, "FULL_SUPERSEDE", "MED_CONSENSUS"), ("M", 2, "ADDITION", "HIGH"), ("L", 6, "ADDITION", "HIGH"), ("XL", 7, "ADDITION", "HIGH"), ("2XL", 4, "ADDITION", "HIGH"), ("3XL", 1, "ADDITION", "HIGH"), ("4XL", 1, "ADDITION", "HIGH")],
        ),
        (
            "LINE52",
            "CL_OC_MEN_LINE52_BLACK",
            "line52_additions_but-S-full.JPG",
            [("S", 72, "FULL_SUPERSEDE", "HIGH"), ("M", 5, "ADDITION", "HIGH"), ("L", 11, "ADDITION", "HIGH"), ("XL", 12, "ADDITION", "HIGH"), ("2XL", 20, "ADDITION", "MED"), ("3XL", 13, "ADDITION", "HIGH"), ("4XL", 1, "ADDITION", "HIGH")],
        ),
    ]
    for family, sku_key, image, specs in mixed_specs:
        for idx, (size, units, semantic, confidence) in enumerate(specs, start=1):
            rows.append(
                _june11_row(
                    f"JUNE11-{family}-{semantic}-{idx:03d}",
                    sku_key=sku_key,
                    size=size,
                    units=units,
                    semantic=semantic,
                    image=image,
                    mode="MIXED_S_FULL_REST_ADDITION",
                    confidence=confidence,
                    notes="arrow on S row only; other rows are additions" if family in {"LINE51", "LINE52"} else "",
                )
            )

    for idx, (size, units) in enumerate(
        [("S", 1), ("M", 1), ("L", 6), ("XL", 13), ("2XL", 10), ("3XL", 6), ("4XL", 3)],
        start=1,
    ):
        rows.append(
            _june11_row(
                f"JUNE11-LINE61-ADD-{idx:03d}",
                sku_key="CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                size=size,
                units=units,
                semantic="ADDITION",
                image="line61_additions.JPG",
                mode="ADDITION",
                confidence="HIGH",
            )
        )

    berserk_rush = [
        ("WHITE", "XL", 2),
        ("WHITE", "2XL", 1),
        ("BLACK", "L", 2),
        ("BLACK", "XL", 1),
        ("BLACK", "2XL", 1),
    ]
    for idx, (color, size, units) in enumerate(berserk_rush, start=1):
        rows.append(
            _june11_row(
                f"JUNE11-BERSERK-RUSH-{color}-ADD-{idx:03d}",
                sku_key=f"CL_NEW-CLO_MEN_BERSERK-RUSH_{color}",
                size=size,
                units=units,
                semantic="ADDITION",
                image="berserk_rush.JPG",
                mode="ADDITION",
                confidence="HIGH",
                notes="explicit Berserk long-sleeve sheet",
            )
        )

    berserk_shirt = [
        ("WHITE", "S", 1),
        ("WHITE", "L", 1),
        ("WHITE", "XL", 1),
        ("BLACK", "M", 1),
        ("BLACK", "XL", 1),
    ]
    for idx, (color, size, units) in enumerate(berserk_shirt, start=1):
        rows.append(
            _june11_row(
                f"JUNE11-BERSERK-SHIRT-{color}-ADD-{idx:03d}",
                sku_key=f"CL_NEW-CLO_MEN_BERSERK-SHIRT_{color}",
                size=size,
                units=units,
                semantic="ADDITION",
                image="berserk_t-shirts.JPG",
                mode="ADDITION",
                confidence="HIGH",
                notes="explicit Berserk short-sleeve sheet; distinct from F-3 T-SHIRT",
            )
        )

    rows.append(
        _june11_row(
            "JUNE11-SPIDER-BLACK-M-ADD-001",
            sku_key="CL_NEW-CLO_MEN_SPIDER-RUSH_BLACK",
            size="M",
            units=1,
            semantic="ADDITION",
            image="spider_rush_addition.JPG",
            mode="ADDITION",
            confidence="HIGH",
            notes="color inferred from 2026-06-04 family table",
        )
    )

    return rows


def _load_active_sku_rows(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT ds.sku_id, ds.sku_key, ds.my_size, ds.active_flag AS size_active,
               COALESCE(d.active_flag, 1) AS sku_active
        FROM dim_sku_size ds
        LEFT JOIN dim_sku d ON d.sku_key = ds.sku_key
        """
    ).fetchall()
    return {str(row["sku_id"]): row for row in rows}


def _db_balance(
    conn: sqlite3.Connection,
    sku_ids: tuple[str, ...],
    event_date: str,
    *,
    inclusive: bool,
) -> int:
    if not sku_ids:
        return 0
    op = "<=" if inclusive else "<"
    placeholders = ",".join("?" for _ in sku_ids)
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(qty_change), 0) AS balance
        FROM stock_ledger
        WHERE sku_id IN ({placeholders})
          AND event_date {op} ?
          AND COALESCE(store_code, ?) = ?
        """,
        [*sku_ids, event_date, STORE_CODE, STORE_CODE],
    ).fetchone()
    return int(row["balance"] or 0)


def _planned_balance(
    planned: list[EventCandidate],
    sku_ids: tuple[str, ...],
    event_date: str,
    *,
    inclusive: bool,
) -> int:
    total = 0
    for event in planned:
        if event.primary_write_sku_id not in sku_ids:
            continue
        if event.event_date < event_date or (inclusive and event.event_date == event_date):
            total += event.qty_change
    return total


def _existing_idempotency_keys(conn: sqlite3.Connection, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"SELECT idempotency_key FROM stock_ledger WHERE idempotency_key IN ({placeholders})",
        keys,
    ).fetchall()
    return {str(row["idempotency_key"]) for row in rows}


def _idempotency_key(row: SourceRow) -> str:
    return (
        f"TEMP_OCR_OVERRIDE:{row.batch_id}:{row.row_id}:"
        f"{row.stock_pool_id}:{row.event_ts}:{row.semantic}"
    )


def _validate_source_row(row: SourceRow, active_skus: dict[str, sqlite3.Row]) -> list[str]:
    errors: list[str] = []
    if row.sku_id not in active_skus:
        errors.append(f"PRIMARY_SKU_ID_MISSING:{row.sku_id}")
    else:
        sku_row = active_skus[row.sku_id]
        if int(sku_row["size_active"] or 0) != 1:
            errors.append(f"PRIMARY_SKU_SIZE_INACTIVE:{row.sku_id}")
        if int(sku_row["sku_active"] or 0) != 1:
            errors.append(f"PRIMARY_SKU_INACTIVE:{row.sku_key}")
        if str(sku_row["sku_key"]) != row.sku_key:
            errors.append(f"PRIMARY_SKU_KEY_MISMATCH:{row.sku_id}:{sku_row['sku_key']}!={row.sku_key}")
        if str(sku_row["my_size"]).strip() != row.my_size:
            errors.append(f"PRIMARY_SIZE_MISMATCH:{row.sku_id}:{sku_row['my_size']}!={row.my_size}")
    for alias in row.applies_to_sku_ids:
        if alias not in active_skus:
            errors.append(f"ALIAS_SKU_ID_MISSING:{alias}")
    if row.quantity < 0:
        errors.append(f"NEGATIVE_SOURCE_QUANTITY:{row.quantity}")
    return errors


def build_plan(conn: sqlite3.Connection, *, snapshot_date: date) -> Plan:
    source_rows = _source_rows_from_approved_manifests() + _source_rows_from_june11_consensus()
    source_rows.sort(key=lambda row: (row.event_ts, row.batch_id, row.row_id))

    plan = Plan()
    plan.parked_rows.extend(PARKED_JUNE11_ROWS)
    plan.owner_hold_rows.extend(OWNER_CONFLICT_HOLD_ROWS)
    active_skus = _load_active_sku_rows(conn)
    existing_keys = _existing_idempotency_keys(conn, [_idempotency_key(row) for row in source_rows])
    planned: list[EventCandidate] = []

    for row in source_rows:
        errors = _validate_source_row(row, active_skus)
        key = _idempotency_key(row)
        if errors:
            plan.blocked_rows.append(
                {
                    "row_id": row.row_id,
                    "batch_id": row.batch_id,
                    "sku_key": row.sku_key,
                    "sku_id": row.sku_id,
                    "my_size": row.my_size,
                    "stock_pool_id": row.stock_pool_id,
                    "quantity": row.quantity,
                    "source_image": row.source_image,
                    "source_doc": row.source_doc,
                    "errors": ";".join(errors),
                    "temporary_policy": TEMPORARY_UNTIL,
                }
            )
            continue

        if row.semantic == "ADDITION":
            balance_before = (
                _db_balance(conn, row.applies_to_sku_ids, row.event_date, inclusive=True)
                + _planned_balance(planned, row.applies_to_sku_ids, row.event_date, inclusive=True)
            )
            qty_change = row.quantity
            reference_type = "TEMP_OCR_COUNT_ADDITION"
            boundary = "addition_on_top_of_after_daily_shipping_balance"
        else:
            balance_before = (
                _db_balance(conn, row.applies_to_sku_ids, row.event_date, inclusive=row.boundary_inclusive)
                + _planned_balance(
                    planned,
                    row.applies_to_sku_ids,
                    row.event_date,
                    inclusive=row.boundary_inclusive,
                )
            )
            qty_change = row.quantity - balance_before
            reference_type = "TEMP_OCR_FULL_SUPERSEDE"
            boundary = "inclusive" if row.boundary_inclusive else "exclusive_pre_day"

        action = "INSERT"
        if key in existing_keys:
            action = "EXISTS"
        elif qty_change == 0:
            action = "NOOP_ZERO_DELTA"

        candidate = EventCandidate(
            row_id=row.row_id,
            batch_id=row.batch_id,
            event_date=row.event_date,
            semantic=row.semantic,
            sku_key=row.sku_key,
            my_size=row.my_size,
            sku_id=row.sku_id,
            primary_write_sku_id=row.sku_id,
            stock_pool_id=row.stock_pool_id,
            applies_to_sku_ids=row.applies_to_sku_ids,
            source_quantity=row.quantity,
            balance_before_override=balance_before,
            qty_change=qty_change,
            predicted_balance_after_override=balance_before + qty_change,
            source_image=row.source_image,
            source_doc=row.source_doc,
            mode=row.mode,
            boundary=boundary,
            idempotency_key=key,
            action=action,
            reference_type=reference_type,
            notes=row.notes,
            confidence=row.confidence,
        )
        plan.candidates.append(candidate)
        if action == "INSERT":
            planned.append(candidate)
        elif action == "EXISTS":
            plan.existing_rows.append(_candidate_to_record(candidate))

    plan.report_rows = _build_activation_report_rows(
        conn,
        source_rows=source_rows,
        candidates=plan.candidates,
        planned=planned,
        snapshot_date=snapshot_date,
        active_skus=active_skus,
    )
    return plan


def _apply_owner_conflict_holds(rows: list[dict[str, Any]]) -> None:
    holds_by_sku_id = {str(row["sku_id"]): row for row in OWNER_CONFLICT_HOLD_ROWS}
    for row in rows:
        hold = holds_by_sku_id.get(str(row.get("sku_id") or ""))
        if hold is None:
            continue
        reason = str(hold["reason"])
        existing_notes = str(row.get("notes") or "").strip()
        row["activation_recommendation"] = "OWNER_CONFLICT_HOLD_DO_NOT_ACTIVATE_PENDING_RECOUNT"
        row["authority"] = "OWNER_CONFLICT_HOLD_SUPERSEDES_TEMP_ACTIVATION"
        row["source_semantic"] = f"{row.get('source_semantic') or ''}+OWNER_CONFLICT_HOLD"
        row["candidate_action"] = "OWNER_HOLD"
        row["notes"] = (
            f"{existing_notes}; OWNER_CONFLICT_HOLD: {reason}"
            if existing_notes
            else f"OWNER_CONFLICT_HOLD: {reason}"
        )


def _candidate_to_record(candidate: EventCandidate) -> dict[str, Any]:
    record = candidate.__dict__.copy()
    record["applies_to_sku_ids"] = ";".join(candidate.applies_to_sku_ids)
    record["temporary_policy"] = TEMPORARY_UNTIL
    record["supersession_policy"] = SUPERSESSION_POLICY
    return record


def _snapshot_balance_after_plan(
    conn: sqlite3.Connection,
    sku_ids: tuple[str, ...],
    snapshot_date: date,
    planned: list[EventCandidate],
) -> int:
    boundary = snapshot_date.isoformat()
    return _db_balance(conn, sku_ids, boundary, inclusive=False) + _planned_balance(
        planned,
        sku_ids,
        boundary,
        inclusive=False,
    )


def _size_sort_key(size: str) -> tuple[int, str]:
    order = {
        "S": 10,
        "M": 20,
        "L": 30,
        "XL": 40,
        "2XL": 50,
        "3XL": 60,
        "4XL": 70,
        "22": 122,
        "24": 124,
        "26": 126,
        "28": 128,
        "30": 130,
    }
    return (order.get(str(size).strip(), 999), str(size))


def _build_activation_report_rows(
    conn: sqlite3.Connection,
    *,
    source_rows: list[SourceRow],
    candidates: list[EventCandidate],
    planned: list[EventCandidate],
    snapshot_date: date,
    active_skus: dict[str, sqlite3.Row],
) -> list[dict[str, Any]]:
    generated_at = datetime.now(ALMATY).isoformat(timespec="seconds")
    by_pool: dict[str, list[SourceRow]] = {}
    for row in source_rows:
        by_pool.setdefault(row.stock_pool_id, []).append(row)

    candidate_by_pool = {candidate.stock_pool_id: candidate for candidate in candidates}
    family_keys = sorted({row.sku_key for row in source_rows})
    rows: list[dict[str, Any]] = []
    emitted: set[str] = set()

    for stock_pool_id, pool_rows in sorted(by_pool.items()):
        latest = sorted(pool_rows, key=lambda item: (item.event_ts, item.batch_id, item.row_id))[-1]
        candidate = candidate_by_pool.get(stock_pool_id)
        pool_stock = _snapshot_balance_after_plan(
            conn,
            latest.applies_to_sku_ids,
            snapshot_date,
            planned,
        )
        for alias in latest.applies_to_sku_ids:
            sku_row = active_skus.get(alias)
            sku_key = str(sku_row["sku_key"]) if sku_row is not None else latest.sku_key
            my_size = str(sku_row["my_size"]) if sku_row is not None else latest.my_size
            if alias in emitted:
                continue
            emitted.add(alias)
            rows.append(
                {
                    "generated_at_almaty": generated_at,
                    "snapshot_date": snapshot_date.isoformat(),
                    "sku_key": sku_key,
                    "sku_id": alias,
                    "my_size": my_size,
                    "stock_pool_id": stock_pool_id,
                    "primary_write_sku_id": latest.sku_id,
                    "shared_pool": "yes" if len(latest.applies_to_sku_ids) > 1 else "no",
                    "alias_group": ";".join(latest.applies_to_sku_ids),
                    "temporary_current_stock": pool_stock,
                    "activation_recommendation": (
                        "ACTIVATE_OK_POSITIVE_TEMP_STOCK"
                        if pool_stock > 0
                        else "DO_NOT_ACTIVATE_ZERO_OR_NEGATIVE_TEMP_STOCK"
                    ),
                    "authority": "TEMP_OCR_OVERRIDE_OR_PRIOR_FRESHEST_PER_OWNER_PRECEDENCE",
                    "source_batch_id": latest.batch_id,
                    "source_event_ts": latest.event_ts,
                    "source_image": latest.source_image,
                    "source_doc": latest.source_doc,
                    "source_mode": latest.mode,
                    "source_semantic": latest.semantic,
                    "source_quantity": latest.quantity,
                    "candidate_action": candidate.action if candidate else "",
                    "candidate_qty_change": candidate.qty_change if candidate else "",
                    "temporary_override_until": TEMPORARY_UNTIL,
                    "supersession_policy": SUPERSESSION_POLICY,
                    "notes": latest.notes,
                }
            )

    # Include sibling sizes for covered families so activation agents can avoid
    # treating absent OCR cells as zero.
    active_rows = [
        row
        for row in active_skus.values()
        if str(row["sku_key"]) in family_keys
        and int(row["size_active"] or 0) == 1
        and int(row["sku_active"] or 0) == 1
    ]
    for row in sorted(active_rows, key=lambda r: (str(r["sku_key"]), _size_sort_key(str(r["my_size"])), str(r["sku_id"]))):
        sku_id = str(row["sku_id"])
        if sku_id in emitted:
            continue
        stock = _snapshot_balance_after_plan(conn, (sku_id,), snapshot_date, planned)
        emitted.add(sku_id)
        rows.append(
            {
                "generated_at_almaty": generated_at,
                "snapshot_date": snapshot_date.isoformat(),
                "sku_key": str(row["sku_key"]),
                "sku_id": sku_id,
                "my_size": str(row["my_size"]),
                "stock_pool_id": sku_id,
                "primary_write_sku_id": sku_id,
                "shared_pool": "no",
                "alias_group": sku_id,
                "temporary_current_stock": stock,
                "activation_recommendation": (
                    "ACTIVATE_OK_POSITIVE_PRIOR_FRESHEST_STOCK"
                    if stock > 0
                    else "DO_NOT_ACTIVATE_ZERO_OR_NEGATIVE_PRIOR_FRESHEST_STOCK"
                ),
                "authority": "NO_DIRECT_TEMP_OCR_ROW_PRIOR_FRESHEST_LEFT_UNTOUCHED",
                "source_batch_id": "",
                "source_event_ts": "",
                "source_image": "",
                "source_doc": "",
                "source_mode": "NOT_CAPTURED_OR_NOT_COVERED",
                "source_semantic": "PRIOR_FRESHEST_UNTOUCHED",
                "source_quantity": "",
                "candidate_action": "",
                "candidate_qty_change": "",
                "temporary_override_until": TEMPORARY_UNTIL,
                "supersession_policy": SUPERSESSION_POLICY,
                "notes": "absent OCR/manual cells are not zero",
            }
        )

    for parked in PARKED_JUNE11_ROWS:
        rows.append(
            {
                "generated_at_almaty": generated_at,
                "snapshot_date": snapshot_date.isoformat(),
                "sku_key": str(parked["family_guess"]),
                "sku_id": "",
                "my_size": "",
                "stock_pool_id": "",
                "primary_write_sku_id": "",
                "shared_pool": "",
                "alias_group": "",
                "temporary_current_stock": "",
                "activation_recommendation": "PARKED_MAPPING_PENDING_DO_NOT_ACTIVATE_FROM_THIS_REPORT",
                "authority": "PARKED_MAPPING_PENDING",
                "source_batch_id": str(parked["batch_id"]),
                "source_event_ts": JUNE11_EVENT_TS,
                "source_image": str(parked["source_image"]),
                "source_doc": str(SNAPSHOT_SOURCE_DOC),
                "source_mode": str(parked["mode"]),
                "source_semantic": "PARKED",
                "source_quantity": "",
                "candidate_action": "PARKED",
                "candidate_qty_change": "",
                "temporary_override_until": TEMPORARY_UNTIL,
                "supersession_policy": SUPERSESSION_POLICY,
                "notes": str(parked["reason"]),
            }
        )

    _apply_owner_conflict_holds(rows)
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _insert_event(conn: sqlite3.Connection, candidate: EventCandidate) -> None:
    note_payload = {
        "temporary_policy": TEMPORARY_UNTIL,
        "supersession_policy": SUPERSESSION_POLICY,
        "source_doc": candidate.source_doc,
        "source_image": candidate.source_image,
        "source_mode": candidate.mode,
        "source_semantic": candidate.semantic,
        "source_quantity": candidate.source_quantity,
        "balance_before_override": candidate.balance_before_override,
        "predicted_balance_after_override": candidate.predicted_balance_after_override,
        "confidence": candidate.confidence,
        "notes": candidate.notes,
    }
    conn.execute(
        """
        INSERT OR IGNORE INTO stock_ledger (
            event_date,
            event_type,
            sku_key,
            sku_id,
            my_size,
            store_code,
            qty_change,
            running_balance,
            reference_id,
            reference_type,
            kaspi_offer_name,
            notes,
            input_source,
            created_by,
            idempotency_key
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate.event_date,
            EVENT_TYPE,
            candidate.sku_key,
            candidate.primary_write_sku_id,
            candidate.my_size,
            STORE_CODE,
            candidate.qty_change,
            candidate.predicted_balance_after_override,
            candidate.row_id,
            candidate.reference_type,
            None,
            json.dumps(note_payload, ensure_ascii=False, sort_keys=True),
            INPUT_SOURCE,
            CREATED_BY,
            candidate.idempotency_key,
        ),
    )


def _write_closeout(
    path: Path,
    *,
    summary: dict[str, Any],
    output_root: Path,
) -> None:
    text = f"""# Temporary OCR Stock Override Closeout

Status: {summary['status']}
Mode: {summary['mode']}
Generated at: {summary['generated_at_almaty']}

This is a temporary owner-approved operational layer. It may be superseded by the
main orchestrator/refactor worktree when that work returns a conflict-free,
up-to-date single source of truth.

## Counts

- Candidate rows: {summary['candidate_rows']}
- Insert candidates: {summary['insert_candidate_rows']}
- Existing idempotent rows: {summary['existing_rows']}
- Zero-delta no-ops: {summary['noop_zero_delta_rows']}
- Blocked rows: {summary['blocked_rows']}
- Parked mapping rows: {summary['parked_rows']}
- Owner conflict holds: {summary.get('owner_hold_rows', 0)}
- Snapshot rows rebuilt: {summary.get('snapshot_rows_rebuilt', 0)}

## Stable Activation Report

- CSV: {CURRENT_DIR / 'temporary_stock_decision_latest.csv'}
- JSON: {CURRENT_DIR / 'temporary_stock_decision_latest.json'}
- Summary: {CURRENT_DIR / 'summary_latest.json'}

Activation agents should treat positive `temporary_current_stock` rows as
eligible and zero/negative/parked rows as not eligible, unless a newer owner or
refactor authority explicitly supersedes this temporary report.

## Evidence

- Candidate events: {output_root / 'candidate_events.csv'}
- Blocked rows: {output_root / 'blocked_rows.csv'}
- Parked rows: {output_root / 'parked_rows.csv'}
- Owner conflict holds: {output_root / 'owner_hold_rows.csv'}
- Activation report: {output_root / 'temporary_stock_decision.csv'}
- Summary JSON: {output_root / 'summary.json'}
- Backup: {summary.get('backup_path') or ''}

## Rollback

If this temporary layer must be removed before the refactor supersedes it, either
restore the backup above or delete rows where `input_source = '{INPUT_SOURCE}'`
and `created_by = '{CREATED_BY}'`, then rebuild `fact_inventory_snapshot_size`
for the affected snapshot date.
"""
    path.write_text(text, encoding="utf-8")


def write_outputs(plan: Plan, output_root: Path, summary: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    _write_csv(output_root / "candidate_events.csv", [_candidate_to_record(row) for row in plan.candidates])
    _write_csv(output_root / "blocked_rows.csv", plan.blocked_rows)
    _write_csv(output_root / "parked_rows.csv", plan.parked_rows)
    _write_csv(output_root / "owner_hold_rows.csv", plan.owner_hold_rows)
    _write_csv(output_root / "existing_rows.csv", plan.existing_rows)
    _write_csv(output_root / "temporary_stock_decision.csv", plan.report_rows)
    _write_json(output_root / "temporary_stock_decision.json", plan.report_rows)
    _write_json(output_root / "summary.json", summary)
    _write_closeout(output_root / "closeout.md", summary=summary, output_root=output_root)

    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    _write_csv(CURRENT_DIR / "temporary_stock_decision_latest.csv", plan.report_rows)
    _write_json(CURRENT_DIR / "temporary_stock_decision_latest.json", plan.report_rows)
    _write_json(CURRENT_DIR / "summary_latest.json", summary)
    (CURRENT_DIR / "README.md").write_text(
        """# Temporary OCR Stock Override - Current Activation Report

This folder is the stable handoff surface for marketplace/archive activation
agents while the main stock-truth refactor is happening in a separate worktree.

Use `temporary_stock_decision_latest.csv` first. Activate only rows with an
`activation_recommendation` beginning with `ACTIVATE_OK_POSITIVE`. Do not activate
rows marked zero, negative, parked, mapping-pending, or owner-conflict hold from
this report.

This layer is temporary and may be superseded by the main refactor output once it
returns to the main worktree with conflict-free single-source stock truth.
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--snapshot-date", type=lambda value: date.fromisoformat(value), default=date.today())
    parser.add_argument("--apply", action="store_true", help="Write stock_ledger events and rebuild snapshot")
    parser.add_argument("--expected-pre-sha256", default="", help="Required for apply")
    parser.add_argument("--backup-dir", type=Path, default=None, help="Required for production apply")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Write safe rows even if unrelated rows are blocked; blocked rows remain parked in evidence",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db.expanduser()
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    output_root = args.output_root.expanduser()
    if not output_root.is_absolute():
        output_root = PROJECT_ROOT / output_root
    output_root.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    pre_sha = _file_sha256(db_path)
    backup_path = ""
    snapshot_rows_rebuilt = 0

    with _connect(db_path, readonly=not args.apply) as conn:
        plan = build_plan(conn, snapshot_date=args.snapshot_date)

    status = "DRY_RUN"
    if args.apply:
        if os.environ.get(ENV_GATE) != "1":
            raise SystemExit(f"apply requires {ENV_GATE}=1")
        if not args.expected_pre_sha256:
            raise SystemExit("apply requires --expected-pre-sha256")
        if args.expected_pre_sha256 != pre_sha:
            raise SystemExit(
                f"pre-sha mismatch: expected {args.expected_pre_sha256}, observed {pre_sha}"
            )
        if plan.blocked_rows and not args.allow_blocked:
            raise SystemExit(
                f"blocked rows present ({len(plan.blocked_rows)}); rerun with --allow-blocked to apply safe rows"
            )
        if _is_production_db(db_path):
            if os.environ.get(PRODUCTION_ENV_GATE) != "1":
                raise SystemExit(f"production apply requires {PRODUCTION_ENV_GATE}=1")
            _fail_on_sqlite_sidecars(db_path)
            if args.backup_dir is None:
                raise SystemExit("production apply requires --backup-dir")
        backup_dir = args.backup_dir or (output_root / "backups")
        backup_path = str(backup_database(db_path, backup_dir, compress=False))
        with _connect(db_path, readonly=False) as conn:
            for candidate in plan.insert_candidates:
                _insert_event(conn, candidate)
            conn.commit()
        snapshot_rows_rebuilt = rebuild_snapshot_from_ledger(
            snapshot_date=args.snapshot_date,
            db_path=db_path,
        )
        status = "APPLIED"

    post_sha = _file_sha256(db_path)
    integrity = _sqlite_integrity_check(db_path)
    summary = {
        "status": status,
        "mode": "apply" if args.apply else "dry_run",
        "generated_at_almaty": datetime.now(ALMATY).isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "snapshot_date": args.snapshot_date.isoformat(),
        "pre_sha256": pre_sha,
        "post_sha256": post_sha,
        "sqlite_integrity_check": integrity,
        "backup_path": backup_path,
        "candidate_rows": len(plan.candidates),
        "insert_candidate_rows": len(plan.insert_candidates),
        "existing_rows": len(plan.existing_rows),
        "noop_zero_delta_rows": len([row for row in plan.candidates if row.action == "NOOP_ZERO_DELTA"]),
        "blocked_rows": len(plan.blocked_rows),
        "parked_rows": len(plan.parked_rows),
        "owner_hold_rows": len(plan.owner_hold_rows),
        "activation_report_rows": len(plan.report_rows),
        "snapshot_rows_rebuilt": snapshot_rows_rebuilt,
        "temporary_override_until": TEMPORARY_UNTIL,
        "supersession_policy": SUPERSESSION_POLICY,
        "owner_approval": "approved_in_chat_2026-06-16_for_temporary_operational_override",
        "stable_activation_report_csv": str(CURRENT_DIR / "temporary_stock_decision_latest.csv"),
        "stable_activation_report_json": str(CURRENT_DIR / "temporary_stock_decision_latest.json"),
    }
    write_outputs(plan, output_root, summary)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"status={summary['status']}")
        print(f"candidate_rows={summary['candidate_rows']}")
        print(f"insert_candidate_rows={summary['insert_candidate_rows']}")
        print(f"blocked_rows={summary['blocked_rows']}")
        print(f"parked_rows={summary['parked_rows']}")
        print(f"owner_hold_rows={summary['owner_hold_rows']}")
        print(f"stable_activation_report={summary['stable_activation_report_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
