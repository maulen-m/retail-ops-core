#!/usr/bin/env python3
"""Production-safe wrapper for the STOREB product-identity quarantine step.

The underlying quarantine materializer remains temp-only. This wrapper keeps
that guard intact by applying the materializer to a staging copy, proving exact
deltas, then replacing the requested DB only after backup, SHA, and integrity
gates pass.
"""

from __future__ import annotations

import argparse
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

from scripts.materialize_storeb_product_identity_quarantine import (  # noqa: E402
    DEFAULT_DB,
    WRITE_ENV_GATE as TEMP_ENV_GATE,
    QuarantineMaterializationError,
    materialize_storeb_product_identity_quarantine,
)


PRODUCTION_ENV_GATE = "ENABLE_STOREB_PRODUCT_IDENTITY_QUARANTINE_PRODUCTION_APPLY"


class ProductionQuarantineApplyError(RuntimeError):
    """Raised when the production-safe quarantine wrapper cannot prove safety."""


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
        raise ProductionQuarantineApplyError(f"refusing file replacement while SQLite sidecars exist: {joined}")


def _copy_or_raise(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if not target.exists():
        raise ProductionQuarantineApplyError(f"required copy was not created: {target}")


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


def _write_summary(output_root: Path, summary: dict[str, Any]) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "summary.json"
    summary["summary_json"] = str(summary_path)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def _validate_expected_delta(
    *,
    materializer_summary: dict[str, Any],
    expected_candidate_rows: int,
    expected_product_cashflow_delete_rows: int,
    expected_stock_ledger_delete_rows: int,
) -> None:
    candidate_rows = int(materializer_summary.get("candidate_rows") or 0)
    if candidate_rows != expected_candidate_rows:
        raise ProductionQuarantineApplyError(
            f"candidate_rows mismatch: expected {expected_candidate_rows}, got {candidate_rows}"
        )
    apply_summary = dict(materializer_summary.get("apply") or {})
    deleted_cashflow = int(apply_summary.get("deleted_product_cashflow_rows") or 0)
    if deleted_cashflow != expected_product_cashflow_delete_rows:
        raise ProductionQuarantineApplyError(
            "deleted_product_cashflow_rows mismatch: "
            f"expected {expected_product_cashflow_delete_rows}, got {deleted_cashflow}"
        )
    deleted_stock = int(apply_summary.get("deleted_stock_ledger_rows") or 0)
    if deleted_stock != expected_stock_ledger_delete_rows:
        raise ProductionQuarantineApplyError(
            f"deleted_stock_ledger_rows mismatch: expected {expected_stock_ledger_delete_rows}, got {deleted_stock}"
        )


def _backup_path_for(db_path: Path, backup_dir: Path, generated_at: str) -> Path:
    safe_ts = generated_at.replace(":", "").replace("-", "").replace("+", "_").replace("T", "_")
    return backup_dir / f"{db_path.stem}_pre_storeb_product_identity_quarantine_{safe_ts}{db_path.suffix}"


def _staging_path_for(db_path: Path, output_root: Path, generated_at: str) -> Path:
    safe_ts = generated_at.replace(":", "").replace("-", "").replace("+", "_").replace("T", "_")
    return output_root / "staging" / f"{db_path.stem}_storeb_product_identity_quarantine_staging_{safe_ts}{db_path.suffix}"


def apply_storeb_product_identity_quarantine_production_safe(
    *,
    db_path: Path,
    candidates_path: Path,
    output_root: Path,
    backup_dir: Path,
    expected_pre_sha256: str,
    expected_candidate_rows: int,
    expected_product_cashflow_delete_rows: int,
    expected_stock_ledger_delete_rows: int,
    apply: bool = False,
) -> dict[str, Any]:
    target_db = Path(db_path).resolve()
    candidates = Path(candidates_path).resolve()
    output = Path(output_root).resolve()
    backups = Path(backup_dir).resolve()
    generated_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

    if not target_db.exists():
        raise ProductionQuarantineApplyError(f"db not found: {target_db}")
    if not candidates.exists():
        raise ProductionQuarantineApplyError(f"candidate file not found: {candidates}")

    pre_sha256 = _sha256(target_db)
    if pre_sha256 != expected_pre_sha256:
        raise ProductionQuarantineApplyError(
            f"pre-write SHA mismatch: expected {expected_pre_sha256}, got {pre_sha256}"
        )

    integrity_before = _integrity_check(target_db)
    if integrity_before.lower() != "ok":
        raise ProductionQuarantineApplyError(f"pre-write integrity_check failed: {integrity_before}")

    dry_run_summary = materialize_storeb_product_identity_quarantine(
        db_path=target_db,
        candidates_path=candidates,
        output_root=output / "materializer_dry_run",
        apply=False,
    )
    if int(dry_run_summary.get("candidate_rows") or 0) != expected_candidate_rows:
        raise ProductionQuarantineApplyError(
            "candidate_rows mismatch: "
            f"expected {expected_candidate_rows}, got {dry_run_summary.get('candidate_rows')}"
        )

    order_ids = [str(order_id) for order_id in dry_run_summary.get("order_ids", [])]
    cash_in_before = _cash_in_count(target_db, order_ids)
    production_target = _target_is_production(target_db)
    summary: dict[str, Any] = {
        "generated_at": generated_at,
        "db_path": str(target_db),
        "candidates_path": str(candidates),
        "output_root": str(output),
        "backup_dir": str(backups),
        "backup_path": None,
        "expected": {
            "pre_sha256": expected_pre_sha256,
            "candidate_rows": expected_candidate_rows,
            "deleted_product_cashflow_rows": expected_product_cashflow_delete_rows,
            "deleted_stock_ledger_rows": expected_stock_ledger_delete_rows,
        },
        "pre_sha256": pre_sha256,
        "post_sha256": pre_sha256,
        "integrity_check": {"before": integrity_before, "after": integrity_before},
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

    if not apply:
        _write_summary(output, summary)
        return summary

    if os.environ.get(PRODUCTION_ENV_GATE) != "1":
        raise ProductionQuarantineApplyError(f"{PRODUCTION_ENV_GATE}=1 is required with --apply")
    _fail_on_sqlite_sidecars(target_db)

    backup_path = _backup_path_for(target_db, backups, generated_at)
    staging_path = _staging_path_for(target_db, output, generated_at)
    _copy_or_raise(target_db, backup_path)
    _copy_or_raise(target_db, staging_path)
    if _integrity_check(backup_path).lower() != "ok":
        raise ProductionQuarantineApplyError(f"backup integrity_check failed: {backup_path}")
    if _integrity_check(staging_path).lower() != "ok":
        raise ProductionQuarantineApplyError(f"staging integrity_check failed: {staging_path}")

    previous_temp_gate = os.environ.get(TEMP_ENV_GATE)
    os.environ[TEMP_ENV_GATE] = "1"
    try:
        materializer_summary = materialize_storeb_product_identity_quarantine(
            db_path=staging_path,
            candidates_path=candidates,
            output_root=output / "materializer_apply",
            apply=True,
        )
    except QuarantineMaterializationError as exc:
        raise ProductionQuarantineApplyError(str(exc)) from exc
    finally:
        if previous_temp_gate is None:
            os.environ.pop(TEMP_ENV_GATE, None)
        else:
            os.environ[TEMP_ENV_GATE] = previous_temp_gate

    _validate_expected_delta(
        materializer_summary=materializer_summary,
        expected_candidate_rows=expected_candidate_rows,
        expected_product_cashflow_delete_rows=expected_product_cashflow_delete_rows,
        expected_stock_ledger_delete_rows=expected_stock_ledger_delete_rows,
    )

    cash_in_after = _cash_in_count(staging_path, order_ids)
    if cash_in_after != cash_in_before:
        raise ProductionQuarantineApplyError(
            f"order-level CASH_IN preservation failed: before {cash_in_before}, after {cash_in_after}"
        )
    integrity_after = _integrity_check(staging_path)
    if integrity_after.lower() != "ok":
        raise ProductionQuarantineApplyError(f"post-write integrity_check failed on staging: {integrity_after}")

    current_sha256 = _sha256(target_db)
    if current_sha256 != pre_sha256:
        raise ProductionQuarantineApplyError(
            f"target changed before replace: expected {pre_sha256}, got {current_sha256}"
        )

    os.replace(staging_path, target_db)
    final_sha256 = _sha256(target_db)
    final_integrity = _integrity_check(target_db)
    if final_integrity.lower() != "ok":
        raise ProductionQuarantineApplyError(f"post-replace integrity_check failed: {final_integrity}")

    summary.update(
        {
            "backup_path": str(backup_path),
            "post_sha256": final_sha256,
            "integrity_check": {"before": integrity_before, "after": final_integrity},
            "cash_in_preservation": {
                "order_ids": order_ids,
                "before_count": cash_in_before,
                "after_count": cash_in_after,
                "preserved": True,
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
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--expected-pre-sha256", required=True)
    parser.add_argument("--expected-candidate-rows", type=int, required=True)
    parser.add_argument("--expected-product-cashflow-delete-rows", type=int, required=True)
    parser.add_argument("--expected-stock-ledger-delete-rows", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv or sys.argv[1:])
    try:
        summary = apply_storeb_product_identity_quarantine_production_safe(
            db_path=args.db,
            candidates_path=args.candidates,
            output_root=args.output_root,
            backup_dir=args.backup_dir,
            expected_pre_sha256=args.expected_pre_sha256,
            expected_candidate_rows=args.expected_candidate_rows,
            expected_product_cashflow_delete_rows=args.expected_product_cashflow_delete_rows,
            expected_stock_ledger_delete_rows=args.expected_stock_ledger_delete_rows,
            apply=bool(args.apply),
        )
    except ProductionQuarantineApplyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"summary_json={summary['summary_json']}")
        print(f"applied={summary['apply']['applied']}")
        print(f"backup_path={summary['backup_path']}")
        print(
            "deleted_product_cashflow_rows="
            f"{summary['materializer_summary']['apply']['deleted_product_cashflow_rows']}"
        )
        print(f"deleted_stock_ledger_rows={summary['materializer_summary']['apply']['deleted_stock_ledger_rows']}")
        print(f"cash_in_preserved={summary['cash_in_preservation']['preserved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
