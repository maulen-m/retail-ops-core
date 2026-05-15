#!/usr/bin/env python3
"""Production-safe wrapper for the inventory snapshot rebuild step.

The underlying snapshot rebuild is intentionally left unchanged. This wrapper
plans the ledger rebuild read-only, applies it to a staging copy, proves exact
row-count/total controls, then replaces the target DB only after backup, SHA,
sidecar, and integrity gates pass.
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

from core.db import DEFAULT_DB_PATH  # noqa: E402
from scripts.rebuild_snapshot import rebuild_snapshot  # noqa: E402


PRODUCTION_ENV_GATE = "ENABLE_REBUILD_SNAPSHOT_PRODUCTION_APPLY"


class ProductionSnapshotApplyError(RuntimeError):
    """Raised when the production-safe snapshot wrapper cannot prove safety."""


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
    return db_path.resolve() == DEFAULT_DB_PATH.resolve()


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(f"{db_path}-wal"), Path(f"{db_path}-shm"), Path(f"{db_path}-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise ProductionSnapshotApplyError(f"refusing file replacement while SQLite sidecars exist: {joined}")


def _copy_or_raise(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if not target.exists():
        raise ProductionSnapshotApplyError(f"required copy was not created: {target}")


def _safe_ts(generated_at: str) -> str:
    return generated_at.replace(":", "").replace("-", "").replace("+", "_").replace("T", "_")


def _backup_path_for(db_path: Path, backup_dir: Path, generated_at: str) -> Path:
    return backup_dir / f"{db_path.stem}_pre_rebuild_snapshot_{_safe_ts(generated_at)}{db_path.suffix}"


def _staging_path_for(db_path: Path, output_root: Path, generated_at: str) -> Path:
    return output_root / "staging" / f"{db_path.stem}_rebuild_snapshot_staging_{_safe_ts(generated_at)}{db_path.suffix}"


def _write_summary(output_root: Path, summary: dict[str, Any]) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "summary.json"
    summary["summary_json"] = str(summary_path)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def _snapshot_stats(db_path: Path, snapshot_date: dt.date) -> dict[str, int]:
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS rows,
                COALESCE(SUM(current_stock), 0) AS current_stock_total,
                COALESCE(SUM(inbound_stock), 0) AS inbound_stock_total
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
            """,
            (snapshot_date.isoformat(),),
        ).fetchone()
    return {
        "rows": int(row[0] if row else 0),
        "current_stock_total": int(row[1] if row else 0),
        "inbound_stock_total": int(row[2] if row else 0),
    }


def _validate_mode(mode: str) -> None:
    if mode not in {"ledger", "simulate"}:
        raise ProductionSnapshotApplyError(
            "production-safe snapshot wrapper only supports --mode ledger or --mode simulate"
        )


def _validate_expected_stats(
    *,
    label: str,
    stats: dict[str, int],
    expected_rows_created: int,
    expected_current_stock_total: int,
    expected_inbound_stock_total: int,
) -> None:
    if stats["rows"] != expected_rows_created:
        raise ProductionSnapshotApplyError(
            f"{label} rows mismatch: expected {expected_rows_created}, got {stats['rows']}"
        )
    if stats["current_stock_total"] != expected_current_stock_total:
        raise ProductionSnapshotApplyError(
            f"{label} current_stock_total mismatch: "
            f"expected {expected_current_stock_total}, got {stats['current_stock_total']}"
        )
    if stats["inbound_stock_total"] != expected_inbound_stock_total:
        raise ProductionSnapshotApplyError(
            f"{label} inbound_stock_total mismatch: "
            f"expected {expected_inbound_stock_total}, got {stats['inbound_stock_total']}"
        )


def _plan_rebuild(
    *,
    db_path: Path,
    snapshot_date: dt.date,
    store_code: str,
    mode: str,
) -> dict[str, Any]:
    result = rebuild_snapshot(
        snapshot_date=snapshot_date,
        store_code=store_code,
        mode=mode,
        compare=False,
        apply=False,
        db_path=db_path,
    )
    return {
        "rows": int(result.get("rows_created") or 0),
        "current_stock_total": int(result.get("current_stock_total") or 0),
        "inbound_stock_total": int(result.get("inbound_stock_total") or 0),
        "apply_status": str(result.get("apply_status") or "DRY_RUN"),
    }


