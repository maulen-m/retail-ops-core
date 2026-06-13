#!/usr/bin/env python3
"""Production-safe wrapper for the STOREB header-only source-gap quarantine.

The direct header-only materializer is intentionally temp-only. This wrapper
keeps that boundary intact by proving exact deltas on a SQLite-backup staging
copy first, then applying the same materializer in place to the requested DB
only after backup, SHA, sidecar, and integrity gates pass. It never swaps a
staging DB file over the target.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.materialize_header_only_source_gap_quarantine import (  # noqa: E402
    DEFAULT_DB,
    WRITE_ENV_GATE as TEMP_ENV_GATE,
    HeaderOnlySourceGapQuarantineError,
    materialize_header_only_source_gap_quarantine,
)
from scripts.backup_db import backup_database  # noqa: E402


PRODUCTION_ENV_GATE = "ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_PRODUCTION_APPLY"


class ProductionHeaderOnlySourceGapQuarantineApplyError(RuntimeError):
    """Raised when the production-safe wrapper cannot prove write safety."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity_check(path: Path) -> str:
    uri = f"file:{path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    return str(row[0] if row else "")


def _target_is_production(db_path: Path) -> bool:
    try:
        return db_path.resolve() == DEFAULT_DB.resolve()
    except FileNotFoundError:
        return db_path.absolute() == DEFAULT_DB.absolute()


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(f"{db_path}-wal"), Path(f"{db_path}-shm"), Path(f"{db_path}-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"refusing production apply while SQLite sidecars exist: {joined}"
        )


def _verify_sqlite_database(*, path: Path, label: str) -> str:
    integrity = _integrity_check(path)
    if integrity.lower() != "ok":
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"{label} integrity_check failed: {integrity}"
        )
    return integrity


