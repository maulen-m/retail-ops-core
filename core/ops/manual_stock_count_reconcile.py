"""Plan and apply owner-approved physical-count ledger reconciliations.

The default path is read-only.  Version 1 deliberately supports only exact
single-SKU stock pools; shared pools require an owner-approved allocation and
are surfaced as blockers instead of being guessed.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from core.db import DEFAULT_DB_PATH
from core.ops.manual_stock_count_manifest import (
    ManualStockAggregate,
    aggregate_manual_stock_counts,
    load_approved_manual_stock_manifest,
)
from scripts.backup_db import backup_database


ALMATY = ZoneInfo("Asia/Almaty")
UTC = timezone.utc
STORE_CODE = "UNIVERSAL"
ENV_GATE = "ENABLE_MANUAL_STOCK_COUNT_RECONCILE_WRITE"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_MANUAL_STOCK_COUNT_RECONCILE_WRITE"
INPUT_SOURCE = "OWNER_APPROVED_MANUAL_STOCK_COUNT_RECONCILE"
CREATED_BY = "manual_stock_count_reconcile_v1"
METHOD = "PHYSICAL_COUNT_CUT_RECONCILIATION"
METHOD_VERSION = "manual_stock_count_reconcile_v1"
ANCHOR_TYPE = "OWNER_APPROVED_PHYSICAL_COUNT_RECONCILIATION"
DEFAULT_OUTPUT_ROOT = Path("exports/validation/manual_stock_count_reconcile")
OWNER_APPROVAL_PREFIX = "I APPROVE MANUAL STOCK COUNT RECONCILE APPLY"
OWNER_ALLOWED_TABLES = "stock_ledger,stock_anchor,stock_adjustment_batch"
OWNER_ALLOWED_WRITE_SET = (
    "stock_ledger:append_adjustment_and_recompute_running_balance_affected_sku_store;"
    "stock_anchor:insert_exact;stock_adjustment_batch:insert_exact"
)
OWNER_SNAPSHOT_REBUILD = "FORBIDDEN"
TIMING_SEMANTICS = (
    "event_date before local count date is pre-count; same-date SQLite "
    "event_time is UTC and <= count instant is pre-count"
)


@dataclass(frozen=True)
class CountPlanRow:
    batch_id: str
    stock_pool_id: str
    sku_key: str
    sku_id: str
    my_size: str
    count_timestamp_at_almaty: str
    count_timestamp_utc: str
    count_date_almaty: str
    observed_count: int
    pre_count_balance: int | None
    post_count_movement: int | None
    current_ledger_balance: int | None
    adjustment_delta: int | None
    projected_current_balance: int | None
    arithmetic_proven: bool
    action: str
    idempotency_key: str
    blocker: str

    def as_record(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "stock_pool_id": self.stock_pool_id,
            "sku_key": self.sku_key,
            "sku_id": self.sku_id,
            "my_size": self.my_size,
            "count_timestamp_at_almaty": self.count_timestamp_at_almaty,
            "count_timestamp_utc": self.count_timestamp_utc,
            "count_date_almaty": self.count_date_almaty,
            "observed_count": self.observed_count,
            "pre_count_balance": self.pre_count_balance,
            "post_count_movement": self.post_count_movement,
            "current_ledger_balance": self.current_ledger_balance,
            "adjustment_delta": self.adjustment_delta,
            "projected_current_balance": self.projected_current_balance,
            "arithmetic_proven": self.arithmetic_proven,
            "action": self.action,
            "idempotency_key": self.idempotency_key,
            "blocker": self.blocker,
        }


@dataclass
class ReconcilePlan:
    manifest_path: Path
    manifest_sha256: str
    db_path: Path
    db_sha256: str
    rows: list[CountPlanRow]
    manifest: dict[str, Any]
    metadata_blockers: list[str]

    @property
    def batch_id(self) -> str:
        return str(self.manifest["batch_id"])

    @property
    def anchor_id(self) -> str:
        return f"{self.batch_id}_COUNT_RECONCILE_V1"

    @property
    def adjustment_batch_id(self) -> str:
        return f"{self.batch_id}_COUNT_RECONCILE_V1"

    @property
    def blockers(self) -> list[str]:
        return self.metadata_blockers + [row.blocker for row in self.rows if row.blocker]

    @property
    def is_clean(self) -> bool:
        return bool(self.rows) and not self.blockers


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _connect(path: Path, *, readonly: bool) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _integrity(path: Path) -> str:
    with _connect(path, readonly=True) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "")


def _is_production_db(path: Path) -> bool:
    return path.resolve() == DEFAULT_DB_PATH.resolve()


def _sidecars(path: Path) -> list[Path]:
    return [Path(f"{path}-wal"), Path(f"{path}-shm"), Path(f"{path}-journal")]


def _parse_count_timestamp(text: str) -> tuple[datetime, datetime]:
    if not text:
        raise ValueError("missing count_timestamp_at_almaty")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("unparseable count_timestamp_at_almaty") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("count_timestamp_at_almaty must be timezone-aware")
    local = parsed.astimezone(ALMATY)
    if parsed.utcoffset() != local.utcoffset():
        raise ValueError("count_timestamp_at_almaty offset does not match Asia/Almaty")
    return local, local.astimezone(UTC)


def _parse_sqlite_utc_event_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("NULL_EVENT_TIME")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("UNPARSEABLE_EVENT_TIME") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _idempotency_key(
    *, batch_id: str, stock_pool_id: str, count_timestamp: str, manifest_sha256: str
) -> str:
    payload = json.dumps(
        {
            "batch_id": batch_id,
            "count_timestamp_at_almaty": count_timestamp,
            "manifest_sha256": manifest_sha256,
            "stock_pool_id": stock_pool_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"MANUAL_COUNT_RECONCILE_V1:{hashlib.sha256(payload.encode()).hexdigest()}"


def _identity_errors(
    conn: sqlite3.Connection, aggregate: ManualStockAggregate
) -> list[str]:
    errors: list[str] = []
    row = conn.execute(
        """
        SELECT ds.sku_key, ds.my_size, ds.active_flag AS size_active,
               d.sku_key AS parent_sku_key, d.active_flag AS sku_active
        FROM dim_sku_size ds
        LEFT JOIN dim_sku d ON d.sku_key = ds.sku_key
        WHERE ds.sku_id = ?
        """,
        (aggregate.sku_id,),
    ).fetchone()
    if row is None:
        return ["SKU_ID_MISSING"]
    if row["parent_sku_key"] is None:
        errors.append("SKU_PARENT_MISSING")
    if int(row["size_active"] or 0) != 1:
        errors.append("SKU_SIZE_INACTIVE")
    if int(row["sku_active"] or 0) != 1:
        errors.append("SKU_INACTIVE")
    db_sku_key = str(row["sku_key"] or "").strip()
    db_my_size = str(row["my_size"] or "").strip()
    manifest_sku_key = str(aggregate.sku_key or "").strip()
    manifest_size = str(aggregate.canonical_size or "").strip()
    if not db_sku_key:
        errors.append("DB_SKU_KEY_BLANK")
    if not db_my_size:
        errors.append("DB_MY_SIZE_BLANK")
    if db_sku_key != manifest_sku_key:
        errors.append("SKU_KEY_MISMATCH")
    if db_my_size != manifest_size:
        errors.append("SIZE_MISMATCH")
    return errors


def _raw_manifest_errors(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(manifest.get("batch_id") or "").strip():
        errors.append("BLANK_BATCH_ID")
    rows = manifest.get("rows") or []
    if not rows:
        errors.append("EMPTY_MANIFEST")
    if str((manifest.get("location") or {}).get("timezone") or "") != "Asia/Almaty":
        errors.append("LOCATION_TIMEZONE_NOT_ASIA_ALMATY")
    for row in rows:
        row_id = str(row.get("row_id") or "ROW")
        required_targets = {
            "ROW_ID": row.get("row_id"),
            "STOCK_POOL_ID": row.get("stock_pool_id"),
            "SKU_KEY": row.get("sku_key"),
            "SKU_ID": row.get("sku_id"),
            "CANONICAL_SIZE": row.get("canonical_size"),
        }
        for label, value in required_targets.items():
            if not str(value or "").strip():
                errors.append(f"{row_id}:BLANK_{label}")
        timestamp = str(row.get("count_timestamp_at_almaty") or "")
        try:
            _parse_count_timestamp(timestamp)
        except ValueError as exc:
            errors.append(f"{row_id}:{exc}")
        try:
            if int(row.get("quantity")) < 0:
                errors.append(f"{row_id}:NEGATIVE_COUNT")
        except (TypeError, ValueError):
            errors.append(f"{row_id}:INVALID_COUNT")
        if str(row.get("counting_policy") or "") != "single_sku_pool":
            errors.append(f"{row_id}:UNSUPPORTED_COUNTING_POLICY")
        sku_id = str(row.get("sku_id") or "")
        if str(row.get("stock_pool_id") or "") != sku_id:
            errors.append(f"{row_id}:SHARED_OR_MISMATCHED_STOCK_POOL")
        if row.get("applies_to_sku_ids") != [sku_id]:
            errors.append(f"{row_id}:SHARED_OR_MISMATCHED_ALIASES")
        if any(not str(value or "").strip() for value in row.get("applies_to_sku_ids") or []):
            errors.append(f"{row_id}:BLANK_APPLIES_TO_SKU_ID")
    return errors


def _existing_adjustment(
    conn: sqlite3.Connection, idempotency_key: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM stock_ledger WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()


def _expected_note(row: CountPlanRow, manifest_sha256: str) -> str:
    return json.dumps(
        {
            "adjustment_delta": row.adjustment_delta,
            "count_timestamp_at_almaty": row.count_timestamp_at_almaty,
            "count_timestamp_utc": row.count_timestamp_utc,
            "manifest_sha256": manifest_sha256,
            "observed_count": row.observed_count,
            "original_current_ledger_balance_before_adjustment": row.current_ledger_balance,
            "original_post_count_movement": row.post_count_movement,
            "original_pre_count_balance": row.pre_count_balance,
            "original_projected_current_balance": row.projected_current_balance,
            "timing_semantics": TIMING_SEMANTICS,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


_IMMUTABLE_NOTE_KEYS = {
    "adjustment_delta",
    "count_timestamp_at_almaty",
    "count_timestamp_utc",
    "manifest_sha256",
    "observed_count",
    "original_current_ledger_balance_before_adjustment",
    "original_post_count_movement",
    "original_pre_count_balance",
    "original_projected_current_balance",
    "timing_semantics",
}


def _parse_immutable_note(value: Any) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        note = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, ["EXISTING_NOTES_INVALID_JSON"]
    if not isinstance(note, dict):
        return None, ["EXISTING_NOTES_NOT_OBJECT"]
    if set(note) != _IMMUTABLE_NOTE_KEYS:
        return None, ["EXISTING_NOTES_SCHEMA_MISMATCH"]
    integer_keys = {
        "adjustment_delta",
        "observed_count",
        "original_current_ledger_balance_before_adjustment",
        "original_post_count_movement",
        "original_pre_count_balance",
        "original_projected_current_balance",
    }
    if any(type(note[key]) is not int for key in integer_keys):
        return None, ["EXISTING_NOTES_INTEGER_TYPE_MISMATCH"]
    if any(
        not isinstance(note[key], str) or not note[key].strip()
        for key in _IMMUTABLE_NOTE_KEYS - integer_keys
    ):
        return None, ["EXISTING_NOTES_STRING_TYPE_MISMATCH"]
    return note, []


def _existing_payload_errors(
    ledger: sqlite3.Row,
    row: CountPlanRow,
    manifest_sha256: str,
) -> list[str]:
    expected = {
        "event_date": row.count_date_almaty,
        "event_type": "ADJUSTMENT",
        "sku_key": row.sku_key,
        "sku_id": row.sku_id,
        "my_size": row.my_size,
        "store_code": STORE_CODE,
        "reference_id": row.batch_id,
        "reference_type": METHOD,
        "input_source": INPUT_SOURCE,
        "created_by": CREATED_BY,
        "idempotency_key": row.idempotency_key,
    }
    errors: list[str] = []
    for key, value in expected.items():
        actual = ledger[key]
        if str(actual if actual is not None else "") != str(value if value is not None else ""):
            errors.append(f"EXISTING_{key.upper()}_MISMATCH")
    note, note_errors = _parse_immutable_note(ledger["notes"])
    errors.extend(note_errors)
    if note is None:
        return errors
    stable_note_values = {
        "count_timestamp_at_almaty": row.count_timestamp_at_almaty,
        "count_timestamp_utc": row.count_timestamp_utc,
        "manifest_sha256": manifest_sha256,
        "observed_count": row.observed_count,
        "timing_semantics": TIMING_SEMANTICS,
    }
    for key, value in stable_note_values.items():
        if note[key] != value:
            errors.append(f"EXISTING_NOTE_{key.upper()}_MISMATCH")
    delta = note["adjustment_delta"]
    original_pre = note["original_pre_count_balance"]
    original_post = note["original_post_count_movement"]
    original_current = note["original_current_ledger_balance_before_adjustment"]
    original_projected = note["original_projected_current_balance"]
    if int(ledger["qty_change"]) != delta:
        errors.append("EXISTING_QTY_CHANGE_MISMATCH")
    if delta != note["observed_count"] - original_pre:
        errors.append("EXISTING_NOTE_DELTA_ARITHMETIC_FAILED")
    if original_current + delta != original_projected:
        errors.append("EXISTING_NOTE_CURRENT_ARITHMETIC_FAILED")
    if original_projected != note["observed_count"] + original_post:
        errors.append("EXISTING_NOTE_PROJECTED_ARITHMETIC_FAILED")
    if row.pre_count_balance != original_pre:
        errors.append("LATE_PRE_COUNT_MOVEMENT_AFTER_RECONCILIATION")
    if row.current_ledger_balance is None or row.post_count_movement is None:
        errors.append("CURRENT_MOVEMENT_CLASSIFICATION_MISSING")
    elif row.current_ledger_balance + delta != row.observed_count + row.post_count_movement:
        errors.append("EXISTING_ADJUSTMENT_CURRENT_ARITHMETIC_FAILED")
    return errors


def _classify_movements(
    conn: sqlite3.Connection,
    *,
    aggregate: ManualStockAggregate,
    count_local: datetime,
    count_utc: datetime,
    excluded_idempotency_key: str,
) -> tuple[int, int, int, list[str]]:
    pre_count = 0
    post_count = 0
    current = 0
    errors: list[str] = []
    rows = conn.execute(
        """
        SELECT ledger_id, event_date, event_time, qty_change
        FROM stock_ledger
        WHERE sku_id = ?
          AND UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
          AND COALESCE(idempotency_key, '') != ?
        ORDER BY ledger_id
        """,
        (aggregate.sku_id, STORE_CODE, excluded_idempotency_key),
    ).fetchall()
    count_date = count_local.date().isoformat()
    for ledger in rows:
        qty = int(ledger["qty_change"] or 0)
        current += qty
        event_date = str(ledger["event_date"] or "")
        try:
            parsed_event_date = date.fromisoformat(event_date)
        except ValueError:
            errors.append(f"LEDGER_{int(ledger['ledger_id'])}:UNPARSEABLE_EVENT_DATE")
            continue
        if parsed_event_date.isoformat() != event_date:
            errors.append(f"LEDGER_{int(ledger['ledger_id'])}:NONCANONICAL_EVENT_DATE")
            continue
        if event_date < count_date:
            pre_count += qty
        elif event_date > count_date:
            post_count += qty
        else:
            try:
                event_utc = _parse_sqlite_utc_event_time(ledger["event_time"])
            except ValueError as exc:
                errors.append(f"LEDGER_{int(ledger['ledger_id'])}:{exc}")
                continue
            if event_utc <= count_utc:
                pre_count += qty
            else:
                post_count += qty
    return pre_count, post_count, current, errors


def _expected_anchor(plan: ReconcilePlan) -> dict[str, Any]:
    approval = plan.manifest.get("approval") or {}
    dates = sorted({row.count_date_almaty for row in plan.rows})
    return {
        "anchor_id": plan.anchor_id,
        "anchor_type": ANCHOR_TYPE,
        "source_path": str(plan.manifest_path),
        "source_sha256": plan.manifest_sha256,
        "snapshot_date": max(dates),
        "as_of_date": max(dates),
        "row_count": len(plan.rows),
        "total_units": sum(row.observed_count for row in plan.rows),
        "approved_by": str(approval.get("approved_by") or ""),
        "approved_at": str(approval.get("approved_at") or ""),
        "status": "APPROVED",
        "notes": json.dumps(
            {
                "manifest_sha256": plan.manifest_sha256,
                "method_version": METHOD_VERSION,
                "single_sku_pool_only": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def _expected_batch(plan: ReconcilePlan, output_root: Path) -> dict[str, Any]:
    approval = plan.manifest.get("approval") or {}
    total_delta = sum(int(row.adjustment_delta or 0) for row in plan.rows)
    return {
        "batch_id": plan.adjustment_batch_id,
        "anchor_id": plan.anchor_id,
        "method": METHOD,
        "method_version": METHOD_VERSION,
        "reduction_rate": None,
        "target_units_delta": total_delta,
        "generated_units_delta": total_delta,
        "dry_run_report_path": str(output_root / "plan.csv"),
        "approved_by": str(approval.get("approved_by") or ""),
        "approved_at": str(approval.get("approved_at") or ""),
        "rollback_batch_id": "",
        "status": "APPLIED",
        "notes": json.dumps(
            {
                "manifest_sha256": plan.manifest_sha256,
                "no_snapshot_rebuild": True,
                "single_sku_pool_only": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def _metadata_mismatches(
    conn: sqlite3.Connection,
    *,
    table: str,
    key_column: str,
    key_value: str,
    expected: dict[str, Any],
    compare_keys: Iterable[str],
) -> list[str]:
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {key_column} = ?", (key_value,)
    ).fetchone()
    if row is None:
        return []
    errors = []
    for key in compare_keys:
        actual = row[key]
        wanted = expected[key]
        if actual is None and wanted in (None, ""):
            continue
        if str(actual) != str(wanted):
            errors.append(f"{table}:{key.upper()}_MISMATCH")
    return errors


def _legacy_governance_blockers(
    conn: sqlite3.Connection, plan: ReconcilePlan
) -> list[str]:
    blockers: list[str] = []
    anchors = conn.execute(
        """
        SELECT anchor_id
        FROM stock_anchor
        WHERE anchor_id != ?
          AND (source_sha256 = ? OR source_path = ? OR anchor_id = ?)
        ORDER BY anchor_id
        """,
        (
            plan.anchor_id,
            plan.manifest_sha256,
            str(plan.manifest_path),
            plan.batch_id,
        ),
    ).fetchall()
    blockers.extend(
        f"LEGACY_STOCK_ANCHOR_ALREADY_GOVERNS_MANIFEST:{row['anchor_id']}"
        for row in anchors
    )
    batches = conn.execute(
        """
        SELECT batch_id
        FROM stock_adjustment_batch
        WHERE batch_id != ?
          AND (anchor_id = ? OR batch_id = ?)
        ORDER BY batch_id
        """,
        (plan.adjustment_batch_id, plan.batch_id, plan.batch_id),
    ).fetchall()
    blockers.extend(
        f"LEGACY_ADJUSTMENT_BATCH_ALREADY_GOVERNS_MANIFEST:{row['batch_id']}"
        for row in batches
    )
    return blockers


def build_reconcile_plan(
    *,
    db_path: Path,
    manifest_path: Path,
    output_root: Path,
) -> ReconcilePlan:
    db_path = db_path.resolve()
    manifest_path = manifest_path.resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    if not manifest_path.name.endswith(".approved.json"):
        raise ValueError("manifest path must end in .approved.json")
    with manifest_path.open(encoding="utf-8") as handle:
        raw_manifest = json.load(handle)
    local_raw_errors = _raw_manifest_errors(raw_manifest)
    blank_target_errors = [
        error for error in local_raw_errors if "BLANK_" in error
    ]
    if blank_target_errors:
        raise ValueError(
            "manifest canonical target identity is incomplete: "
            + ";".join(blank_target_errors)
        )
    manifest = load_approved_manual_stock_manifest(manifest_path)
    source_sha = file_sha256(manifest_path)
    raw_errors = _raw_manifest_errors(manifest)
    aggregates = aggregate_manual_stock_counts(manifest)
    aggregate_target_counts = Counter(
        (aggregate.sku_id, aggregate.stock_pool_id) for aggregate in aggregates
    )
    plan_rows: list[CountPlanRow] = []
    with _connect(db_path, readonly=True) as conn:
        for aggregate in aggregates:
            blockers: list[str] = []
            aggregate_row_ids = {
                str(row.get("row_id") or "ROW")
                for row in manifest.get("rows") or []
                if str(row.get("count_timestamp_at_almaty") or "")
                == aggregate.count_timestamp_at_almaty
                and str(row.get("stock_pool_id") or "") == aggregate.stock_pool_id
                and str(row.get("sku_id") or "") == aggregate.sku_id
                and str(row.get("canonical_size") or "") == aggregate.canonical_size
            }
            blockers.extend(
                error
                for error in raw_errors
                if any(error.startswith(f"{row_id}:") for row_id in aggregate_row_ids)
            )
            if aggregate.counting_policy != "single_sku_pool":
                blockers.append("UNSUPPORTED_COUNTING_POLICY")
            if aggregate_target_counts[(aggregate.sku_id, aggregate.stock_pool_id)] > 1:
                blockers.append("DUPLICATE_AGGREGATE_TARGET_IDENTITY")
            if aggregate.stock_pool_id != aggregate.sku_id or aggregate.applies_to_sku_ids != (aggregate.sku_id,):
                blockers.append("SHARED_POOL_REQUIRES_EXPLICIT_ALLOCATION")
            blockers.extend(_identity_errors(conn, aggregate))
            try:
                count_local, count_utc = _parse_count_timestamp(aggregate.count_timestamp_at_almaty)
            except ValueError as exc:
                blockers.append(str(exc))
                count_local = datetime(1970, 1, 1, tzinfo=ALMATY)
                count_utc = count_local.astimezone(UTC)
            key = _idempotency_key(
                batch_id=aggregate.batch_id,
                stock_pool_id=aggregate.stock_pool_id,
                count_timestamp=aggregate.count_timestamp_at_almaty,
                manifest_sha256=source_sha,
            )
            pre, post, current, timing_errors = _classify_movements(
                conn,
                aggregate=aggregate,
                count_local=count_local,
                count_utc=count_utc,
                excluded_idempotency_key=key,
            )
            blockers.extend(timing_errors)
            delta = int(aggregate.quantity) - pre
            projected = int(aggregate.quantity) + post
            arithmetic = current + delta == projected
            if not arithmetic:
                blockers.append("ARITHMETIC_IDENTITY_FAILED")
            provisional = CountPlanRow(
                batch_id=aggregate.batch_id,
                stock_pool_id=aggregate.stock_pool_id,
                sku_key=aggregate.sku_key,
                sku_id=aggregate.sku_id,
                my_size=aggregate.canonical_size,
                count_timestamp_at_almaty=aggregate.count_timestamp_at_almaty,
                count_timestamp_utc=count_utc.isoformat(),
                count_date_almaty=count_local.date().isoformat(),
                observed_count=int(aggregate.quantity),
                pre_count_balance=pre,
                post_count_movement=post,
                current_ledger_balance=current,
                adjustment_delta=delta,
                projected_current_balance=projected,
                arithmetic_proven=arithmetic,
                action="BLOCKED" if blockers else ("NOOP_ZERO_DELTA" if delta == 0 else "INSERT"),
                idempotency_key=key,
                blocker=";".join(dict.fromkeys(blockers)),
            )
            existing = _existing_adjustment(conn, key)
            if existing is not None:
                payload_errors = _existing_payload_errors(existing, provisional, source_sha)
                blockers.extend(payload_errors)
                provisional = CountPlanRow(
                    **{
                        **provisional.__dict__,
                        "action": "BLOCKED" if blockers else "EXISTS",
                        "blocker": ";".join(dict.fromkeys(blockers)),
                    }
                )
            plan_rows.append(provisional)

        plan = ReconcilePlan(
            manifest_path=manifest_path,
            manifest_sha256=source_sha,
            db_path=db_path,
            db_sha256=file_sha256(db_path),
            rows=plan_rows,
            manifest=manifest,
            metadata_blockers=[error for error in raw_errors if ":" not in error],
        )
        if plan.rows:
            plan.metadata_blockers.extend(_legacy_governance_blockers(conn, plan))
            anchor = _expected_anchor(plan)
            batch = _expected_batch(plan, output_root)
            plan.metadata_blockers.extend(
                _metadata_mismatches(
                    conn,
                    table="stock_anchor",
                    key_column="anchor_id",
                    key_value=plan.anchor_id,
                    expected=anchor,
                    compare_keys=tuple(anchor.keys()),
                )
            )
            plan.metadata_blockers.extend(
                _metadata_mismatches(
                    conn,
                    table="stock_adjustment_batch",
                    key_column="batch_id",
                    key_value=plan.adjustment_batch_id,
                    expected=batch,
                    compare_keys=tuple(batch.keys()),
                )
            )
            if plan.metadata_blockers:
                plan.rows = [
                    CountPlanRow(
                        **{
                            **row.__dict__,
                            "action": "BLOCKED",
                            "blocker": ";".join(
                                dict.fromkeys(
                                    filter(None, [row.blocker, "GLOBAL_METADATA_BLOCKER"])
                                )
                            ),
                        }
                    )
                    for row in plan.rows
                ]
    return plan


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(CountPlanRow.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _summary(plan: ReconcilePlan, *, mode: str, **extra: Any) -> dict[str, Any]:
    blockers = plan.blockers
    return {
        "status": "APPLIED" if mode == "apply" else "DRY_RUN",
        "mode": mode,
        "gate": "GREEN" if not blockers else "RED",
        "manifest_path": str(plan.manifest_path),
        "manifest_sha256": plan.manifest_sha256,
        "db_path": str(plan.db_path),
        "pre_sha256": plan.db_sha256,
        "row_count": len(plan.rows),
        "insert_rows": sum(row.action == "INSERT" for row in plan.rows),
        "existing_rows": sum(row.action == "EXISTS" for row in plan.rows),
        "noop_rows": sum(row.action == "NOOP_ZERO_DELTA" for row in plan.rows),
        "blocked_rows": sum(bool(row.blocker) for row in plan.rows),
        "metadata_blockers": list(plan.metadata_blockers),
        "is_safe_to_apply": plan.is_clean,
        "external_writes": 0,
        "snapshot_rebuilt": False,
        "next_safe_step": (
            "After a governed count apply and after all movements through the prior business day "
            "are complete, dry-run then rebuild the morning snapshot for the next business date."
        ),
        **extra,
    }


def write_evidence(output_root: Path, plan: ReconcilePlan, summary: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    _write_csv(output_root / "plan.csv", [row.as_record() for row in plan.rows])
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = f"""# Manual Physical Count Reconciliation

