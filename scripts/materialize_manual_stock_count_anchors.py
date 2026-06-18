#!/usr/bin/env python3
"""Materialize governed metadata for approved manual stock count anchors.

This script does not create stock movement rows. It proves that the approved
manual-count rows are already represented by the temporary OCR stock-ledger
layer, or that a row was a zero-delta no-op, then records durable
stock_anchor/stock_adjustment_batch metadata.

Apply gates:
  ENABLE_MANUAL_STOCK_COUNT_ANCHOR_WRITE=1
  ALLOW_PRODUCTION_MANUAL_STOCK_COUNT_ANCHOR_WRITE=1 for db/app.db
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterable
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH  # noqa: E402
from core.ops.manual_stock_count_manifest import (  # noqa: E402
    APPROVED_MANIFEST_DIR,
    aggregate_manual_stock_counts,
    load_approved_manual_stock_manifest,
)
from scripts.backup_db import backup_database  # noqa: E402


ALMATY = ZoneInfo("Asia/Almaty")
ENV_GATE = "ENABLE_MANUAL_STOCK_COUNT_ANCHOR_WRITE"
PRODUCTION_ENV_GATE = "ALLOW_PRODUCTION_MANUAL_STOCK_COUNT_ANCHOR_WRITE"
INPUT_SOURCE = "OWNER_APPROVED_TEMP_OCR_OVERRIDE"
STORE_CODE = "UNIVERSAL"
ANCHOR_TYPE = "OWNER_APPROVED_MANUAL_STOCK_COUNT"
METHOD = "MANUAL_COUNT_SUPERSESSION_DELTA"
METHOD_VERSION = "manual_stock_count_anchor_metadata_v1"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports/validation/manual_stock_count_anchors"


@dataclass(frozen=True)
class ManualCountSourceRow:
    row_id: str
    batch_id: str
    event_ts: str
    event_date: str
    boundary_inclusive: bool
    sku_key: str
    sku_id: str
    my_size: str
    stock_pool_id: str
    applies_to_sku_ids: tuple[str, ...]
    quantity: int
    source_doc: str
    source_images: tuple[str, ...]

    @property
    def idempotency_key(self) -> str:
        return (
            f"TEMP_OCR_OVERRIDE:{self.batch_id}:{self.row_id}:"
            f"{self.stock_pool_id}:{self.event_ts}:FULL_SUPERSEDE"
        )


@dataclass
class ManifestPlan:
    manifest_path: Path
    manifest: dict[str, Any]
    source_sha256: str
    source_rows: list[ManualCountSourceRow]
    coverage_rows: list[dict[str, Any]]
    blocked_rows: list[dict[str, Any]]
    anchor_action: str
    batch_action: str
    anchor_blocker: str = ""
    batch_blocker: str = ""

    @property
    def batch_id(self) -> str:
        return str(self.manifest["batch_id"])

    @property
    def anchor_id(self) -> str:
        return self.batch_id

    @property
    def adjustment_batch_id(self) -> str:
        return f"{self.batch_id}_GOVERNED_SUPERSESSION_DELTA"

    @property
    def aggregate_row_count(self) -> int:
        return len(self.source_rows)

    @property
    def total_units(self) -> int:
        return sum(row.quantity for row in self.source_rows)

    @property
    def event_dates(self) -> list[str]:
        return sorted({row.event_date for row in self.source_rows})

    @property
    def latest_event_date(self) -> str:
        return max(self.event_dates)

    @property
    def ledger_row_count(self) -> int:
        return sum(1 for row in self.coverage_rows if row["coverage_status"] == "EXISTING_LEDGER")

    @property
    def noop_row_count(self) -> int:
        return sum(1 for row in self.coverage_rows if row["coverage_status"] == "NOOP_ZERO_DELTA")

    @property
    def ledger_delta_sum(self) -> int:
        return sum(int(row["ledger_qty_change"] or 0) for row in self.coverage_rows)

    @property
    def is_safe(self) -> bool:
        return not self.blocked_rows and not self.anchor_blocker and not self.batch_blocker


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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest_paths(paths: Iterable[Path] | None) -> list[Path]:
    if paths:
        return [path.expanduser() for path in paths]
    return sorted(APPROVED_MANIFEST_DIR.glob("*.approved.json"))


def _source_rows_from_manifest(manifest_path: Path, manifest: dict[str, Any]) -> list[ManualCountSourceRow]:
    count_scope = manifest.get("count_scope") or {}
    method = str(count_scope.get("method") or "").lower()
    source_rows: list[ManualCountSourceRow] = []
    for aggregate in aggregate_manual_stock_counts(manifest):
        matching_rows = [
            row
            for row in manifest.get("rows") or []
            if row.get("stock_pool_id") == aggregate.stock_pool_id
            and row.get("sku_id") == aggregate.sku_id
            and row.get("canonical_size") == aggregate.canonical_size
        ]
        boundary_inclusive = "before" not in method and "pre" not in method
        if matching_rows:
            timing_policy = str(matching_rows[0].get("timing_policy") or "")
            if "pre_" in timing_policy:
                boundary_inclusive = False
        row_id = (
            str(matching_rows[0].get("row_id"))
            if len(matching_rows) == 1
            else f"{aggregate.batch_id}:{aggregate.stock_pool_id}"
        )
        source_rows.append(
            ManualCountSourceRow(
                row_id=row_id,
                batch_id=aggregate.batch_id,
                event_ts=aggregate.count_timestamp_at_almaty,
                event_date=aggregate.count_timestamp_at_almaty[:10],
                boundary_inclusive=boundary_inclusive,
                sku_key=aggregate.sku_key,
                sku_id=aggregate.sku_id,
                my_size=aggregate.canonical_size,
                stock_pool_id=aggregate.stock_pool_id,
                applies_to_sku_ids=tuple(aggregate.applies_to_sku_ids),
                quantity=int(aggregate.quantity),
                source_doc=str(manifest_path),
                source_images=tuple(aggregate.source_images),
            )
        )
    return sorted(source_rows, key=lambda row: (row.event_ts, row.sku_key, row.my_size, row.stock_pool_id))


def _balance_before_count(
    conn: sqlite3.Connection,
    row: ManualCountSourceRow,
    *,
    exclude_idempotency_key: str,
) -> int:
    op = "<=" if row.boundary_inclusive else "<"
    placeholders = ",".join("?" for _ in row.applies_to_sku_ids)
    sql = f"""
        SELECT COALESCE(SUM(qty_change), 0) AS balance
        FROM stock_ledger
        WHERE sku_id IN ({placeholders})
          AND event_date {op} ?
          AND COALESCE(store_code, ?) = ?
          AND COALESCE(idempotency_key, '') != ?
    """
    args = [*row.applies_to_sku_ids, row.event_date, STORE_CODE, STORE_CODE, exclude_idempotency_key]
    result = conn.execute(sql, args).fetchone()
    return int(result["balance"] or 0)


def _ledger_row_for_key(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT ledger_id, event_date, reference_type, qty_change, input_source,
               created_by, notes, reference_id
        FROM stock_ledger
        WHERE idempotency_key = ?
        """,
        (key,),
    ).fetchone()