def _cash_in_count(db_path: Path, order_ids: list[str]) -> int:
    if not order_ids:
        return 0
    placeholders = ",".join("?" for _ in order_ids)
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_cashflow_events'"
        ).fetchone()
        if not exists:
            return 0
        row = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM fact_cashflow_events
            WHERE CAST(ref_id AS TEXT) IN ({placeholders})
              AND UPPER(COALESCE(event_type, '')) = 'CASH_IN'
            """,
            order_ids,
        ).fetchone()
    return int(row[0] if row else 0)


def _actual_deltas(materializer_summary: dict[str, Any]) -> dict[str, int]:
    apply_summary = dict(materializer_summary.get("apply") or {})
    return {
        "candidate_rows": int(materializer_summary.get("candidate_rows") or 0),
        "deleted_product_cashflow_rows": int(apply_summary.get("deleted_product_cashflow_rows") or 0),
        "deleted_stock_ledger_rows": int(apply_summary.get("deleted_stock_ledger_rows") or 0),
        "nulled_sales_fact_product_profit_rows": int(
            apply_summary.get("nulled_sales_fact_product_profit_rows") or 0
        ),
    }


def _validate_expected_deltas(
    *,
    materializer_summary: dict[str, Any],
    expected_deltas: dict[str, int],
) -> dict[str, int]:
    actual = _actual_deltas(materializer_summary)
    for key, expected_value in expected_deltas.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            raise ProductionHeaderOnlySourceGapQuarantineApplyError(
                f"{key} mismatch: expected {expected_value}, got {actual_value}"
            )
    return actual


def _write_summary(output_root: Path, summary: dict[str, Any]) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "summary.json"
    summary["summary_json"] = str(summary_path)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def _sqlite_backup_copy(*, source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    with sqlite3.connect(str(source)) as source_conn, sqlite3.connect(str(target)) as target_conn:
        source_conn.backup(target_conn)


def _staging_path_for(db_path: Path, output_root: Path, generated_at: str) -> Path:
    safe_ts = generated_at.replace(":", "").replace("-", "").replace("+", "_").replace("T", "_")
    return output_root / "staging" / f"{db_path.stem}_header_only_source_gap_quarantine_staging_{safe_ts}{db_path.suffix}"


def _restore_command(*, backup_path: Path, target_db: Path) -> str:
    return (
        "python3 - <<'PY'\n"
        "import sqlite3\n"
        f"backup_path = {str(backup_path)!r}\n"
        f"target_db = {str(target_db)!r}\n"
        "with sqlite3.connect(backup_path) as source, sqlite3.connect(target_db) as target:\n"
        "    source.backup(target)\n"
        "PY"
    )


def apply_header_only_source_gap_quarantine_production_safe(
    *,
    db_path: Path,
    classification_path: Path,
    output_root: Path,
    backup_dir: Path,
    expected_pre_sha256: str,
    expected_candidate_rows: int,
    expected_product_cashflow_delete_rows: int,
    expected_stock_ledger_delete_rows: int,
    expected_sales_fact_product_profit_null_rows: int,
    apply: bool = False,
) -> dict[str, Any]:
    target_db = Path(db_path).resolve()
    classification = Path(classification_path).resolve()
    output = Path(output_root).resolve()
    backups = Path(backup_dir).resolve()
    generated_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

    if not target_db.exists():
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(f"db not found: {target_db}")
    if not classification.exists():
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(f"classification file not found: {classification}")

    if apply and os.environ.get(PRODUCTION_ENV_GATE) != "1":
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(f"{PRODUCTION_ENV_GATE}=1 is required with --apply")

    pre_sha256 = _sha256(target_db)
    if pre_sha256 != expected_pre_sha256:
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"pre-write SHA mismatch: expected {expected_pre_sha256}, got {pre_sha256}"
        )

    integrity_before = _integrity_check(target_db)
    if integrity_before.lower() != "ok":
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"pre-write integrity_check failed: {integrity_before}"
        )

    expected_deltas = {
        "candidate_rows": int(expected_candidate_rows),
        "deleted_product_cashflow_rows": int(expected_product_cashflow_delete_rows),
        "deleted_stock_ledger_rows": int(expected_stock_ledger_delete_rows),
        "nulled_sales_fact_product_profit_rows": int(expected_sales_fact_product_profit_null_rows),
    }

    dry_run_summary = materialize_header_only_source_gap_quarantine(
        db_path=target_db,
        classification_path=classification,
        output_root=output / "materializer_dry_run",
        apply=False,
    )
    if int(dry_run_summary.get("candidate_rows") or 0) != expected_candidate_rows:
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            "candidate_rows mismatch: "
            f"expected {expected_candidate_rows}, got {dry_run_summary.get('candidate_rows')}"
        )

    order_ids = [str(order_id) for order_id in dry_run_summary.get("order_ids", [])]
    cash_in_before = _cash_in_count(target_db, order_ids)
    production_target = _target_is_production(target_db)
    dry_run_actual_deltas = _actual_deltas(dry_run_summary)
    summary: dict[str, Any] = {
        "generated_at": generated_at,
        "db_path": str(target_db),
        "classification_path": str(classification),
        "output_root": str(output),
        "backup_dir": str(backups),
        "backup_path": None,
        "backup_sha256": None,
        "staging_sha256_before_apply": None,
        "staging_sha256_after_apply": None,
        "expected": {
            "pre_sha256": expected_pre_sha256,
            **expected_deltas,
        },
        "actual": dry_run_actual_deltas,
        "pre_sha256": pre_sha256,
        "post_sha256": pre_sha256,
        "integrity_check": {
            "before": integrity_before,
            "backup": None,
            "staging_before_apply": None,
            "staging_after_apply": None,
            "after": integrity_before,
        },
        "cash_in_preservation": {
            "order_ids": order_ids,
            "before_count": cash_in_before,
            "after_count": cash_in_before,
            "preserved": True,
        },
        "env_gate": PRODUCTION_ENV_GATE,
        "temp_materializer_env_gate": TEMP_ENV_GATE,
        "apply": {
            "requested": bool(apply),
            "applied": False,
            "target_replaced": False,
            "staging_path": None,
            "write_mode": "dry_run",
        },
        "materializer_summary": dry_run_summary,
        "production_db_target": production_target,
        "production_db_modified": False,
        "fact_order_entries_inserted": 0,
        "header_fields_used_as_canonical_item_entry_truth": False,
        "rollback": {
            "backup_path": None,
            "restore_command": None,
            "verify_command": f"sqlite3 -readonly {target_db} 'PRAGMA integrity_check;'",
        },
    }

    if not apply:
        _write_summary(output, summary)
        return summary

    _fail_on_sqlite_sidecars(target_db)

    backup_path = backup_database(target_db, backups, compress=False)
    if not backup_path.exists():
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(f"required backup was not created: {backup_path}")
    backup_integrity = _verify_sqlite_database(path=backup_path, label="backup")

    staging_path = _staging_path_for(target_db, output, generated_at)
    _sqlite_backup_copy(source=target_db, target=staging_path)
    staging_sha256_before = _sha256(staging_path)
    staging_integrity_before = _verify_sqlite_database(path=staging_path, label="staging")

    previous_temp_gate = os.environ.get(TEMP_ENV_GATE)
    os.environ[TEMP_ENV_GATE] = "1"
    try:
        staging_materializer_summary = materialize_header_only_source_gap_quarantine(
            db_path=staging_path,
            classification_path=classification,
            output_root=output / "materializer_staging_apply",
            apply=True,
        )
    except HeaderOnlySourceGapQuarantineError as exc:
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(str(exc)) from exc
    finally:
        if previous_temp_gate is None:
            os.environ.pop(TEMP_ENV_GATE, None)
        else:
            os.environ[TEMP_ENV_GATE] = previous_temp_gate

    staging_actual_deltas = _validate_expected_deltas(
        materializer_summary=staging_materializer_summary,
        expected_deltas=expected_deltas,
    )
    cash_in_after_staging = _cash_in_count(staging_path, order_ids)
    if cash_in_after_staging != cash_in_before:
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"staging order-level CASH_IN preservation failed: before {cash_in_before}, "
            f"after {cash_in_after_staging}"
        )
    staging_sha256_after = _sha256(staging_path)
    staging_integrity_after = _integrity_check(staging_path)
    if staging_integrity_after.lower() != "ok":
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"post-write integrity_check failed on staging: {staging_integrity_after}"
        )

    current_sha256 = _sha256(target_db)
    if current_sha256 != expected_pre_sha256:
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"target changed before apply: expected {expected_pre_sha256}, got {current_sha256}"
        )

    previous_temp_gate = os.environ.get(TEMP_ENV_GATE)
    os.environ[TEMP_ENV_GATE] = "1"
    try:
        materializer_summary = materialize_header_only_source_gap_quarantine(
            db_path=target_db,
            classification_path=classification,
            output_root=output / "materializer_apply",
            apply=True,
            allow_production_apply=True,
        )
    except HeaderOnlySourceGapQuarantineError as exc:
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(str(exc)) from exc
    finally:
        if previous_temp_gate is None:
            os.environ.pop(TEMP_ENV_GATE, None)
        else:
            os.environ[TEMP_ENV_GATE] = previous_temp_gate

    actual_deltas = _validate_expected_deltas(
        materializer_summary=materializer_summary,
        expected_deltas=expected_deltas,
    )
    if actual_deltas != staging_actual_deltas:
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"production deltas diverged from staging proof: staging {staging_actual_deltas}, "
            f"production {actual_deltas}"
        )

    cash_in_after = _cash_in_count(target_db, order_ids)
    if cash_in_after != cash_in_before:
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"order-level CASH_IN preservation failed: before {cash_in_before}, after {cash_in_after}"
        )

    final_sha256 = _sha256(target_db)
    final_integrity = _integrity_check(target_db)
    if final_integrity.lower() != "ok":
        raise ProductionHeaderOnlySourceGapQuarantineApplyError(
            f"post-apply integrity_check failed: {final_integrity}"
        )

    summary.update(
        {
            "backup_path": str(backup_path),
            "backup_sha256": _sha256(backup_path),
            "staging_sha256_before_apply": staging_sha256_before,
            "staging_sha256_after_apply": staging_sha256_after,
            "actual": actual_deltas,
            "post_sha256": final_sha256,
            "integrity_check": {
                "before": integrity_before,
                "backup": backup_integrity,
                "staging_before_apply": staging_integrity_before,
                "staging_after_apply": staging_integrity_after,
                "after": final_integrity,
            },
            "cash_in_preservation": {
                "order_ids": order_ids,
                "before_count": cash_in_before,
                "after_count": cash_in_after,
                "preserved": True,
            },
            "apply": {
                "requested": True,
                "applied": True,
                "target_replaced": False,
                "staging_path": str(staging_path),
                "write_mode": "sqlite_in_place",
            },
            "materializer_summary": materializer_summary,
            "staging_materializer_summary": staging_materializer_summary,
            "production_db_modified": production_target,
            "fact_order_entries_inserted": 0,
            "header_fields_used_as_canonical_item_entry_truth": False,
            "rollback": {
                "backup_path": str(backup_path),
                "restore_command": _restore_command(backup_path=backup_path, target_db=target_db),
                "verify_command": f"sqlite3 -readonly {target_db} 'PRAGMA integrity_check;'",
            },
        }
    )
    _write_summary(output, summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--classification", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--expected-pre-sha256", required=True)
    parser.add_argument("--expected-candidate-rows", type=int, required=True)
    parser.add_argument("--expected-product-cashflow-delete-rows", type=int, required=True)
    parser.add_argument("--expected-stock-ledger-delete-rows", type=int, required=True)
    parser.add_argument("--expected-sales-fact-product-profit-null-rows", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv or sys.argv[1:])
    try:
        summary = apply_header_only_source_gap_quarantine_production_safe(
            db_path=args.db,
            classification_path=args.classification,
            output_root=args.output_root,
            backup_dir=args.backup_dir,
            expected_pre_sha256=args.expected_pre_sha256,
            expected_candidate_rows=args.expected_candidate_rows,
            expected_product_cashflow_delete_rows=args.expected_product_cashflow_delete_rows,
            expected_stock_ledger_delete_rows=args.expected_stock_ledger_delete_rows,
            expected_sales_fact_product_profit_null_rows=args.expected_sales_fact_product_profit_null_rows,
            apply=bool(args.apply),
        )
    except ProductionHeaderOnlySourceGapQuarantineApplyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"summary_json={summary['summary_json']}")
        print(f"applied={summary['apply']['applied']}")
        print(f"backup_path={summary['backup_path']}")
        print(f"deleted_product_cashflow_rows={summary['actual']['deleted_product_cashflow_rows']}")
        print(f"deleted_stock_ledger_rows={summary['actual']['deleted_stock_ledger_rows']}")
        print(
            "nulled_sales_fact_product_profit_rows="
            f"{summary['actual']['nulled_sales_fact_product_profit_rows']}"
        )
        print(f"cash_in_preserved={summary['cash_in_preservation']['preserved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