- Mode: {summary['mode']}
- Rows: {summary['row_count']}
- Insert: {summary['insert_rows']}
- Existing: {summary['existing_rows']}
- No-op: {summary['noop_rows']}
- Blocked: {summary['blocked_rows']}
- Source SHA-256: {summary['manifest_sha256']}
- DB SHA before: {summary['pre_sha256']}
- DB SHA after: {summary.get('post_sha256', summary['pre_sha256'])}
- Backup SHA-256: {summary.get('backup_sha256') or 'none'}
- External writes: 0
- Snapshot rebuilt: false

## Minimum safe next step

{summary['next_safe_step']}

Gate: {summary['gate']}
"""
    (output_root / "REPORT.md").write_text(report, encoding="utf-8")


def _insert_anchor(conn: sqlite3.Connection, expected: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO stock_anchor (
          anchor_id, anchor_type, source_path, source_sha256, snapshot_date,
          as_of_date, row_count, total_units, approved_by, approved_at, status, notes
        ) VALUES (
          :anchor_id, :anchor_type, :source_path, :source_sha256, :snapshot_date,
          :as_of_date, :row_count, :total_units, :approved_by, :approved_at, :status, :notes
        )
        """,
        expected,
    )


def _insert_batch(
    conn: sqlite3.Connection, expected: dict[str, Any], *, applied_at: str
) -> None:
    conn.execute(
        """
        INSERT INTO stock_adjustment_batch (
          batch_id, anchor_id, method, method_version, reduction_rate,
          target_units_delta, generated_units_delta, dry_run_report_path,
          approved_by, approved_at, applied_at, rollback_batch_id, status, notes
        ) VALUES (
          :batch_id, :anchor_id, :method, :method_version, :reduction_rate,
          :target_units_delta, :generated_units_delta, :dry_run_report_path,
          :approved_by, :approved_at, :applied_at, :rollback_batch_id, :status, :notes
        )
        """,
        {**expected, "applied_at": applied_at},
    )


