#!/usr/bin/env python3
"""Dry-run or apply an API-entry formula manifest to a disposable DB copy.

The canonical production DB, the proof-bound baseline DB, and source evidence
DB are hard-refused.  Apply requires an explicit environment gate, a real
prewrite backup, exact preimages, one transaction, and full target/non-target
readback.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from scripts.build_api_order_entry_formula_promotion_manifest import (  # noqa: E402
    TARGET_FIELDS,
    _non_target_hash,
    _query_target,
    _table_counts,
    validate_promotion_manifest,
)
from scripts.build_api_order_entry_formula_provenance_sidecar import (  # noqa: E402
    _canonical_bytes,
    _text,
    sha256_file,
)


APPLY_GATE = "ENABLE_COPIED_API_ENTRY_FORMULA_REPAIR"
PRODUCTION_DB = (PROJECT_ROOT / "db" / "app.db").resolve()
RUNS_ROOT = (PROJECT_ROOT / "runs").resolve()


class ApiEntryPromotionApplyError(RuntimeError):
    """Raised when copied apply cannot prove its exact boundary."""


def _same_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return left.resolve() == right.resolve()


def _inside_runs(path: Path) -> bool:
    try:
        path.resolve().relative_to(RUNS_ROOT)
        return True
    except ValueError:
        return False


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_bytes(_canonical_bytes(payload, pretty=True))
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _sqlite_sidecars(path: Path) -> list[Path]:
    return [
        candidate
        for candidate in (
            Path(str(path) + "-wal"),
            Path(str(path) + "-shm"),
            Path(str(path) + "-journal"),
        )
        if candidate.exists()
    ]


def _integrity_path(path: Path) -> str:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
        return _text(conn.execute("PRAGMA integrity_check").fetchone()[0])


def _post_commit_barrier(path: Path) -> None:
    if _integrity_path(path).lower() != "ok":
        raise ApiEntryPromotionApplyError("post-commit integrity failed")


def _restore_verified_backup(
    *, target: Path, backup: Path, expected_sha256: str
) -> str:
    sidecars = _sqlite_sidecars(target)
    if sidecars:
        raise ApiEntryPromotionApplyError(
            "cannot restore copied DB while SQLite sidecars exist: "
            + ", ".join(str(path) for path in sidecars)
        )
    shutil.copy2(backup, target)
    restored_sha = sha256_file(target)
    if restored_sha != expected_sha256 or _integrity_path(target).lower() != "ok":
        raise ApiEntryPromotionApplyError(
            "formula promotion restore did not reproduce exact copied preimage"
        )
    return restored_sha


def _verify_idempotent_replay_in_transaction(
    conn: sqlite3.Connection,
    *,
    targets: list[dict[str, Any]],
    target_ids: set[int],
    counts_before: dict[str, int],
    non_target_before: str,
) -> None:
    for target in targets:
        after = target["after"]
        cursor = conn.execute(
            """
            UPDATE sales_fact_v2
            SET delivery_fee=?, net_rev=?, profit=?
            WHERE sale_id=?
            """,
            (
                after.get("delivery_fee"),
                after.get("net_rev"),
                after.get("profit"),
                int(target["sale_id"]),
            ),
        )
        if cursor.rowcount != 1:
            raise ApiEntryPromotionApplyError(
                f"idempotent replay count mismatch: sale_id={target['sale_id']}"
            )
    if _table_counts(conn) != counts_before:
        raise ApiEntryPromotionApplyError("table counts changed during idempotent replay")
    if _non_target_hash(conn, target_ids) != non_target_before:
        raise ApiEntryPromotionApplyError("non-target rows changed during idempotent replay")
    for target in targets:
        if _query_target(conn, int(target["sale_id"])) != target.get("after"):
            raise ApiEntryPromotionApplyError(
                f"idempotent replay mismatch: sale_id={target['sale_id']}"
            )


def _preflight_output_path(path: Path, protected: list[Path]) -> None:
    path = path.resolve()
    if not _inside_runs(path):
        raise ApiEntryPromotionApplyError("report path must be inside repo runs/")
    if path.exists():
        raise ApiEntryPromotionApplyError("report path already exists")
    if any(_same_file(path, item) for item in protected):
        raise ApiEntryPromotionApplyError("report path collides with a protected input")


def apply_manifest(
    *,
    manifest_path: Path,
    db_path: Path,
    expected_manifest_sha256: str,
    expected_db_sha256: str,
    apply: bool,
    backup_dir: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    db_path = db_path.resolve()
    if not db_path.exists():
        raise ApiEntryPromotionApplyError(f"copied target DB does not exist: {db_path}")
    if not _inside_runs(db_path):
        raise ApiEntryPromotionApplyError("copied target DB must be inside repo runs/")
    validation = validate_promotion_manifest(manifest_path)
    if not validation.get("ok"):
        raise ApiEntryPromotionApplyError(
            f"promotion manifest validation failed: {validation.get('errors')}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _text(manifest.get("manifest_sha256")) != _text(expected_manifest_sha256):
        raise ApiEntryPromotionApplyError("promotion manifest SHA-256 mismatch")
    if manifest.get("copied_apply_ready") is not True:
        raise ApiEntryPromotionApplyError("promotion manifest is not copied-apply ready")
    if manifest.get("provisional_economic_date") is True:
        raise ApiEntryPromotionApplyError("provisional economic date cannot be promoted")
    baseline_db = Path(_text(manifest.get("copied_db_path"))).resolve()
    source_manifest_path = Path(_text(manifest.get("source_sidecar_manifest_path"))).resolve()
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_db = Path(_text(source_manifest.get("source_db_path"))).resolve()
    protected = [manifest_path, baseline_db, source_manifest_path, source_db, db_path, PRODUCTION_DB]
    if _same_file(db_path, PRODUCTION_DB):
        raise ApiEntryPromotionApplyError("canonical production db/app.db is hard-refused")
    if _same_file(db_path, baseline_db):
        raise ApiEntryPromotionApplyError("proof-bound baseline DB is read-only and hard-refused")
    if _same_file(db_path, source_db):
        raise ApiEntryPromotionApplyError("source evidence DB is hard-refused")
    if report_path is not None:
        _preflight_output_path(report_path, protected)
    if apply:
        if os.environ.get(APPLY_GATE) != "1":
            raise ApiEntryPromotionApplyError(f"apply requires {APPLY_GATE}=1")
        if backup_dir is None:
            raise ApiEntryPromotionApplyError("apply requires a backup directory")
        backup_dir = backup_dir.resolve()
        if not _inside_runs(backup_dir):
            raise ApiEntryPromotionApplyError("backup directory must be inside repo runs/")
    pre_sha = sha256_file(db_path)
    if pre_sha != _text(expected_db_sha256) or pre_sha != _text(manifest.get("copied_db_sha256")):
        raise ApiEntryPromotionApplyError("copied target DB SHA-256 mismatch")
    targets = list(manifest.get("targets") or [])
    if len(targets) != int(manifest.get("target_count") or 0) or not targets:
        raise ApiEntryPromotionApplyError("target count is empty or mismatched")
    target_ids = {int(target["sale_id"]) for target in targets}
    if len(target_ids) != len(targets):
        raise ApiEntryPromotionApplyError("duplicate target sale_id")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if _text(conn.execute("PRAGMA integrity_check").fetchone()[0]).lower() != "ok":
            raise ApiEntryPromotionApplyError("copied target DB integrity failed")
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='sales_fact_v2'"
        ).fetchall()
        if triggers:
            raise ApiEntryPromotionApplyError("sales_fact_v2 triggers are not permitted")
        counts_before = _table_counts(conn)
        non_target_before = _non_target_hash(conn, target_ids)
        if counts_before != manifest.get("table_counts_before"):
            raise ApiEntryPromotionApplyError("table-count baseline mismatch")
        if non_target_before != manifest.get("non_target_sales_fact_v2_sha256"):
            raise ApiEntryPromotionApplyError("non-target baseline hash mismatch")
        for target in targets:
            actual = _query_target(conn, int(target["sale_id"]))
            if actual != target.get("before"):
                raise ApiEntryPromotionApplyError(
                    f"target preimage mismatch: sale_id={target['sale_id']}"
                )

    backup_path: Path | None = None
    rollback_path: Path | None = None
    rollback: dict[str, Any] | None = None
    if apply:
        assert backup_dir is not None
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = backup_dir / f"app.pre_api_formula_{pre_sha[:12]}_{stamp}.db"
        if backup_path.exists():
            raise ApiEntryPromotionApplyError("backup path collision")
        shutil.copy2(db_path, backup_path)
        if sha256_file(backup_path) != pre_sha:
            raise ApiEntryPromotionApplyError("backup SHA-256 mismatch")
        with sqlite3.connect(backup_path) as backup_conn:
            if _text(backup_conn.execute("PRAGMA integrity_check").fetchone()[0]).lower() != "ok":
                raise ApiEntryPromotionApplyError("backup integrity failed")
        rollback_path = backup_dir / f"ROLLBACK_{stamp}.json"
        if rollback_path.exists():
            raise ApiEntryPromotionApplyError("rollback path collision")
        rollback = {
            "schema": "api_entry_formula_copied_rollback_v1",
            "status": "PREPARED_BEFORE_TRANSACTION",
            "manifest_path": str(manifest_path),
            "manifest_sha256": _text(manifest.get("manifest_sha256")),
            "db_path": str(db_path),
            "db_pre_sha256": pre_sha,
            "db_post_sha256": None,
            "backup_path": str(backup_path),
            "backup_sha256": pre_sha,
            "restore_verified": False,
            "rollback_command": f"cp -p {json.dumps(str(backup_path))} {json.dumps(str(db_path))}",
        }
        _write_json_atomic(rollback_path, rollback)
        conn = sqlite3.connect(db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        transaction_error: BaseException | None = None
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for target in targets:
                    actual = _query_target(conn, int(target["sale_id"]))
                    if actual != target.get("before"):
                        raise ApiEntryPromotionApplyError(
                            f"in-transaction preimage mismatch: sale_id={target['sale_id']}"
                        )
                for target in targets:
                    after = target["after"]
                    cursor = conn.execute(
                        """
                        UPDATE sales_fact_v2
                        SET delivery_fee=?, net_rev=?, profit=?
                        WHERE sale_id=?
                        """,
                        (
                            after.get("delivery_fee"),
                            after.get("net_rev"),
                            after.get("profit"),
                            int(target["sale_id"]),
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ApiEntryPromotionApplyError(
                            f"target update count mismatch: sale_id={target['sale_id']}"
                        )
                if _table_counts(conn) != counts_before:
                    raise ApiEntryPromotionApplyError("table counts changed in transaction")
                if _non_target_hash(conn, target_ids) != non_target_before:
                    raise ApiEntryPromotionApplyError("non-target rows changed in transaction")
                for target in targets:
                    actual = _query_target(conn, int(target["sale_id"]))
                    if actual != target.get("after"):
                        raise ApiEntryPromotionApplyError(
                            f"target postimage mismatch: sale_id={target['sale_id']}"
                        )
                _verify_idempotent_replay_in_transaction(
                    conn,
                    targets=targets,
                    target_ids=target_ids,
                    counts_before=counts_before,
                    non_target_before=non_target_before,
                )
                conn.execute("COMMIT")
            except BaseException as exc:
                transaction_error = exc
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
        finally:
            conn.close()
        if transaction_error is not None:
            restored_sha = _restore_verified_backup(
                target=db_path,
                backup=backup_path,
                expected_sha256=pre_sha,
            )
            rollback.update(
                {
                    "status": "TRANSACTION_ROLLED_BACK_AND_PREIMAGE_RESTORED",
                    "failure": f"{type(transaction_error).__name__}: {transaction_error}",
                    "restore_verified": True,
                    "restored_sha256": restored_sha,
                }
            )
            _write_json_atomic(rollback_path, rollback)
            raise transaction_error

    try:
        if apply:
            _post_commit_barrier(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            integrity_after = _text(conn.execute("PRAGMA integrity_check").fetchone()[0])
            counts_after = _table_counts(conn)
            non_target_after = _non_target_hash(conn, target_ids)
            target_mismatches = []
            for target in targets:
                expected = target.get("after") if apply else target.get("before")
                if _query_target(conn, int(target["sale_id"])) != expected:
                    target_mismatches.append(int(target["sale_id"]))
        post_sha = sha256_file(db_path)
        if integrity_after.lower() != "ok":
            raise ApiEntryPromotionApplyError("post-run integrity failed")
        if counts_after != counts_before:
            raise ApiEntryPromotionApplyError("post-run table counts changed")
        if non_target_after != non_target_before:
            raise ApiEntryPromotionApplyError("post-run non-target hash changed")
        if target_mismatches:
            raise ApiEntryPromotionApplyError(
                f"post-run target mismatch count={len(target_mismatches)}"
            )
        if not apply and post_sha != pre_sha:
            raise ApiEntryPromotionApplyError("dry-run changed copied target DB bytes")
        report = {
            "schema": "api_order_entry_formula_copied_apply_report_v1",
            "mode": "APPLY" if apply else "DRY_RUN",
            "status": "PASS",
            "manifest_path": str(manifest_path),
            "manifest_sha256": _text(manifest.get("manifest_sha256")),
            "db_path": str(db_path),
            "db_pre_sha256": pre_sha,
            "db_post_sha256": post_sha,
            "backup_path": str(backup_path) if backup_path else None,
            "backup_sha256": sha256_file(backup_path) if backup_path else None,
            "rollback_artifact_path": str(rollback_path) if rollback_path else None,
            "rollback_command": f"cp -p {json.dumps(str(backup_path))} {json.dumps(str(db_path))}" if backup_path else None,
            "target_count": len(targets),
            "target_sale_ids": sorted(target_ids),
            "changed_columns": ["delivery_fee", "net_rev", "profit"] if apply else [],
            "target_readback_mismatch_count": 0,
            "non_target_sales_fact_v2_sha256_before": non_target_before,
            "non_target_sales_fact_v2_sha256_after": non_target_after,
            "table_counts_unchanged": counts_before == counts_after,
            "db_integrity": integrity_after,
            "idempotent_replay": True if apply else None,
            "production_write_performed": False,
            "cash_or_stock_write_performed": False,
        }
        if apply:
            assert rollback is not None and rollback_path is not None
            rollback.update(
                {
                    "status": "READY",
                    "db_post_sha256": post_sha,
                    "restore_verified": False,
                }
            )
            _write_json_atomic(rollback_path, rollback)
        if report_path is not None:
            _write_json_atomic(report_path.resolve(), report)
        return report
    except BaseException as exc:
        if not apply:
            raise
        assert backup_path is not None and rollback is not None and rollback_path is not None
        try:
            restored_sha = _restore_verified_backup(
                target=db_path,
                backup=backup_path,
                expected_sha256=pre_sha,
            )
        except BaseException as restore_exc:
            rollback.update(
                {
                    "status": "RESTORE_FAILED_AFTER_POST_COMMIT_FAILURE",
                    "failure": f"{type(exc).__name__}: {exc}",
                    "restore_failure": f"{type(restore_exc).__name__}: {restore_exc}",
                }
            )
            try:
                _write_json_atomic(rollback_path, rollback)
            except Exception:
                pass
            raise ApiEntryPromotionApplyError(
                "AMBIGUOUS: formula promotion post-commit failure and verified restore failed; "
                f"use prepared backup {backup_path}"
            ) from restore_exc
        rollback.update(
            {
                "status": "RESTORED_AFTER_POST_COMMIT_FAILURE",
                "failure": f"{type(exc).__name__}: {exc}",
                "db_post_sha256": None,
                "restore_verified": True,
                "restored_sha256": restored_sha,
            }
        )
        _write_json_atomic(rollback_path, rollback)
        if report_path is not None:
            report_path.resolve().unlink(missing_ok=True)
        raise ApiEntryPromotionApplyError(
            "formula promotion post-commit verification or evidence finalization failed; "
            "copied DB restored to exact preimage"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-db-sha256", required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        report = apply_manifest(
            manifest_path=args.manifest,
            db_path=args.db,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_db_sha256=args.expected_db_sha256,
            apply=args.apply,
            backup_dir=args.backup_dir,
            report_path=args.report,
        )
    except (OSError, ValueError, sqlite3.Error, ApiEntryPromotionApplyError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
