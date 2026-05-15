#!/usr/bin/env python3
"""Production-safe wrapper for Agent 31 STOREB API order-entry materialization.

The Agent 31 materializer is intentionally temp-only. This wrapper preserves
that guard by applying the materializer to a staging copy, proving exact row
deltas and quarantine non-leakage, then replacing the requested DB only after
backup, SHA, and integrity gates pass.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.materialize_storeb_api_order_entries_from_agent31 import (  # noqa: E402
    DEFAULT_DB,
    WRITE_ENV_GATE as TEMP_ENV_GATE,
    MaterializationError,
    materialize_storeb_api_order_entries,
)


PRODUCTION_ENV_GATE = "ENABLE_STOREB_API_ORDER_ENTRY_PRODUCTION_APPLY"


class ProductionAgent31ApplyError(RuntimeError):
    """Raised when the production-safe Agent 31 wrapper cannot prove safety."""


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
        raise ProductionAgent31ApplyError(f"refusing file replacement while SQLite sidecars exist: {joined}")


def _copy_or_raise(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if not target.exists():
        raise ProductionAgent31ApplyError(f"required copy was not created: {target}")


def _read_quarantine_order_ids(quarantine_rows_path: Path) -> list[str]:
    with quarantine_rows_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        order_ids = sorted({str(row.get("order_id") or "").strip() for row in reader if row.get("order_id")})
    return [order_id for order_id in order_ids if order_id]


def _entry_count_for_orders(db_path: Path, order_ids: list[str]) -> int:
    if not order_ids:
        return 0
    placeholders = ",".join("?" for _ in order_ids)
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_order_entries_kaspi'"
        ).fetchone()
        if not exists:
            return 0
        row = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM fact_order_entries_kaspi
            WHERE UPPER(COALESCE(store_code, 'UNIVERSAL')) = 'STOREB'
              AND CAST(order_id AS TEXT) IN ({placeholders})
            """,
            order_ids,
        ).fetchone()
    return int(row[0] if row else 0)


def _write_summary(output_root: Path, summary: dict[str, Any]) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "summary.json"
    summary["summary_json"] = str(summary_path)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def _backup_path_for(db_path: Path, backup_dir: Path, generated_at: str) -> Path:
    safe_ts = generated_at.replace(":", "").replace("-", "").replace("+", "_").replace("T", "_")
    return backup_dir / f"{db_path.stem}_pre_storeb_api_order_entries_agent31_{safe_ts}{db_path.suffix}"


def _staging_path_for(db_path: Path, output_root: Path, generated_at: str) -> Path:
    safe_ts = generated_at.replace(":", "").replace("-", "").replace("+", "_").replace("T", "_")
    return output_root / "staging" / f"{db_path.stem}_storeb_api_order_entries_agent31_staging_{safe_ts}{db_path.suffix}"


def _validate_summary_counts(
    *,
    materializer_summary: dict[str, Any],
    expected_safe_order_rows: int,
    expected_candidate_entry_rows: int,
    expected_inserted_entry_rows: int,
    expected_quarantine_rows: int,
) -> None:
    safe_order_rows = int(materializer_summary.get("safe_order_rows") or 0)
    if safe_order_rows != expected_safe_order_rows:
        raise ProductionAgent31ApplyError(
            f"safe_order_rows mismatch: expected {expected_safe_order_rows}, got {safe_order_rows}"
        )
    candidate_entry_rows = int(materializer_summary.get("candidate_entry_rows") or 0)
    if candidate_entry_rows != expected_candidate_entry_rows:
        raise ProductionAgent31ApplyError(
            f"candidate_entry_rows mismatch: expected {expected_candidate_entry_rows}, got {candidate_entry_rows}"
        )
    quarantine_rows = int(materializer_summary.get("quarantine_rows") or 0)
    if quarantine_rows != expected_quarantine_rows:
        raise ProductionAgent31ApplyError(
            f"quarantine_rows mismatch: expected {expected_quarantine_rows}, got {quarantine_rows}"
        )
    apply_summary = dict(materializer_summary.get("apply") or {})
    inserted_entry_rows = int(apply_summary.get("inserted_entry_rows") or 0)
    if inserted_entry_rows != expected_inserted_entry_rows:
        raise ProductionAgent31ApplyError(
            f"inserted_entry_rows mismatch: expected {expected_inserted_entry_rows}, got {inserted_entry_rows}"
        )
    expected_skipped = expected_candidate_entry_rows - expected_inserted_entry_rows
    skipped_existing = int(apply_summary.get("skipped_existing_entry_rows") or 0)
    if skipped_existing != expected_skipped:
        raise ProductionAgent31ApplyError(
            f"skipped_existing_entry_rows mismatch: expected {expected_skipped}, got {skipped_existing}"
        )