def _insert_adjustment(
    conn: sqlite3.Connection, row: CountPlanRow, manifest_sha256: str, applied_at_utc: str
) -> None:
    conn.execute(
        """
        INSERT INTO stock_ledger (
          event_date, event_time, event_type, sku_key, sku_id, my_size, store_code,
          qty_change, running_balance, reference_id, reference_type, kaspi_offer_name,
          notes, input_source, created_by, idempotency_key
        ) VALUES (?, ?, 'ADJUSTMENT', ?, ?, ?, ?, ?, NULL, ?, ?, NULL, ?, ?, ?, ?)
        """,
        (
            row.count_date_almaty,
            applied_at_utc,
            row.sku_key,
            row.sku_id,
            row.my_size,
            STORE_CODE,
            row.adjustment_delta,
            row.batch_id,
            METHOD,
            _expected_note(row, manifest_sha256),
            INPUT_SOURCE,
            CREATED_BY,
            row.idempotency_key,
        ),
    )


def _recompute_running_balances(
    conn: sqlite3.Connection, affected: set[tuple[str, str]]
) -> int:
    updates = 0
    for sku_id, store_code in sorted(affected):
        running = 0
        rows = conn.execute(
            """
            SELECT ledger_id, qty_change, running_balance
            FROM stock_ledger
            WHERE sku_id = ? AND UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
            ORDER BY ledger_id
            """,
            (sku_id, store_code),
        ).fetchall()
        for row in rows:
            running += int(row["qty_change"] or 0)
            if row["running_balance"] is None or int(row["running_balance"]) != running:
                conn.execute(
                    "UPDATE stock_ledger SET running_balance = ? WHERE ledger_id = ?",
                    (running, int(row["ledger_id"])),
                )
                updates += 1
    return updates


