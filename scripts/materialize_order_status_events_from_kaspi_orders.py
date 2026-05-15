#!/usr/bin/env python3
"""Materialize order_status_event from local Kaspi order evidence.

Dry-run is the default. Apply requires ENABLE_ORDER_STATUS_EVENT_WRITE=1 and
creates a DB backup before inserting idempotent rows.
"""

from __future__ import annotations

import argparse
from collections import Counter
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
from core.integrations.kaspi_order_stage import (
    StageCode,
    classify_kaspi_stage_from_db_row,
)
from scripts.backup_db import backup_database

ORDER_STATUS_EVENT_ENV_GATE = "ENABLE_ORDER_STATUS_EVENT_WRITE"

DEFAULT_BACKUP_DIR = PROJECT_ROOT / "runtime" / "backups"

INTERNAL_STATUS_STAGE = {
    "NEW": StageCode.NEW_APPROVED,
    "ACCEPTED": StageCode.ACCEPTED_PENDING_ASSEMBLY,
    "READY": StageCode.ASSEMBLED_PENDING_HANDOVER,
    "SHIPPED": StageCode.IN_DELIVERY,
    "DELIVERED": StageCode.ISSUED_COMPLETED,
    "COMPLETED": StageCode.ISSUED_COMPLETED,
    "ISSUED": StageCode.ISSUED_COMPLETED,
    "CANCELLING": StageCode.CANCELLING,
    "CANCELLED": StageCode.CANCELLED,
    "RETURNING": StageCode.RETURN_REQUESTED,
    "RETURN_REQUESTED": StageCode.RETURN_REQUESTED,
    "RETURNED": StageCode.RETURNED,
}


def _c3_stage_code(stage: StageCode) -> str:
    if stage == StageCode.ISSUED_COMPLETED:
        return "COMPLETED"
    if stage == StageCode.RETURN_REQUESTED:
        return "RETURN"
    return stage.value


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _hash_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _stage_from_internal_status(value: Any) -> StageCode:
    return INTERNAL_STATUS_STAGE.get(_norm(value), StageCode.UNKNOWN)


def _stage_from_order_row(row: dict[str, Any]) -> StageCode:
    stage = classify_kaspi_stage_from_db_row(row)
    if stage != StageCode.UNKNOWN:
        return stage
    return _stage_from_internal_status(row.get("internal_status"))


def _has_strict_completed_header_contract(row: dict[str, Any]) -> bool:
    return (
        _norm(row.get("internal_status")) == "COMPLETED"
        and _norm(row.get("kaspi_status")) == "ARCHIVE"
        and _norm(row.get("kaspi_status_detail")) == "COMPLETED"
    )