def _plan_rebuild_on_copy(
    *,
    db_path: Path,
    snapshot_date: dt.date,
    store_code: str,
    mode: str,
    output_root: Path,
    generated_at: str,
) -> tuple[dict[str, Any], Path | None]:
    if mode == "ledger":
        return (
            _plan_rebuild(
                db_path=db_path,
                snapshot_date=snapshot_date,
                store_code=store_code,
                mode=mode,
            ),
            None,
        )

    plan_copy = output_root / "planning" / f"{db_path.stem}_rebuild_snapshot_plan_{_safe_ts(generated_at)}{db_path.suffix}"
    _copy_or_raise(db_path, plan_copy)
    plan_integrity = _integrity_check(plan_copy)
    if plan_integrity.lower() != "ok":
        raise ProductionSnapshotApplyError(f"planning copy integrity_check failed: {plan_integrity}")

    result = rebuild_snapshot(
        snapshot_date=snapshot_date,
        store_code=store_code,
        mode=mode,
        compare=False,
        apply=True,
        db_path=plan_copy,
    )
    plan_after_integrity = _integrity_check(plan_copy)
    if plan_after_integrity.lower() != "ok":
        raise ProductionSnapshotApplyError(f"planning copy post-write integrity_check failed: {plan_after_integrity}")

    return (
        {
            "rows": int(result.get("rows_created") or 0),
            "current_stock_total": int(result.get("current_stock_total") or 0),
            "inbound_stock_total": int(result.get("inbound_stock_total") or 0),
            "apply_status": str(result.get("apply_status") or "APPLIED"),
        },
        plan_copy,
    )


