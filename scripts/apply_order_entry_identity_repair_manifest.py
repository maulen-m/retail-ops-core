#!/usr/bin/env python3
"""Apply an exact order-entry identity manifest to a disposable copied DB only.

This writer deliberately refuses the production DB. It does not modify cash,
stock, duplicate-snapshot rows, or external systems. Production application
requires a different, later owner-approved wrapper after all manifest blockers
are resolved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any

try:
    from scripts.build_order_entry_identity_repair_manifest import (
        PROJECTION_ID_COLUMNS,
        REQUIRED_LINE_IDENTITY_COLUMNS,
        _canonical_bytes,
        _safe_projection_row,
        _sha256_bytes,
    )
except ModuleNotFoundError:  # direct `python scripts/...` execution
    from build_order_entry_identity_repair_manifest import (
        PROJECTION_ID_COLUMNS,
        REQUIRED_LINE_IDENTITY_COLUMNS,
        _canonical_bytes,
        _safe_projection_row,
        _sha256_bytes,
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_DB = (PROJECT_ROOT / "db" / "app.db").resolve()
COPIED_APPLY_ENV_GATE = "ENABLE_COPIED_ORDER_ENTRY_IDENTITY_REPAIR"


class OrderEntryIdentityApplyError(RuntimeError):
    """Raised when copied-only apply preconditions or readback fail."""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _integrity(path: Path) -> str:
    conn = _connect(path, readonly=True)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    return str(row[0] if row else "missing")


def _backup(source: Path, target: Path) -> None:
    if target.exists():
        raise OrderEntryIdentityApplyError(f"backup target already exists: {target}")
    sidecars = [
        candidate
        for candidate in (
            Path(str(source) + "-wal"),
            Path(str(source) + "-shm"),
            Path(str(source) + "-journal"),
        )
        if candidate.exists()
    ]
    if sidecars:
        raise OrderEntryIdentityApplyError(
            "refusing byte backup while SQLite sidecars exist: "
            + ", ".join(str(path) for path in sidecars)
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if _sha256_file(target) != _sha256_file(source):
        raise OrderEntryIdentityApplyError(f"backup SHA-256 mismatch: {target}")
    if _integrity(target).lower() != "ok":
        raise OrderEntryIdentityApplyError(f"backup integrity_check failed: {target}")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _post_commit_barrier(path: Path) -> None:
    if _integrity(path).lower() != "ok":
        raise OrderEntryIdentityApplyError(
            "copied DB post-commit integrity_check failed"
        )


def _restore_verified_backup(
    *, target: Path, backup: Path, expected_sha256: str
) -> str:
    shutil.copy2(backup, target)
    restored_sha = _sha256_file(target)
    if restored_sha != expected_sha256 or _integrity(target).lower() != "ok":
        raise OrderEntryIdentityApplyError(
            "identity apply restore did not reproduce exact copied preimage"
        )
    return restored_sha


def _manifest(path: Path, expected_internal_sha256: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OrderEntryIdentityApplyError(f"manifest unreadable: {path}") from exc
    actual = str(payload.get("manifest_sha256") or "")
    canonical = dict(payload)
    canonical.pop("manifest_sha256", None)
    recomputed = _sha256_bytes(_canonical_bytes(canonical))
    if actual != recomputed:
        raise OrderEntryIdentityApplyError(
            f"manifest internal SHA mismatch: stored {actual}, recomputed {recomputed}"
        )
    if actual != expected_internal_sha256:
        raise OrderEntryIdentityApplyError(
            f"manifest expected SHA mismatch: expected {expected_internal_sha256}, got {actual}"
        )
    if payload.get("production_apply_authorized") is not False:
        raise OrderEntryIdentityApplyError(
            "manifest must explicitly set production_apply_authorized=false"
        )
    return payload


def _refuse_production_or_hardlink(path: Path) -> None:
    resolved = path.resolve()
    if resolved == PRODUCTION_DB:
        raise OrderEntryIdentityApplyError("refusing production DB path")
    if PRODUCTION_DB.exists() and path.exists() and os.path.samefile(path, PRODUCTION_DB):
        raise OrderEntryIdentityApplyError("refusing production DB hard-link/alias")
    try:
        resolved.relative_to((PROJECT_ROOT / "runs").resolve())
    except ValueError as exc:
        if "PYTEST_CURRENT_TEST" not in os.environ:
            raise OrderEntryIdentityApplyError(
                "copied apply target must be under the repo runs directory"
            ) from exc


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')]


def _logical_hash(
    conn: sqlite3.Connection,
    *,
    table: str,
    order_by: str,
    exclude_order_id: str | None = None,
) -> str:
    columns = _columns(conn, table)
    select = ",".join(f'"{column}"' for column in columns)
    sql = f'SELECT {select} FROM "{table}"'
    params: tuple[Any, ...] = ()
    if exclude_order_id is not None and "order_id" in columns:
        sql += " WHERE CAST(order_id AS TEXT)<>? OR order_id IS NULL"
        params = (exclude_order_id,)
    sql += f' ORDER BY "{order_by}"'
    h = hashlib.sha256()
    for row in conn.execute(sql, params):
        h.update(_canonical_bytes(list(row)))
        h.update(b"\n")
    return h.hexdigest()


def _validate_projection_schema(conn: sqlite3.Connection) -> None:
    for table in PROJECTION_ID_COLUMNS:
        missing = REQUIRED_LINE_IDENTITY_COLUMNS - set(_columns(conn, table))
        if missing:
            raise OrderEntryIdentityApplyError(
                f"migration 031 columns missing from {table}: {sorted(missing)}"
            )


def _row_for_patch(conn: sqlite3.Connection, patch: dict[str, Any]) -> sqlite3.Row:
    table = str(patch["table"])
    id_column = str(patch["id_column"])
    if PROJECTION_ID_COLUMNS.get(table) != id_column:
        raise OrderEntryIdentityApplyError(f"unexpected ID column for {table}: {id_column}")
    row = conn.execute(
        f'SELECT * FROM "{table}" WHERE "{id_column}"=?',
        (patch["row_id"],),
    ).fetchone()
    if row is None:
        raise OrderEntryIdentityApplyError(
            f"target row missing: {table}.{id_column}={patch['row_id']}"
        )
    return row


def _verify_before(conn: sqlite3.Connection, patch: dict[str, Any]) -> None:
    table = str(patch["table"])
    current = _safe_projection_row(table, _row_for_patch(conn, patch))
    expected = dict(patch["before"])
    if current.get("safe_row_sha256") != expected.get("safe_row_sha256"):
        raise OrderEntryIdentityApplyError(
            f"before-row hash mismatch: {table}.{patch['id_column']}={patch['row_id']}"
        )
    for key, value in expected.items():
        if key == "safe_row_sha256":
            continue
        if current.get(key) != value:
            raise OrderEntryIdentityApplyError(
                f"before-row field mismatch: {table}.{patch['row_id']}.{key}"
            )


def _apply_patch(conn: sqlite3.Connection, patch: dict[str, Any]) -> int:
    table = str(patch["table"])
    id_column = str(patch["id_column"])
    after = dict(patch["after"])
    columns = set(_columns(conn, table))
    missing = sorted(set(after) - columns)
    if missing:
        raise OrderEntryIdentityApplyError(
            f"target columns missing from {table}: {missing}"
        )
    assignments = ", ".join(f'"{column}"=?' for column in after)
    values = [after[column] for column in after]
    cur = conn.execute(
        f'UPDATE "{table}" SET {assignments} WHERE "{id_column}"=?',
        (*values, patch["row_id"]),
    )
    return int(cur.rowcount or 0)


def _verify_after(conn: sqlite3.Connection, patch: dict[str, Any]) -> None:
    row = _row_for_patch(conn, patch)
    for key, value in dict(patch["after"]).items():
        if row[key] != value:
            raise OrderEntryIdentityApplyError(
                f"after-row mismatch: {patch['table']}.{patch['row_id']}.{key}"
            )


def _entry_readback(conn: sqlite3.Connection, manifest: dict[str, Any]) -> None:
    expected = [str(row["entry_id"]) for row in manifest["entries"]]
    order_id = str(manifest["order_id"])
    for table in PROJECTION_ID_COLUMNS:
        rows = conn.execute(
            f"""
            SELECT source_entry_id, COUNT(*)
            FROM "{table}"
            WHERE CAST(order_id AS TEXT)=?
              AND TRIM(COALESCE(source_entry_id,''))<>''
            GROUP BY source_entry_id
            ORDER BY source_entry_id
            """,
            (order_id,),
        ).fetchall()
        if [(str(row[0]), int(row[1])) for row in rows] != [
            (entry_id, 1) for entry_id in expected
        ]:
            raise OrderEntryIdentityApplyError(
                f"entry readback mismatch for {table}: {[(row[0], row[1]) for row in rows]}"
            )


def apply_manifest_to_copied_db(
    *,
    copied_db_path: Path,
    manifest_path: Path,
    expected_manifest_sha256: str,
    expected_copied_pre_sha256: str,
    backup_dir: Path,
    report_path: Path,
    apply: bool,
) -> dict[str, Any]:
    copied_db_path = copied_db_path.resolve()
    _refuse_production_or_hardlink(copied_db_path)
    if not copied_db_path.is_file():
        raise OrderEntryIdentityApplyError(f"copied DB missing: {copied_db_path}")
    if report_path.exists():
        raise OrderEntryIdentityApplyError(f"report path already exists: {report_path}")
    manifest = _manifest(manifest_path.resolve(), expected_manifest_sha256)
    pre_sha = _sha256_file(copied_db_path)
    if pre_sha != expected_copied_pre_sha256:
        raise OrderEntryIdentityApplyError(
            f"copied DB pre-SHA mismatch: expected {expected_copied_pre_sha256}, got {pre_sha}"
        )
    if _integrity(copied_db_path).lower() != "ok":
        raise OrderEntryIdentityApplyError("copied DB preimage integrity_check failed")
    if apply and os.environ.get(COPIED_APPLY_ENV_GATE) != "1":
        raise OrderEntryIdentityApplyError(
            f"{COPIED_APPLY_ENV_GATE}=1 is required for copied apply"
        )

    conn = _connect(copied_db_path)
    order_id = str(manifest["order_id"])
    patches = [
        patch
        for table in ("fact_sales", "sales_fact_v2", "fact_orders_kaspi")
        for patch in manifest["projection_patches"][table]
    ]
    try:
        _validate_projection_schema(conn)
        for patch in patches:
            _verify_before(conn, patch)
        pre_non_target = {
            table: _logical_hash(
                conn,
                table=table,
                order_by=id_column,
                exclude_order_id=order_id,
            )
            for table, id_column in PROJECTION_ID_COLUMNS.items()
        }
        cash_pre = _logical_hash(
            conn,
            table="fact_cashflow_events",
            order_by="id",
        )
    finally:
        conn.close()

    backup_path: Path | None = None
    rollback_path: Path | None = None
    rollback: dict[str, Any] | None = None
    rows_updated = 0
    if apply:
        backup_path = backup_dir.resolve() / (
            f"{copied_db_path.stem}.before_identity_patch_{pre_sha[:12]}.db"
        )
        _backup(copied_db_path, backup_path)
        rollback_path = backup_dir.resolve() / (
            f"ROLLBACK_ORDER_ENTRY_IDENTITY_{pre_sha[:12]}.json"
        )
        if rollback_path.exists():
            raise OrderEntryIdentityApplyError(
                f"rollback path already exists: {rollback_path}"
            )
        rollback = {
            "operation": "RESTORE_PRE_IDENTITY_COPIED_DB",
            "status": "PREPARED_BEFORE_TRANSACTION",
            "target_path": str(copied_db_path),
            "target_pre_sha256": pre_sha,
            "target_post_sha256": None,
            "backup_path": str(backup_path),
            "backup_sha256": pre_sha,
            "restore_verified": False,
            "command": f"cp -p {json.dumps(str(backup_path))} {json.dumps(str(copied_db_path))}",
        }
        _write_json_atomic(rollback_path, rollback)
        conn = _connect(copied_db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            for patch in patches:
                _verify_before(conn, patch)
                rows_updated += _apply_patch(conn, patch)
            if rows_updated != len(patches):
                raise OrderEntryIdentityApplyError(
                    f"row update count mismatch: expected {len(patches)}, got {rows_updated}"
                )
            for patch in patches:
                _verify_after(conn, patch)
            _entry_readback(conn, manifest)
            conn.commit()
        except BaseException as exc:
            conn.rollback()
            rollback.update(
                {
                    "status": "TRANSACTION_ROLLED_BACK",
                    "failure": f"{type(exc).__name__}: {exc}",
                    "restore_verified": _sha256_file(copied_db_path) == pre_sha,
                }
            )
            _write_json_atomic(rollback_path, rollback)
            raise
        finally:
            conn.close()

    try:
        if apply:
            _post_commit_barrier(copied_db_path)
        conn = _connect(copied_db_path, readonly=True)
        try:
            post_non_target = {
                table: _logical_hash(
                    conn,
                    table=table,
                    order_by=id_column,
                    exclude_order_id=order_id,
                )
                for table, id_column in PROJECTION_ID_COLUMNS.items()
            }
            cash_post = _logical_hash(
                conn,
                table="fact_cashflow_events",
                order_by="id",
            )
        finally:
            conn.close()
        integrity = _integrity(copied_db_path)
        post_sha = _sha256_file(copied_db_path)
        non_target_unchanged = pre_non_target == post_non_target
        cash_unchanged = cash_pre == cash_post
        if not non_target_unchanged:
            raise OrderEntryIdentityApplyError("non-target projection hashes changed")
        if not cash_unchanged:
            raise OrderEntryIdentityApplyError("cashflow table changed")
        if integrity.lower() != "ok":
            raise OrderEntryIdentityApplyError(
                f"copied DB postimage integrity_check failed: {integrity}"
            )

        source_db = Path(str(manifest["source_db"]["path"])).resolve()
        source_current_sha = _sha256_file(source_db) if source_db.is_file() else None
        report = {
            "status": "APPLIED_TO_COPIED_DB_ONLY" if apply else "VALIDATED_NO_WRITE",
            "copied_db_path": str(copied_db_path),
            "manifest_path": str(manifest_path.resolve()),
            "manifest_internal_sha256": manifest["manifest_sha256"],
            "source_manifest_production_apply_authorized": manifest["production_apply_authorized"],
            "copied_db_pre_sha256": pre_sha,
            "copied_db_post_sha256": post_sha,
            "backup_path": str(backup_path) if backup_path else None,
            "backup_sha256": pre_sha if backup_path else None,
            "rollback_path": str(rollback_path) if rollback_path else None,
            "rows_expected": len(patches),
            "rows_updated": rows_updated,
            "non_target_projection_hashes_pre": pre_non_target,
            "non_target_projection_hashes_post": post_non_target,
            "non_target_projection_hashes_unchanged": non_target_unchanged,
            "cashflow_table_hash_pre": cash_pre,
            "cashflow_table_hash_post": cash_post,
            "cashflow_table_hash_unchanged": cash_unchanged,
            "integrity_check": integrity,
            "manifest_source_db_sha256": manifest["source_db"]["sha256"],
            "manifest_source_db_current_sha256": source_current_sha,
            "manifest_source_db_unchanged": (
                source_current_sha == manifest["source_db"]["sha256"]
                if source_current_sha is not None and source_db != copied_db_path
                else None
            ),
            "production_write_performed": False,
            "cash_or_stock_write_performed": False,
        }
        if apply:
            rollback.update(
                {
                    "status": "READY",
                    "target_post_sha256": post_sha,
                    "restore_verified": False,
                }
            )
            _write_json_atomic(rollback_path, rollback)
        _write_json_atomic(report_path, report)
        return report
    except BaseException as exc:
        if not apply:
            raise
        try:
            restored_sha = _restore_verified_backup(
                target=copied_db_path,
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
            raise OrderEntryIdentityApplyError(
                "AMBIGUOUS: identity post-commit failure and verified restore failed; "
                f"use prepared backup {backup_path}"
            ) from restore_exc
        rollback.update(
            {
                "status": "RESTORED_AFTER_POST_COMMIT_FAILURE",
                "failure": f"{type(exc).__name__}: {exc}",
                "target_post_sha256": None,
                "restore_verified": True,
                "restored_sha256": restored_sha,
            }
        )
        _write_json_atomic(rollback_path, rollback)
        report_path.unlink(missing_ok=True)
        raise OrderEntryIdentityApplyError(
            "identity post-commit verification or evidence finalization failed; "
            "copied DB restored to exact preimage"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copied-db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-copied-pre-sha256", required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply-to-copy", action="store_true")
    args = parser.parse_args()

    report = apply_manifest_to_copied_db(
        copied_db_path=args.copied_db,
        manifest_path=args.manifest,
        expected_manifest_sha256=args.expected_manifest_sha256,
        expected_copied_pre_sha256=args.expected_copied_pre_sha256,
        backup_dir=args.backup_dir,
        report_path=args.report,
        apply=args.apply_to_copy,
    )
    print(f"status={report['status']}")
    print(f"rows_updated={report['rows_updated']}")
    print(f"copied_db_post_sha256={report['copied_db_post_sha256']}")
    print(f"backup_path={report['backup_path']}")
    print(f"integrity_check={report['integrity_check']}")
    print(f"non_target_projection_hashes_unchanged={str(report['non_target_projection_hashes_unchanged']).lower()}")
    print(f"cashflow_table_hash_unchanged={str(report['cashflow_table_hash_unchanged']).lower()}")
    print("production_write_performed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