def _event_ts_from_order_row(row: dict[str, Any]) -> str | None:
    for key in ("status_updated_at", "updated_at", "imported_at", "created_at"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return None


def _event_from_order_row(row: dict[str, Any], *, run_id: str) -> dict[str, Any] | None:
    store_code = str(row.get("store_code") or "UNIVERSAL").strip().upper()
    order_id = str(row.get("order_id") or "").strip()
    if not order_id:
        return None
    stage = _stage_from_order_row(row)
    if stage == StageCode.UNKNOWN:
        return None
    if stage == StageCode.ISSUED_COMPLETED and not _has_strict_completed_header_contract(row):
        return None
    stage_code = _c3_stage_code(stage)
    event_ts = _event_ts_from_order_row(row)
    if not event_ts:
        return None
    raw_state = str(row.get("kaspi_status") or "").strip() or None
    raw_status = str(row.get("kaspi_status_detail") or row.get("internal_status") or "").strip() or None
    source_payload = {
        "source_table": "fact_orders_kaspi",
        "row_id": row.get("id"),
        "store_code": store_code,
        "order_id": order_id,
        "stage_code": stage_code,
        "event_ts": event_ts,
        "raw_state": raw_state,
        "raw_status": raw_status,
        "status_updated_at": row.get("status_updated_at"),
        "updated_at": row.get("updated_at"),
    }
    source_row_hash = _hash_json(source_payload)
    idempotency_key = _hash_json(
        {
            "source": "LOCAL_FACT_ORDERS_KASPI",
            "store_code": store_code,
            "order_id": order_id,
            "stage_code": stage_code,
            "event_ts": event_ts,
        }
    )
    return {
        "store_code": store_code,
        "order_id": order_id,
        "stage_code": stage_code,
        "event_ts": event_ts,
        "source": "LOCAL_FACT_ORDERS_KASPI",
        "raw_state": raw_state,
        "raw_status": raw_status,
        "source_status_change_at": row.get("status_updated_at"),
        "source_run_id": run_id,
        "flags_json": json.dumps(
            {
                "materializer": "materialize_order_status_events_from_kaspi_orders",
                "source_table": "fact_orders_kaspi",
                "completed_header_contract": (
                    "internal_status=COMPLETED;kaspi_status=ARCHIVE;"
                    "kaspi_status_detail=COMPLETED"
                )
                if stage_code == "COMPLETED"
                else None,
            },
            sort_keys=True,
        ),
        "source_row_hash": source_row_hash,
        "idempotency_key": idempotency_key,
    }


def _event_from_observation_row(row: dict[str, Any], *, run_id: str) -> dict[str, Any] | None:
    store_code = str(row.get("store_code") or "UNIVERSAL").strip().upper()
    order_id = str(row.get("order_id") or "").strip()
    if not order_id:
        return None
    stage = _stage_from_internal_status(row.get("status_internal"))
    if stage == StageCode.UNKNOWN:
        return None
    stage_code = _c3_stage_code(stage)
    event_ts = str(row.get("observed_at") or "").strip()
    if not event_ts:
        return None
    raw_status = str(row.get("status_internal") or "").strip() or None
    source_payload = {
        "source_table": "fact_order_status_observations",
        "row_id": row.get("id"),
        "store_code": store_code,
        "order_id": order_id,
        "stage_code": stage_code,
        "event_ts": event_ts,
        "raw_status": raw_status,
        "source": row.get("source"),
        "ledger_run_id": row.get("ledger_run_id"),
    }
    source_row_hash = _hash_json(source_payload)
    idempotency_key = _hash_json(
        {
            "source": "LOCAL_FACT_ORDER_STATUS_OBSERVATIONS",
            "store_code": store_code,
            "order_id": order_id,
            "stage_code": stage_code,
            "event_ts": event_ts,
        }
    )
    return {
        "store_code": store_code,
        "order_id": order_id,
        "stage_code": stage_code,
        "event_ts": event_ts,
        "source": "LOCAL_FACT_ORDER_STATUS_OBSERVATIONS",
        "raw_state": None,
        "raw_status": raw_status,
        "source_status_change_at": event_ts,
        "source_run_id": run_id,
        "flags_json": json.dumps(
            {
                "materializer": "materialize_order_status_events_from_kaspi_orders",
                "source_table": "fact_order_status_observations",
                "source": row.get("source"),
                "ledger_run_id": row.get("ledger_run_id"),
            },
            sort_keys=True,
        ),
        "source_row_hash": source_row_hash,
        "idempotency_key": idempotency_key,
    }


def build_order_status_event_candidates(conn: sqlite3.Connection, *, run_id: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates_by_key: dict[str, dict[str, Any]] = {}
    skipped = Counter()

    if not _table_exists(conn, "order_status_event"):
        raise RuntimeError("order_status_event table is missing")

    if _table_exists(conn, "fact_orders_kaspi"):
        wanted = [
            "id",
            "order_id",
            "store_code",
            "kaspi_status",
            "kaspi_status_detail",
            "internal_status",
            "status_updated_at",
            "updated_at",
            "imported_at",
            "created_at",
            "signature_required",
            "pre_order",
            "waybill_url",
            "delivery_mode",
            "returned_to_warehouse",
            "courier_transmission_date",
            "actual_shipment_date",
        ]
        available = _columns(conn, "fact_orders_kaspi")
        select_cols = [column for column in wanted if column in available]
        for row in conn.execute(f"SELECT {', '.join(select_cols)} FROM fact_orders_kaspi").fetchall():
            event = _event_from_order_row(dict(row), run_id=run_id)
            if event is None:
                skipped["fact_orders_kaspi"] += 1
                continue
            candidates_by_key[event["idempotency_key"]] = event

    if _table_exists(conn, "fact_order_status_observations"):
        for row in conn.execute(
            """
            SELECT id, order_id, store_code, status_internal, observed_at,
                   source, ledger_run_id, source_detail
            FROM fact_order_status_observations
            """
        ).fetchall():
            event = _event_from_observation_row(dict(row), run_id=run_id)
            if event is None:
                skipped["fact_order_status_observations"] += 1
                continue
            candidates_by_key[event["idempotency_key"]] = event

    candidates = sorted(
        candidates_by_key.values(),
        key=lambda row: (
            row["store_code"],
            row["order_id"],
            row["event_ts"],
            row["stage_code"],
            row["source"],
        ),
    )
    return candidates, dict(skipped)


def _parse_date(value: str | None, *, field_name: str) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"{field_name} must start with YYYY-MM-DD: {value!r}") from exc


def _filter_candidates_as_of(
    candidates: list[dict[str, Any]],
    *,
    as_of: str | None,
) -> tuple[list[dict[str, Any]], int]:
    as_of_date = _parse_date(as_of, field_name="as_of")
    if as_of_date is None:
        return candidates, 0

    filtered: list[dict[str, Any]] = []
    skipped = 0
    for candidate in candidates:
        event_date = _parse_date(candidate.get("event_ts"), field_name="event_ts")
        if event_date is not None and event_date <= as_of_date:
            filtered.append(candidate)
        else:
            skipped += 1
    return filtered, skipped


def _insert_events(conn: sqlite3.Connection, candidates: list[dict[str, Any]]) -> int:
    inserted = 0
    for row in candidates:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO order_status_event (
                store_code, order_id, stage_code, event_ts, source,
                raw_state, raw_status, source_status_change_at, source_run_id,
                flags_json, source_row_hash, idempotency_key
            ) VALUES (
                :store_code, :order_id, :stage_code, :event_ts, :source,
                :raw_state, :raw_status, :source_status_change_at, :source_run_id,
                :flags_json, :source_row_hash, :idempotency_key
            )
            """,
            row,
        )
        inserted += max(cursor.rowcount, 0)
    return inserted


def materialize_order_status_events(
    *,
    db_path: Path,
    as_of: str | None,
    run_id: str,
    apply: bool,
    backup_dir: Path,
    replace_run_id: bool = False,
) -> dict[str, Any]:
    backup_path: Path | None = None
    if apply:
        if os.environ.get(ORDER_STATUS_EVENT_ENV_GATE) != "1":
            raise RuntimeError(f"{ORDER_STATUS_EVENT_ENV_GATE}=1 is required for order_status_event apply")
        backup_path = backup_database(db_path, backup_dir, compress=False)

    with _connect(db_path) as conn:
        before_count = conn.execute("SELECT COUNT(*) FROM order_status_event").fetchone()[0]
        raw_candidates, skipped = build_order_status_event_candidates(conn, run_id=run_id)
        candidates, as_of_filtered_count = _filter_candidates_as_of(raw_candidates, as_of=as_of)
        stage_counts = dict(sorted(Counter(row["stage_code"] for row in candidates).items()))
        deleted = 0
        inserted = 0
        if apply:
            if replace_run_id:
                cursor = conn.execute(
                    "DELETE FROM order_status_event WHERE source_run_id = ?",
                    (run_id,),
                )
                deleted = max(cursor.rowcount, 0)
            inserted = _insert_events(conn, candidates)
            conn.commit()
        after_count = conn.execute("SELECT COUNT(*) FROM order_status_event").fetchone()[0]

    return {
        "applied": apply,
        "db_path": str(db_path),
        "as_of": as_of,
        "run_id": run_id,
        "backup_path": str(backup_path) if backup_path else None,
        "candidate_count": len(candidates),
        "candidate_count_before_as_of_filter": len(raw_candidates),
        "candidate_count_after_as_of_filter": len(candidates),
        "as_of_filtered_count": as_of_filtered_count,
        "deleted_count": deleted,
        "inserted_count": inserted,
        "before_count": before_count,
        "after_count": after_count,
        "stage_counts": stage_counts,
        "skipped_counts": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize order_status_event from local order evidence")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--as-of", help="Optional YYYY-MM-DD candidate cutoff; omitted means materialize current evidence")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--replace-run-id", action="store_true", help="Delete this run_id's prior materialized rows before insert")
    parser.add_argument("--strict", action="store_true", help="Reserved for command compatibility; skipped rows stay reported")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = materialize_order_status_events(
        db_path=args.db,
        as_of=args.as_of,
        run_id=args.run_id,
        apply=args.apply,
        backup_dir=args.backup_dir,
        replace_run_id=args.replace_run_id,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for key in sorted(report):
            print(f"{key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