def apply_rebuild_snapshot_production_safe(
    *,
    db_path: Path,
    snapshot_date: dt.date,
    store_code: str,
    mode: str,
    output_root: Path,
    backup_dir: Path,
    expected_pre_sha256: str,
    expected_existing_rows: int,
    expected_rows_created: int,
    expected_current_stock_total: int,
    expected_inbound_stock_total: int,
    apply: bool = False,
) -> dict[str, Any]:
    target_db = Path(db_path).resolve()
    output = Path(output_root).resolve()
    backups = Path(backup_dir).resolve()
    generated_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")

    _validate_mode(mode)
    if not target_db.exists():
        raise ProductionSnapshotApplyError(f"db not found: {target_db}")

    pre_sha256 = _sha256(target_db)
    if pre_sha256 != expected_pre_sha256:
        raise ProductionSnapshotApplyError(
            f"pre-write SHA mismatch: expected {expected_pre_sha256}, got {pre_sha256}"
        )

    integrity_before = _integrity_check(target_db)
    if integrity_before.lower() != "ok":
        raise ProductionSnapshotApplyError(f"pre-write integrity_check failed: {integrity_before}")

    before_stats = _snapshot_stats(target_db, snapshot_date)
    if before_stats["rows"] != expected_existing_rows:
        raise ProductionSnapshotApplyError(
            f"existing_rows mismatch: expected {expected_existing_rows}, got {before_stats['rows']}"
        )

    if apply and os.environ.get(PRODUCTION_ENV_GATE) != "1":
        raise ProductionSnapshotApplyError(f"{PRODUCTION_ENV_GATE}=1 is required with --apply")

    planned_stats, plan_copy_path = _plan_rebuild_on_copy(
        db_path=target_db,
        snapshot_date=snapshot_date,
        store_code=store_code,
        mode=mode,
        output_root=output,
        generated_at=generated_at,
    )
    _validate_expected_stats(
        label="planned snapshot",
        stats=planned_stats,
        expected_rows_created=expected_rows_created,
        expected_current_stock_total=expected_current_stock_total,
        expected_inbound_stock_total=expected_inbound_stock_total,
    )

    production_target = _target_is_production(target_db)
    summary: dict[str, Any] = {
        "generated_at": generated_at,
        "db_path": str(target_db),
        "snapshot": {
            "date": snapshot_date.isoformat(),
            "store_code": store_code,
            "mode": mode,
        },
        "output_root": str(output),
        "backup_dir": str(backups),
        "backup_path": None,
        "expected": {
            "pre_sha256": expected_pre_sha256,
            "existing_rows": expected_existing_rows,
            "rows_created": expected_rows_created,
            "current_stock_total": expected_current_stock_total,
            "inbound_stock_total": expected_inbound_stock_total,
            "row_delta": expected_rows_created - expected_existing_rows,
        },
        "pre_sha256": pre_sha256,
        "post_sha256": pre_sha256,
        "row_counts": {
            "before": before_stats,
            "planned": planned_stats,
            "staging_after": None,
            "target_after": before_stats,
            "actual_row_delta": 0,
        },
        "integrity_check": {
            "target_before": integrity_before,
            "backup": None,
            "staging_before": None,
            "staging_after": None,
            "target_after": integrity_before,
        },
        "env_gate": PRODUCTION_ENV_GATE,
        "apply": {
            "requested": bool(apply),
            "applied": False,
            "target_replaced": False,
            "staging_path": None,
        },
        "rebuild_summary": {
            "dry_run": planned_stats,
            "plan_copy_path": str(plan_copy_path) if plan_copy_path else None,
            "staging_apply": None,
        },
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

    _fail_on_sqlite_sidecars(target_db)
    backup_path = _backup_path_for(target_db, backups, generated_at)
    staging_path = _staging_path_for(target_db, output, generated_at)
    _copy_or_raise(target_db, backup_path)
    _copy_or_raise(target_db, staging_path)

    backup_integrity = _integrity_check(backup_path)
    if backup_integrity.lower() != "ok":
        raise ProductionSnapshotApplyError(f"backup integrity_check failed: {backup_integrity}")
    staging_integrity_before = _integrity_check(staging_path)
    if staging_integrity_before.lower() != "ok":
        raise ProductionSnapshotApplyError(f"staging integrity_check failed before apply: {staging_integrity_before}")

    staging_result = rebuild_snapshot(
        snapshot_date=snapshot_date,
        store_code=store_code,
        mode=mode,
        compare=False,
        apply=True,
        db_path=staging_path,
    )
    staging_result_stats = {
        "rows": int(staging_result.get("rows_created") or 0),
        "current_stock_total": int(staging_result.get("current_stock_total") or 0),
        "inbound_stock_total": int(staging_result.get("inbound_stock_total") or 0),
    }
    _validate_expected_stats(
        label="staging rebuild summary",
        stats=staging_result_stats,
        expected_rows_created=expected_rows_created,
        expected_current_stock_total=expected_current_stock_total,
        expected_inbound_stock_total=expected_inbound_stock_total,
    )

    staging_after_stats = _snapshot_stats(staging_path, snapshot_date)
    _validate_expected_stats(
        label="staging snapshot table",
        stats=staging_after_stats,
        expected_rows_created=expected_rows_created,
        expected_current_stock_total=expected_current_stock_total,
        expected_inbound_stock_total=expected_inbound_stock_total,
    )

    staging_integrity_after = _integrity_check(staging_path)
    if staging_integrity_after.lower() != "ok":
        raise ProductionSnapshotApplyError(f"post-write integrity_check failed on staging: {staging_integrity_after}")

    _fail_on_sqlite_sidecars(target_db)
    current_sha256 = _sha256(target_db)
    if current_sha256 != expected_pre_sha256:
        raise ProductionSnapshotApplyError(
            f"target changed before replace: expected {expected_pre_sha256}, got {current_sha256}"
        )

    staging_sha256 = _sha256(staging_path)
    os.replace(staging_path, target_db)
    final_sha256 = _sha256(target_db)
    final_integrity = _integrity_check(target_db)
    if final_integrity.lower() != "ok":
        raise ProductionSnapshotApplyError(f"post-replace integrity_check failed: {final_integrity}")
    target_after_stats = _snapshot_stats(target_db, snapshot_date)
    _validate_expected_stats(
        label="target snapshot table",
        stats=target_after_stats,
        expected_rows_created=expected_rows_created,
        expected_current_stock_total=expected_current_stock_total,
        expected_inbound_stock_total=expected_inbound_stock_total,
    )

    summary.update(
        {
            "backup_path": str(backup_path),
            "post_sha256": final_sha256,
            "row_counts": {
                "before": before_stats,
                "planned": planned_stats,
                "staging_after": staging_after_stats,
                "target_after": target_after_stats,
                "actual_row_delta": target_after_stats["rows"] - before_stats["rows"],
            },
            "integrity_check": {
                "target_before": integrity_before,
                "backup": backup_integrity,
                "staging_before": staging_integrity_before,
                "staging_after": staging_integrity_after,
                "target_after": final_integrity,
            },
            "apply": {
                "requested": True,
                "applied": True,
                "target_replaced": True,
                "staging_path": str(staging_path),
                "staging_sha256": staging_sha256,
            },
            "rebuild_summary": {
                "dry_run": planned_stats,
                "plan_copy_path": str(plan_copy_path) if plan_copy_path else None,
                "staging_apply": staging_result,
            },
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


def _parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--date", type=_parse_date, required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--mode", choices=["ledger", "simulate"], required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--expected-pre-sha256", required=True)
    parser.add_argument("--expected-existing-rows", type=int, required=True)
    parser.add_argument("--expected-rows-created", type=int, required=True)
    parser.add_argument("--expected-current-stock-total", type=int, required=True)
    parser.add_argument("--expected-inbound-stock-total", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv or sys.argv[1:])
    try:
        summary = apply_rebuild_snapshot_production_safe(
            db_path=args.db,
            snapshot_date=args.date,
            store_code=args.store,
            mode=args.mode,
            output_root=args.output_root,
            backup_dir=args.backup_dir,
            expected_pre_sha256=args.expected_pre_sha256,
            expected_existing_rows=args.expected_existing_rows,
            expected_rows_created=args.expected_rows_created,
            expected_current_stock_total=args.expected_current_stock_total,
            expected_inbound_stock_total=args.expected_inbound_stock_total,
            apply=bool(args.apply),
        )
    except ProductionSnapshotApplyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(f"summary_json={summary['summary_json']}")
        print(f"applied={summary['apply']['applied']}")
        print(f"backup_path={summary['backup_path']}")
        print(f"rows_created={summary['expected']['rows_created']}")
        print(f"current_stock_total={summary['expected']['current_stock_total']}")
        print(f"inbound_stock_total={summary['expected']['inbound_stock_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