def _running_balance_mismatches(
    conn: sqlite3.Connection, affected: set[tuple[str, str]]
) -> int:
    mismatches = 0
    for sku_id, store_code in sorted(affected):
        running = 0
        for row in conn.execute(
            """
            SELECT qty_change, running_balance FROM stock_ledger
            WHERE sku_id = ? AND UPPER(COALESCE(store_code, 'UNIVERSAL')) = ?
            ORDER BY ledger_id
            """,
            (sku_id, store_code),
        ):
            running += int(row["qty_change"] or 0)
            if row["running_balance"] is None or int(row["running_balance"]) != running:
                mismatches += 1
    return mismatches


def required_owner_approval_phrase(
    *,
    apply_date_almaty: str,
    batch_id: str,
    manifest_sha256: str,
    expected_pre_db_sha256: str,
) -> str:
    return (
        f"{OWNER_APPROVAL_PREFIX} | apply_date_almaty={apply_date_almaty}"
        f" | batch_id={batch_id} | manifest_sha256={manifest_sha256}"
        f" | expected_pre_db_sha256={expected_pre_db_sha256}"
        f" | allowed_tables={OWNER_ALLOWED_TABLES}"
        f" | allowed_write_set={OWNER_ALLOWED_WRITE_SET}"
        f" | snapshot_rebuild={OWNER_SNAPSHOT_REBUILD}"
    )