def _validate_drift_proof(
    *,
    reviewed_drift_proof: Path | None,
    expected_candidate_entry_rows: int,
    expected_inserted_entry_rows: int,
) -> str | None:
    if expected_inserted_entry_rows >= expected_candidate_entry_rows:
        return None
    if reviewed_drift_proof is None:
        raise ProductionAgent31ApplyError(
            "reviewed drift proof is required when expected_inserted_entry_rows "
            "is lower than expected_candidate_entry_rows"
        )
    proof = Path(reviewed_drift_proof).resolve()
    if not proof.exists():
        raise ProductionAgent31ApplyError(f"reviewed drift proof not found: {proof}")
    return str(proof)


def apply_storeb_api_order_entries_from_agent31_production_safe(
    *,
    db_path: Path,
    safe_rows_path: Path,
    api_entries_path: Path,
    quarantine_rows_path: Path,
    output_root: Path,
    backup_dir: Path,
    expected_pre_sha256: str,
    expected_safe_order_rows: int,
    expected_candidate_entry_rows: int,
    expected_inserted_entry_rows: int,
    expected_quarantine_rows: int,
    reviewed_drift_proof: Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    target_db = Path(db_path).resolve()
    safe_rows = Path(safe_rows_path).resolve()
    api_entries = Path(api_entries_path).resolve()
    quarantine_rows = Path(quarantine_rows_path).resolve()
    output = Path(output_root).resolve()
    backups = Path(backup_dir).resolve()
    generated_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

    if not target_db.exists():
        raise ProductionAgent31ApplyError(f"db not found: {target_db}")
    for input_path, label in (
        (safe_rows, "safe rows"),
        (api_entries, "API entries"),
        (quarantine_rows, "quarantine rows"),
    ):
        if not input_path.exists():
            raise ProductionAgent31ApplyError(f"{label} file not found: {input_path}")

    drift_proof = _validate_drift_proof(
        reviewed_drift_proof=reviewed_drift_proof,
        expected_candidate_entry_rows=expected_candidate_entry_rows,
        expected_inserted_entry_rows=expected_inserted_entry_rows,
    )

    pre_sha256 = _sha256(target_db)
    if pre_sha256 != expected_pre_sha256:
        raise ProductionAgent31ApplyError(
            f"pre-write SHA mismatch: expected {expected_pre_sha256}, got {pre_sha256}"
        )

    integrity_before = _integrity_check(target_db)
    if integrity_before.lower() != "ok":
        raise ProductionAgent31ApplyError(f"pre-write integrity_check failed: {integrity_before}")

    try:
        dry_run_summary = materialize_storeb_api_order_entries(
            db_path=target_db,
            safe_rows_path=safe_rows,
            api_entries_path=api_entries,
            quarantine_rows_path=quarantine_rows,
            output_root=output / "materializer_dry_run",
            apply=False,
            expected_safe_order_rows=expected_safe_order_rows,
            expected_quarantine_rows=expected_quarantine_rows,
        )
    except MaterializationError as exc:
        raise ProductionAgent31ApplyError(str(exc)) from exc

    dry_candidate_rows = int(dry_run_summary.get("candidate_entry_rows") or 0)
    if dry_candidate_rows != expected_candidate_entry_rows:
        raise ProductionAgent31ApplyError(
            f"candidate_entry_rows mismatch: expected {expected_candidate_entry_rows}, got {dry_candidate_rows}"
        )
    dry_would_insert = int(dict(dry_run_summary.get("apply") or {}).get("would_insert_entry_rows") or 0)
    if dry_would_insert != expected_inserted_entry_rows:
        raise ProductionAgent31ApplyError(
            "inserted_entry_rows mismatch at dry-run preflight: "
            f"expected {expected_inserted_entry_rows}, would insert {dry_would_insert}"
        )

    quarantine_order_ids = _read_quarantine_order_ids(quarantine_rows)
    quarantine_entry_count_before = _entry_count_for_orders(target_db, quarantine_order_ids)
    production_target = _target_is_production(target_db)
    summary: dict[str, Any] = {
        "generated_at": generated_at,
        "db_path": str(target_db),
        "agent31_inputs": {
            "safe_rows_path": str(safe_rows),
            "api_entries_path": str(api_entries),
            "quarantine_rows_path": str(quarantine_rows),
        },
        "output_root": str(output),
        "backup_dir": str(backups),
        "backup_path": None,
        "expected": {
            "pre_sha256": expected_pre_sha256,
            "safe_order_rows": expected_safe_order_rows,
            "candidate_entry_rows": expected_candidate_entry_rows,
            "inserted_entry_rows": expected_inserted_entry_rows,
            "quarantine_rows": expected_quarantine_rows,
        },
        "reviewed_drift_proof": drift_proof,
        "pre_sha256": pre_sha256,
        "post_sha256": pre_sha256,
        "integrity_check": {"before": integrity_before, "after": integrity_before},
        "quarantine_product_truth_probe": {
            "order_ids": quarantine_order_ids,
            "before_count": quarantine_entry_count_before,
            "after_count": quarantine_entry_count_before,
            "passed": quarantine_entry_count_before == 0,
        },
        "env_gate": PRODUCTION_ENV_GATE,
        "temp_materializer_env_gate": TEMP_ENV_GATE,
        "apply": {
            "requested": bool(apply),
            "applied": False,
            "target_replaced": False,
            "staging_path": None,
        },
        "materializer_summary": dry_run_summary,
        "production_db_target": production_target,
        "production_db_modified": False,
        "rollback": {
            "backup_path": None,
            "restore_command": None,
            "verify_command": f"sqlite3 -readonly {target_db} 'PRAGMA integrity_check;'",
        },
    }

    if quarantine_entry_count_before:
        raise ProductionAgent31ApplyError(
            f"quarantine rows already exist as product truth before apply: {quarantine_entry_count_before}"
        )

    if not apply:
        _write_summary(output, summary)
        return summary

    if os.environ.get(PRODUCTION_ENV_GATE) != "1":
        raise ProductionAgent31ApplyError(f"{PRODUCTION_ENV_GATE}=1 is required with --apply")
    _fail_on_sqlite_sidecars(target_db)

    backup_path = _backup_path_for(target_db, backups, generated_at)
    staging_path = _staging_path_for(target_db, output, generated_at)
    _copy_or_raise(target_db, backup_path)
    _copy_or_raise(target_db, staging_path)
    if _integrity_check(backup_path).lower() != "ok":
        raise ProductionAgent31ApplyError(f"backup integrity_check failed: {backup_path}")
    if _integrity_check(staging_path).lower() != "ok":
        raise ProductionAgent31ApplyError(f"staging integrity_check failed: {staging_path}")

    previous_temp_gate = os.environ.get(TEMP_ENV_GATE)
    os.environ[TEMP_ENV_GATE] = "1"
    try:
        materializer_summary = materialize_storeb_api_order_entries(
            db_path=staging_path,
            safe_rows_path=safe_rows,
            api_entries_path=api_entries,
            quarantine_rows_path=quarantine_rows,
            output_root=output / "materializer_apply",
            apply=True,
            expected_safe_order_rows=expected_safe_order_rows,
            expected_quarantine_rows=expected_quarantine_rows,
        )
    except MaterializationError as exc:
        raise ProductionAgent31ApplyError(str(exc)) from exc
    finally:
        if previous_temp_gate is None:
            os.environ.pop(TEMP_ENV_GATE, None)
        else:
            os.environ[TEMP_ENV_GATE] = previous_temp_gate

    _validate_summary_counts(
        materializer_summary=materializer_summary,
        expected_safe_order_rows=expected_safe_order_rows,
        expected_candidate_entry_rows=expected_candidate_entry_rows,
        expected_inserted_entry_rows=expected_inserted_entry_rows,
        expected_quarantine_rows=expected_quarantine_rows,
    )

    quarantine_entry_count_after = _entry_count_for_orders(staging_path, quarantine_order_ids)
    if quarantine_entry_count_after:
        raise ProductionAgent31ApplyError(
            f"quarantine rows inserted as product truth: {quarantine_entry_count_after}"
        )

    integrity_after = _integrity_check(staging_path)
    if integrity_after.lower() != "ok":
        raise ProductionAgent31ApplyError(f"post-write integrity_check failed on staging: {integrity_after}")

    current_sha256 = _sha256(target_db)
    if current_sha256 != pre_sha256:
        raise ProductionAgent31ApplyError(
            f"target changed before replace: expected {pre_sha256}, got {current_sha256}"
        )

    os.replace(staging_path, target_db)
    final_sha256 = _sha256(target_db)
    final_integrity = _integrity_check(target_db)
    if final_integrity.lower() != "ok":
        raise ProductionAgent31ApplyError(f"post-replace integrity_check failed: {final_integrity}")

    summary.update(
        {
            "backup_path": str(backup_path),
            "post_sha256": final_sha256,
            "integrity_check": {"before": integrity_before, "after": final_integrity},
            "quarantine_product_truth_probe": {
                "order_ids": quarantine_order_ids,
                "before_count": quarantine_entry_count_before,
                "after_count": quarantine_entry_count_after,
                "passed": True,
            },
            "apply": {
                "requested": True,
                "applied": True,
                "target_replaced": True,
                "staging_path": str(staging_path),
            },
            "materializer_summary": materializer_summary,
            "production_db_modified": production_target,
            "rollback": {
                "backup_path": str(backup_path),
                "restore_command": f"cp {backup_path} {target_db}",
                "verify_command": f"sqlite3 -readonly {target_db} 'PRAGMA integrity_check;'",
            },
        }
    )
    _write_summary(output, summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--safe-rows", type=Path, required=True)
    parser.add_argument("--api-entries", type=Path, required=True)
    parser.add_argument("--quarantine-rows", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--expected-pre-sha256", required=True)
    parser.add_argument("--expected-safe-order-rows", type=int, required=True)
    parser.add_argument("--expected-candidate-entry-rows", type=int, required=True)
    parser.add_argument("--expected-inserted-entry-rows", type=int, required=True)
    parser.add_argument("--expected-quarantine-rows", type=int, required=True)
    parser.add_argument("--reviewed-drift-proof", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv or sys.argv[1:])
    try:
        summary = apply_storeb_api_order_entries_from_agent31_production_safe(
            db_path=args.db,
            safe_rows_path=args.safe_rows,
            api_entries_path=args.api_entries,
            quarantine_rows_path=args.quarantine_rows,
            output_root=args.output_root,
            backup_dir=args.backup_dir,
            expected_pre_sha256=args.expected_pre_sha256,
            expected_safe_order_rows=args.expected_safe_order_rows,
            expected_candidate_entry_rows=args.expected_candidate_entry_rows,
            expected_inserted_entry_rows=args.expected_inserted_entry_rows,
            expected_quarantine_rows=args.expected_quarantine_rows,
            reviewed_drift_proof=args.reviewed_drift_proof,
            apply=bool(args.apply),
        )
    except ProductionAgent31ApplyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"summary_json={summary['summary_json']}")
        print(f"applied={summary['apply']['applied']}")
        print(f"backup_path={summary['backup_path']}")
        print(f"safe_order_rows={summary['materializer_summary']['safe_order_rows']}")
        print(f"candidate_entry_rows={summary['materializer_summary']['candidate_entry_rows']}")
        print(f"inserted_entry_rows={summary['materializer_summary']['apply']['inserted_entry_rows']}")
        print(f"skipped_existing_entry_rows={summary['materializer_summary']['apply']['skipped_existing_entry_rows']}")
        print(f"quarantine_product_truth_passed={summary['quarantine_product_truth_probe']['passed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