def _parse_note_json(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _coverage_for_source_row(conn: sqlite3.Connection, row: ManualCountSourceRow) -> tuple[dict[str, Any], dict[str, Any] | None]:
    ledger = _ledger_row_for_key(conn, row.idempotency_key)
    base = {
        "batch_id": row.batch_id,
        "row_id": row.row_id,
        "event_ts": row.event_ts,
        "event_date": row.event_date,
        "sku_key": row.sku_key,
        "sku_id": row.sku_id,
        "my_size": row.my_size,
        "stock_pool_id": row.stock_pool_id,
        "applies_to_sku_ids": ";".join(row.applies_to_sku_ids),
        "source_quantity": row.quantity,
        "idempotency_key": row.idempotency_key,
    }
    if ledger is not None:
        notes = _parse_note_json(str(ledger["notes"] or ""))
        errors: list[str] = []
        if str(ledger["input_source"]) != INPUT_SOURCE:
            errors.append(f"INPUT_SOURCE_MISMATCH:{ledger['input_source']}")
        if str(ledger["reference_type"]) != "TEMP_OCR_FULL_SUPERSEDE":
            errors.append(f"REFERENCE_TYPE_MISMATCH:{ledger['reference_type']}")
        if str(ledger["event_date"]) != row.event_date:
            errors.append(f"EVENT_DATE_MISMATCH:{ledger['event_date']}")
        if notes.get("source_doc") != row.source_doc:
            errors.append("SOURCE_DOC_MISMATCH")
        if int(notes.get("source_quantity", row.quantity)) != row.quantity:
            errors.append("SOURCE_QUANTITY_MISMATCH")
        record = {
            **base,
            "coverage_status": "EXISTING_LEDGER" if not errors else "BLOCKED_LEDGER_MISMATCH",
            "ledger_id": int(ledger["ledger_id"]),
            "ledger_qty_change": int(ledger["qty_change"] or 0),
            "balance_before_count": notes.get("balance_before_override", ""),
            "expected_delta_if_missing": "",
            "blocker": ";".join(errors),
        }
        return record, record if errors else None

    balance_before = _balance_before_count(conn, row, exclude_idempotency_key=row.idempotency_key)
    expected_delta = row.quantity - balance_before
    if expected_delta == 0:
        return (
            {
                **base,
                "coverage_status": "NOOP_ZERO_DELTA",
                "ledger_id": "",
                "ledger_qty_change": 0,
                "balance_before_count": balance_before,
                "expected_delta_if_missing": 0,
                "blocker": "",
            },
            None,
        )
    record = {
        **base,
        "coverage_status": "MISSING_LEDGER_DELTA",
        "ledger_id": "",
        "ledger_qty_change": "",
        "balance_before_count": balance_before,
        "expected_delta_if_missing": expected_delta,
        "blocker": "expected temp OCR ledger row is missing and row is not zero-delta",
    }
    return record, record


def _expected_anchor(plan: ManifestPlan) -> dict[str, Any]:
    approval = plan.manifest.get("approval") or {}
    return {
        "anchor_id": plan.anchor_id,
        "anchor_type": ANCHOR_TYPE,
        "source_path": str(plan.manifest_path),
        "source_sha256": plan.source_sha256,
        "snapshot_date": plan.latest_event_date,
        "as_of_date": plan.latest_event_date,
        "row_count": plan.aggregate_row_count,
        "total_units": plan.total_units,
        "approved_by": str(approval.get("approved_by") or ""),
        "approved_at": str(approval.get("approved_at") or ""),
        "status": "APPROVED",
        "notes": json.dumps(
            {
                "precedence": plan.manifest.get("precedence") or {},
                "event_dates": plan.event_dates,
                "source": "owner_approved_manual_stock_count_manifest",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def _expected_batch(plan: ManifestPlan, report_path: Path, *, applied_at: str) -> dict[str, Any]:
    approval = plan.manifest.get("approval") or {}
    return {
        "batch_id": plan.adjustment_batch_id,
        "anchor_id": plan.anchor_id,
        "method": METHOD,
        "method_version": METHOD_VERSION,
        "reduction_rate": None,
        "target_units_delta": plan.ledger_delta_sum,
        "generated_units_delta": plan.ledger_delta_sum,
        "dry_run_report_path": str(report_path),
        "approved_by": str(approval.get("approved_by") or ""),
        "approved_at": str(approval.get("approved_at") or ""),
        "applied_at": applied_at,
        "rollback_batch_id": "",
        "status": "APPLIED",
        "notes": json.dumps(
            {
                "ledger_input_source": INPUT_SOURCE,
                "ledger_rows_existing": plan.ledger_row_count,
                "noop_zero_delta_rows": plan.noop_row_count,
                "movement_policy": "metadata_only_over_existing_temp_ocr_stock_ledger_rows",
                "no_double_count": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def _metadata_action(
    conn: sqlite3.Connection,
    *,
    table: str,
    key_column: str,
    key_value: str,
    expected: dict[str, Any],
    compare_keys: Iterable[str],
) -> tuple[str, str]:
    row = conn.execute(f"SELECT * FROM {table} WHERE {key_column} = ?", (key_value,)).fetchone()
    if row is None:
        return "INSERT", ""
    mismatches = []
    for key in compare_keys:
        actual = row[key]
        expected_value = expected[key]
        if actual is None and expected_value in ("", None):
            continue
        if str(actual) != str(expected_value):
            mismatches.append(f"{key}:{actual}!={expected_value}")
    if mismatches:
        return "BLOCKED_MISMATCH", ";".join(mismatches)
    return "EXISTS", ""


def build_plans(
    conn: sqlite3.Connection,
    *,
    manifest_paths: list[Path],
    output_root: Path,
    applied_at: str,
) -> list[ManifestPlan]:
    plans: list[ManifestPlan] = []
    for manifest_path in manifest_paths:
        resolved_path = manifest_path if manifest_path.is_absolute() else PROJECT_ROOT / manifest_path
        manifest = load_approved_manual_stock_manifest(resolved_path)
        source_rows = _source_rows_from_manifest(resolved_path, manifest)
        coverage_rows: list[dict[str, Any]] = []
        blocked_rows: list[dict[str, Any]] = []
        for source_row in source_rows:
            coverage, blocker = _coverage_for_source_row(conn, source_row)
            coverage_rows.append(coverage)
            if blocker is not None:
                blocked_rows.append(blocker)

        plan = ManifestPlan(
            manifest_path=resolved_path,
            manifest=manifest,
            source_sha256=_file_sha256(resolved_path),
            source_rows=source_rows,
            coverage_rows=coverage_rows,
            blocked_rows=blocked_rows,
            anchor_action="",
            batch_action="",
        )
        anchor_expected = _expected_anchor(plan)
        batch_expected = _expected_batch(plan, output_root / f"{plan.batch_id}_coverage.csv", applied_at=applied_at)
        plan.anchor_action, plan.anchor_blocker = _metadata_action(
            conn,
            table="stock_anchor",
            key_column="anchor_id",
            key_value=plan.anchor_id,
            expected=anchor_expected,
            compare_keys=(
                "anchor_type",
                "source_path",
                "source_sha256",
                "snapshot_date",
                "as_of_date",
                "row_count",
                "total_units",
                "status",
            ),
        )
        plan.batch_action, plan.batch_blocker = _metadata_action(
            conn,
            table="stock_adjustment_batch",
            key_column="batch_id",
            key_value=plan.adjustment_batch_id,
            expected=batch_expected,
            compare_keys=(
                "anchor_id",
                "method",
                "method_version",
                "target_units_delta",
                "generated_units_delta",
                "status",
            ),
        )
        plans.append(plan)
    return plans


def _insert_anchor(conn: sqlite3.Connection, plan: ManifestPlan) -> None:
    expected = _expected_anchor(plan)
    conn.execute(
        """
        INSERT INTO stock_anchor (
            anchor_id, anchor_type, source_path, source_sha256, snapshot_date,
            as_of_date, row_count, total_units, approved_by, approved_at,
            status, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            expected["anchor_id"],
            expected["anchor_type"],
            expected["source_path"],
            expected["source_sha256"],
            expected["snapshot_date"],
            expected["as_of_date"],
            expected["row_count"],
            expected["total_units"],
            expected["approved_by"],
            expected["approved_at"],
            expected["status"],
            expected["notes"],
        ),
    )


def _insert_batch(conn: sqlite3.Connection, plan: ManifestPlan, report_path: Path, *, applied_at: str) -> None:
    expected = _expected_batch(plan, report_path, applied_at=applied_at)
    conn.execute(
        """
        INSERT INTO stock_adjustment_batch (
            batch_id, anchor_id, method, method_version, reduction_rate,
            target_units_delta, generated_units_delta, dry_run_report_path,
            approved_by, approved_at, applied_at, rollback_batch_id, status, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            expected["batch_id"],
            expected["anchor_id"],
            expected["method"],
            expected["method_version"],
            expected["reduction_rate"],
            expected["target_units_delta"],
            expected["generated_units_delta"],
            expected["dry_run_report_path"],
            expected["approved_by"],
            expected["approved_at"],
            expected["applied_at"],
            expected["rollback_batch_id"],
            expected["status"],
            expected["notes"],
        ),
    )


def _write_closeout(path: Path, summary: dict[str, Any]) -> None:
    rollback = (
        f"Restore backup `{summary['backup_path']}` over `{summary['db_path']}` after stopping writers, "
        "or delete the exact inserted stock_anchor/stock_adjustment_batch ids listed in summary.json."
        if summary.get("backup_path")
        else "No DB write occurred; no rollback is required."
    )
    text = f"""# Manual Stock Count Anchor Materialization Closeout

Status: {summary['status']}
Mode: {summary['mode']}
Generated at: {summary['generated_at_almaty']}

## Scope

This materializes governed metadata for owner-approved manual stock count
anchors. It does not create stock movement rows. Existing
`OWNER_APPROVED_TEMP_OCR_OVERRIDE` stock-ledger rows remain the movement evidence,
and zero-delta count rows are documented as no-ops.

## Counts

- Manifests: {summary['manifest_count']}
- Anchor inserts planned/performed: {summary['anchor_insert_count']}
- Batch inserts planned/performed: {summary['batch_insert_count']}
- Existing ledger coverage rows: {summary['existing_ledger_rows']}
- Zero-delta no-op rows: {summary['noop_zero_delta_rows']}
- Missing/blocking rows: {summary['blocked_rows']}
- Metadata mismatches: {summary['metadata_mismatch_count']}

## Safety

- DB SHA before: {summary['pre_sha256']}
- DB SHA after: {summary['post_sha256']}
- SQLite integrity: {summary['sqlite_integrity_check']}
- Backup: {summary.get('backup_path') or ''}

## Rollback

{rollback}
"""
    path.write_text(text, encoding="utf-8")


def write_outputs(output_root: Path, plans: list[ManifestPlan], summary: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    for plan in plans:
        coverage_path = output_root / f"{plan.batch_id}_coverage.csv"
        _write_csv(coverage_path, plan.coverage_rows)
        coverage_rows.extend(plan.coverage_rows)
        blocked_rows.extend(plan.blocked_rows)
        manifest_rows.append(
            {
                "batch_id": plan.batch_id,
                "manifest_path": str(plan.manifest_path),
                "source_sha256": plan.source_sha256,
                "anchor_id": plan.anchor_id,
                "adjustment_batch_id": plan.adjustment_batch_id,
                "aggregate_row_count": plan.aggregate_row_count,
                "total_units": plan.total_units,
                "event_dates": ";".join(plan.event_dates),
                "existing_ledger_rows": plan.ledger_row_count,
                "noop_zero_delta_rows": plan.noop_row_count,
                "ledger_delta_sum": plan.ledger_delta_sum,
                "anchor_action": plan.anchor_action,
                "batch_action": plan.batch_action,
                "anchor_blocker": plan.anchor_blocker,
                "batch_blocker": plan.batch_blocker,
                "is_safe": str(plan.is_safe).lower(),
            }
        )
    _write_csv(output_root / "manifest_summary.csv", manifest_rows)
    _write_csv(output_root / "coverage_rows.csv", coverage_rows)
    _write_csv(output_root / "blocked_rows.csv", blocked_rows)
    _write_json(output_root / "summary.json", summary)
    _write_closeout(output_root / "closeout.md", summary)


def materialize_manual_stock_count_anchors(
    *,
    db_path: Path,
    manifest_paths: list[Path],
    output_root: Path,
    apply: bool = False,
    expected_pre_sha256: str = "",
    backup_dir: Path | None = None,
    json_output: bool = False,
) -> dict[str, Any]:
    db_path = db_path.expanduser()
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    output_root = output_root.expanduser()
    if not output_root.is_absolute():
        output_root = PROJECT_ROOT / output_root
    if not db_path.exists():
        raise RuntimeError(f"DB not found: {db_path}")

    generated_at = datetime.now(ALMATY).isoformat(timespec="seconds")
    pre_sha = _file_sha256(db_path)
    with _connect(db_path, readonly=True) as conn:
        plans = build_plans(
            conn,
            manifest_paths=manifest_paths,
            output_root=output_root,
            applied_at=generated_at,
        )

    blocked_rows = sum(len(plan.blocked_rows) for plan in plans)
    metadata_mismatch_count = sum(1 for plan in plans if plan.anchor_blocker or plan.batch_blocker)
    anchor_insert_count = sum(1 for plan in plans if plan.anchor_action == "INSERT")
    batch_insert_count = sum(1 for plan in plans if plan.batch_action == "INSERT")
    existing_ledger_rows = sum(plan.ledger_row_count for plan in plans)
    noop_zero_delta_rows = sum(plan.noop_row_count for plan in plans)
    is_safe_to_apply = blocked_rows == 0 and metadata_mismatch_count == 0

    backup_path = ""
    status = "DRY_RUN"
    if apply:
        if os.environ.get(ENV_GATE) != "1":
            raise RuntimeError(f"apply requires {ENV_GATE}=1")
        if not expected_pre_sha256:
            raise RuntimeError("apply requires --expected-pre-sha256")
        if expected_pre_sha256 != pre_sha:
            raise RuntimeError(f"pre-sha mismatch: expected {expected_pre_sha256}, observed {pre_sha}")
        if not is_safe_to_apply:
            raise RuntimeError("manual stock count anchor coverage is not safe to apply")
        if _is_production_db(db_path):
            if os.environ.get(PRODUCTION_ENV_GATE) != "1":
                raise RuntimeError(f"production apply requires {PRODUCTION_ENV_GATE}=1")
            _fail_on_sqlite_sidecars(db_path)
            if backup_dir is None:
                raise RuntimeError("production apply requires --backup-dir")
        backup_path = str(backup_database(db_path, backup_dir or (output_root / "backups"), compress=False))
        with _connect(db_path, readonly=False) as conn:
            for plan in plans:
                if plan.anchor_action == "INSERT":
                    _insert_anchor(conn, plan)
                if plan.batch_action == "INSERT":
                    _insert_batch(
                        conn,
                        plan,
                        output_root / f"{plan.batch_id}_coverage.csv",
                        applied_at=generated_at,
                    )
            conn.commit()
        status = "APPLIED"

    post_sha = _file_sha256(db_path)
    integrity = _sqlite_integrity_check(db_path)
    summary = {
        "status": status,
        "mode": "apply" if apply else "dry_run",
        "generated_at_almaty": generated_at,
        "db_path": str(db_path),
        "pre_sha256": pre_sha,
        "post_sha256": post_sha,
        "sqlite_integrity_check": integrity,
        "backup_path": backup_path,
        "manifest_count": len(plans),
        "manifest_batch_ids": [plan.batch_id for plan in plans],
        "anchor_insert_count": anchor_insert_count,
        "batch_insert_count": batch_insert_count,
        "existing_ledger_rows": existing_ledger_rows,
        "noop_zero_delta_rows": noop_zero_delta_rows,
        "blocked_rows": blocked_rows,
        "metadata_mismatch_count": metadata_mismatch_count,
        "is_safe_to_apply": is_safe_to_apply,
        "movement_policy": "metadata_only_no_stock_ledger_inserts",
        "env_gate": ENV_GATE,
        "production_env_gate": PRODUCTION_ENV_GATE,
        "output_root": str(output_root),
    }
    write_outputs(output_root, plans, summary)
    if json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--manifest", dest="manifests", action="append", type=Path, default=[])
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true", help="Insert stock anchor metadata")
    parser.add_argument("--expected-pre-sha256", default="", help="Required for apply")
    parser.add_argument("--backup-dir", type=Path, default=None, help="Required for production apply")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = materialize_manual_stock_count_anchors(
        db_path=args.db,
        manifest_paths=_manifest_paths(args.manifests),
        output_root=args.output_root,
        apply=args.apply,
        expected_pre_sha256=args.expected_pre_sha256,
        backup_dir=args.backup_dir,
        json_output=args.json,
    )
    if not args.json:
        print(f"status={summary['status']}")
        print(f"is_safe_to_apply={str(summary['is_safe_to_apply']).lower()}")
        print(f"manifest_count={summary['manifest_count']}")
        print(f"anchor_insert_count={summary['anchor_insert_count']}")
        print(f"batch_insert_count={summary['batch_insert_count']}")
        print(f"blocked_rows={summary['blocked_rows']}")
        print(f"metadata_mismatch_count={summary['metadata_mismatch_count']}")
        print(f"output_root={summary['output_root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