def _validate_owner_instrument(
    path: Path,
    expected_sha256: str,
    *,
    plan: ReconcilePlan,
    expected_pre_db_sha256: str,
) -> str:
    if not path.exists() or not path.is_file():
        raise RuntimeError("production apply requires an existing owner instrument")
    apply_date_almaty = datetime.now(ALMATY).date().isoformat()
    accepted_filename_dates = {
        apply_date_almaty,
        apply_date_almaty.replace("-", ""),
        apply_date_almaty.replace("-", "_"),
    }
    if not any(value in path.name for value in accepted_filename_dates):
        raise RuntimeError(
            "owner instrument filename must contain the current Asia/Almaty apply date"
        )
    observed = file_sha256(path)
    if not expected_sha256 or observed != expected_sha256:
        raise RuntimeError("owner instrument SHA-256 mismatch")
    required_phrase = required_owner_approval_phrase(
        apply_date_almaty=apply_date_almaty,
        batch_id=plan.batch_id,
        manifest_sha256=plan.manifest_sha256,
        expected_pre_db_sha256=expected_pre_db_sha256,
    )
    if path.read_text(encoding="utf-8").strip() != required_phrase:
        raise RuntimeError(
            "owner instrument does not exactly match the required current apply approval phrase"
        )
    return observed


def reconcile_manual_stock_count(
    *,
    db_path: Path,
    manifest_path: Path,
    output_root: Path,
    apply: bool = False,
    expected_pre_sha256: str = "",
    backup_dir: Path | None = None,
    owner_instrument: Path | None = None,
    owner_instrument_sha256: str = "",
) -> dict[str, Any]:
    db_path = db_path.resolve()
    manifest_path = manifest_path.resolve()
    output_root = output_root.resolve()
    plan = build_reconcile_plan(
        db_path=db_path, manifest_path=manifest_path, output_root=output_root
    )
    if not apply:
        summary = _summary(
            plan,
            mode="dry_run",
            post_sha256=plan.db_sha256,
            integrity_check=_integrity(db_path),
            backup_path=None,
            backup_sha256=None,
            owner_instrument_path=None,
            owner_instrument_sha256=None,
            running_balance_rows_updated=0,
            running_balance_mismatches=0,
        )
        write_evidence(output_root, plan, summary)
        return summary

    if os.environ.get(ENV_GATE) != "1":
        raise RuntimeError(f"apply requires {ENV_GATE}=1")
    if not expected_pre_sha256:
        raise RuntimeError("apply requires --expected-pre-sha256")
    if expected_pre_sha256 != plan.db_sha256:
        raise RuntimeError(
            f"pre-SHA mismatch: expected {expected_pre_sha256}, observed {plan.db_sha256}"
        )
    if not plan.is_clean:
        raise RuntimeError("count reconciliation plan contains blockers")

    production = _is_production_db(db_path)
    instrument_sha: str | None = None
    if production:
        if os.environ.get(PRODUCTION_ENV_GATE) != "1":
            raise RuntimeError(f"production apply requires {PRODUCTION_ENV_GATE}=1")
        existing_sidecars = [path for path in _sidecars(db_path) if path.exists()]
        if existing_sidecars:
            raise RuntimeError("production apply refused while SQLite sidecars exist")
        if backup_dir is None:
            raise RuntimeError("production apply requires --backup-dir")
        if owner_instrument is None:
            raise RuntimeError("production apply requires --owner-instrument")
        instrument_sha = _validate_owner_instrument(
            owner_instrument.resolve(),
            owner_instrument_sha256,
            plan=plan,
            expected_pre_db_sha256=expected_pre_sha256,
        )

    before_backup_sha = file_sha256(db_path)
    backup_base = (backup_dir or (output_root / "backups")).resolve()
    backup_run_dir = backup_base / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_database(db_path, backup_run_dir, compress=False)
    backup_integrity = _integrity(backup_path)
    if backup_integrity.lower() != "ok":
        raise RuntimeError(f"backup integrity_check failed: {backup_integrity}")
    backup_sha = file_sha256(backup_path)
    if file_sha256(db_path) != before_backup_sha:
        raise RuntimeError("database changed while backup was created")

    applied_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    affected = {(row.sku_id, STORE_CODE) for row in plan.rows}
    updates = 0
    with _connect(db_path, readonly=False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if file_sha256(db_path) != plan.db_sha256:
            conn.rollback()
            raise RuntimeError("database SHA changed before transaction")
        locked_plan = build_reconcile_plan(
            db_path=db_path, manifest_path=manifest_path, output_root=output_root
        )
        if [row.as_record() for row in locked_plan.rows] != [
            row.as_record() for row in plan.rows
        ]:
            conn.rollback()
            raise RuntimeError("reconciliation plan drifted under write lock")
        for row in plan.rows:
            if row.action == "INSERT":
                _insert_adjustment(conn, row, plan.manifest_sha256, applied_at)
        if conn.execute(
            "SELECT 1 FROM stock_anchor WHERE anchor_id = ?", (plan.anchor_id,)
        ).fetchone() is None:
            _insert_anchor(conn, _expected_anchor(plan))
        if conn.execute(
            "SELECT 1 FROM stock_adjustment_batch WHERE batch_id = ?",
            (plan.adjustment_batch_id,),
        ).fetchone() is None:
            _insert_batch(conn, _expected_batch(plan, output_root), applied_at=applied_at)
        updates = _recompute_running_balances(conn, affected)
        mismatches = _running_balance_mismatches(conn, affected)
        if mismatches:
            conn.rollback()
            raise RuntimeError(f"running_balance mismatches remain: {mismatches}")
        conn.commit()

    post_plan = build_reconcile_plan(
        db_path=db_path, manifest_path=manifest_path, output_root=output_root
    )
    if post_plan.blockers or any(
        row.action not in {"EXISTS", "NOOP_ZERO_DELTA"} for row in post_plan.rows
    ):
        raise RuntimeError("post-apply idempotency readback failed")
    with _connect(db_path, readonly=True) as conn:
        mismatches = _running_balance_mismatches(conn, affected)
    summary = _summary(
        post_plan,
        mode="apply",
        pre_sha256=plan.db_sha256,
        post_sha256=file_sha256(db_path),
        integrity_check=_integrity(db_path),
        backup_path=str(backup_path),
        backup_sha256=backup_sha,
        backup_integrity_check=backup_integrity,
        owner_instrument_path=str(owner_instrument.resolve()) if owner_instrument else None,
        owner_instrument_sha256=instrument_sha,
        running_balance_rows_updated=updates,
        running_balance_mismatches=mismatches,
    )
    write_evidence(output_root, post_plan, summary)
    return summary
