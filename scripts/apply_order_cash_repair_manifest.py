#!/usr/bin/env python3
"""Dry-run or apply a manifest-bound append-only cash repair to a copied DB."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_order_cash_repair_manifest import (  # noqa: E402
    OrderCashRepairManifestError,
    build_manifest,
)
from scripts.build_sales_publication_binding_manifest import (  # noqa: E402
    canonical_sha256,
    sha256_file,
)
from scripts.validate_sales_publication_binding import validate as validate_binding  # noqa: E402


WRITE_ENV_GATE = "ENABLE_COPIED_ORDER_CASH_REPAIR_WRITE"
PRODUCTION_DB = (PROJECT_ROOT / "db" / "app.db").resolve()


class OrderCashRepairApplyError(RuntimeError):
    pass


def _sidecars(path: Path) -> list[Path]:
    return [
        candidate
        for candidate in (
            Path(str(path) + "-wal"),
            Path(str(path) + "-shm"),
            Path(str(path) + "-journal"),
        )
        if candidate.exists()
    ]


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise OrderCashRepairApplyError("manifest must be a JSON object")
    expected = str(payload.get("manifest_sha256") or "")
    body = dict(payload)
    body.pop("manifest_sha256", None)
    observed = canonical_sha256(body)
    if not expected or expected != observed:
        raise OrderCashRepairApplyError(
            f"manifest internal hash mismatch: expected {expected or 'missing'}, observed {observed}"
        )
    return payload


def _assert_copied_target(path: Path) -> None:
    resolved = path.resolve()
    if resolved == PRODUCTION_DB or (PRODUCTION_DB.exists() and os.path.samefile(resolved, PRODUCTION_DB)):
        raise OrderCashRepairApplyError("refusing canonical production DB or alias")
    if "/runs/tmux_orchestration/" not in str(resolved):
        raise OrderCashRepairApplyError("copied apply target must be inside runs/tmux_orchestration")
    sidecars = _sidecars(resolved)
    if sidecars:
        raise OrderCashRepairApplyError(
            "refusing copied apply while SQLite sidecars exist: " + ", ".join(map(str, sidecars))
        )


def _integrity(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


def _post_commit_barrier(path: Path) -> None:
    if _integrity(path).lower() != "ok":
        raise OrderCashRepairApplyError("post-commit integrity_check failed")


def _restore_verified_backup(
    *, target: Path, backup: Path, expected_sha256: str
) -> str:
    sidecars = _sidecars(target)
    if sidecars:
        raise OrderCashRepairApplyError(
            "cannot restore copied DB while SQLite sidecars exist: "
            + ", ".join(str(path) for path in sidecars)
        )
    shutil.copy2(backup, target)
    restored_sha = sha256_file(target)
    if restored_sha != expected_sha256 or _integrity(target).lower() != "ok":
        raise OrderCashRepairApplyError(
            "cash repair restore did not reproduce exact copied preimage"
        )
    return restored_sha


def _logical_hash(conn: sqlite3.Connection, table: str) -> str:
    columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]
    rows = [dict(zip(columns, row)) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
    return canonical_sha256(sorted(rows, key=canonical_sha256))


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def _expected_events(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [item["event"] for item in manifest["reversals"]] + [
        item["event"] for item in manifest["replacements"]
    ]


def _event_matches(row: sqlite3.Row, expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if row[key] != value:
            return False
    return True


def _exact_applied_state_conn(
    conn: sqlite3.Connection,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    expected_events = _expected_events(manifest)
    hashes = [event["event_hash"] for event in expected_events]
    rows = conn.execute(
        f"SELECT * FROM fact_cashflow_events WHERE event_hash IN ({','.join('?' for _ in hashes)}) ORDER BY event_hash",
        hashes,
    ).fetchall()
    if not rows:
        return None
    if len(rows) != len(expected_events):
        raise OrderCashRepairApplyError("partial applied cash repair event set")
    by_hash = {str(row["event_hash"]): row for row in rows}
    for expected in expected_events:
        row = by_hash.get(str(expected["event_hash"]))
        if row is None or not _event_matches(row, expected):
            raise OrderCashRepairApplyError(
                f"cash repair postimage drift: {expected['event_hash']}"
            )
    return {
        "event_count": len(rows),
        "event_hashes": sorted(hashes),
        "cash_table_logical_sha256": _logical_hash(conn, "fact_cashflow_events"),
    }


def _exact_applied_state(db_path: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return _exact_applied_state_conn(conn, manifest)
    finally:
        conn.close()


def _validate_external(manifest: dict[str, Any]) -> None:
    path = Path(str(manifest["publication_manifest_path"]))
    if not path.is_file() or sha256_file(path) != str(manifest["publication_manifest_file_sha256"]):
        raise OrderCashRepairApplyError("publication binding manifest file drift")
    binding = validate_binding(db_path=Path(manifest["db_path"]), manifest_path=path)
    if binding.get("status") != "PASS" or binding.get("binding_id") != manifest["publication_binding_id"]:
        raise OrderCashRepairApplyError("publication binding is no longer valid")


def _insert_events(conn: sqlite3.Connection, events: list[dict[str, Any]]) -> None:
    columns = [
        "event_date",
        "event_ts",
        "event_type",
        "account",
        "amount_kzt",
        "store_code",
        "sku_key",
        "sku_id",
        "ref_type",
        "ref_id",
        "notes",
        "source",
        "run_id",
        "event_hash",
    ]
    for event in events:
        conn.execute(
            f"INSERT INTO fact_cashflow_events ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [event.get(column) for column in columns],
        )


def apply_manifest(
    *,
    db_path: Path,
    manifest_path: Path,
    output_path: Path,
    backup_dir: Path | None,
    apply: bool,
    expected_pre_sha256: str | None,
    expected_insert_count: int,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    manifest_path = manifest_path.resolve()
    output_path = output_path.resolve()
    if output_path.exists():
        raise OrderCashRepairApplyError(f"output path already exists: {output_path}")
    manifest = _load_manifest(manifest_path)
    _assert_copied_target(db_path)
    if Path(manifest["db_path"]).resolve() != db_path:
        raise OrderCashRepairApplyError("manifest DB path differs from target")
    _validate_external(manifest)
    events = _expected_events(manifest)
    if len(events) != expected_insert_count or int(manifest["expected_insert_count"]) != expected_insert_count:
        raise OrderCashRepairApplyError("expected insert count mismatch")
    pre_sha = sha256_file(db_path)
    idempotent_state = None
    if pre_sha != str(manifest["db_sha256"]):
        idempotent_state = _exact_applied_state(db_path, manifest)
    if pre_sha != str(manifest["db_sha256"]) and idempotent_state is None:
        raise OrderCashRepairApplyError(
            f"copied DB SHA mismatch: manifest {manifest['db_sha256']}, observed {pre_sha}"
        )
    if expected_pre_sha256 and pre_sha != expected_pre_sha256 and idempotent_state is None:
        raise OrderCashRepairApplyError(
            f"--expected-pre-sha256 mismatch: expected {expected_pre_sha256}, observed {pre_sha}"
        )
    if idempotent_state is None:
        rebuilt = build_manifest(
            db_path=db_path,
            publication_manifest_path=Path(manifest["publication_manifest_path"]),
            order_id=str(manifest["order_id"]),
            store_code=str(manifest["store_code"]),
            supersede_event_ids=[int(item["superseded_preimage"]["id"]) for item in manifest["reversals"]],
            repair_key=str(manifest["repair_key"]),
            run_id=str(manifest["run_id"]),
        )
        if rebuilt["manifest_sha256"] != manifest["manifest_sha256"]:
            raise OrderCashRepairApplyError("fresh cash manifest rebuild differs from reviewed manifest")

    report: dict[str, Any] = {
        "status": "PASS",
        "apply_requested": apply,
        "production_apply": False,
        "idempotent_replay": idempotent_state is not None,
        "db_path": str(db_path),
        "pre_sha256": pre_sha,
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": sha256_file(manifest_path),
        "manifest_internal_sha256": manifest["manifest_sha256"],
        "expected_insert_count": expected_insert_count,
        "rows_inserted": 0,
    }
    if idempotent_state is not None:
        if apply and os.environ.get(WRITE_ENV_GATE) != "1":
            raise OrderCashRepairApplyError(f"{WRITE_ENV_GATE}=1 is required for copied replay")
        report.update(idempotent_state)
        report["post_sha256"] = pre_sha
        _write_json_atomic(output_path, report)
        return report
    if not apply:
        _write_json_atomic(output_path, report)
        return report
    if os.environ.get(WRITE_ENV_GATE) != "1":
        raise OrderCashRepairApplyError(f"{WRITE_ENV_GATE}=1 is required for copied apply")
    if backup_dir is None:
        raise OrderCashRepairApplyError("--backup-dir is required with --apply")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"{db_path.stem}.before_cash_repair_{pre_sha[:12]}_{stamp}.db"
    rollback_path = backup_dir / f"ROLLBACK_{stamp}.json"
    if backup_path.exists() or rollback_path.exists():
        raise OrderCashRepairApplyError("backup or rollback path collision")
    shutil.copy2(db_path, backup_path)
    if sha256_file(backup_path) != pre_sha or _integrity(backup_path).lower() != "ok":
        raise OrderCashRepairApplyError("byte-valid copied DB backup verification failed")

    rollback: dict[str, Any] = {
        "operation": "REPLACE_DISPOSABLE_COPY_WITH_BYTE_VALID_PREWRITE_BACKUP",
        "status": "PREPARED_BEFORE_TRANSACTION",
        "target_path": str(db_path),
        "target_pre_sha256": pre_sha,
        "target_post_sha256": None,
        "backup_path": str(backup_path),
        "backup_sha256": pre_sha,
        "restore_verified": False,
        "command": f"cp -p {json.dumps(str(backup_path))} {json.dumps(str(db_path))}",
    }
    _write_json_atomic(rollback_path, rollback)

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    transaction_error: BaseException | None = None
    try:
        counts_before = _table_counts(conn)
        noncash_tables = [table for table in counts_before if table != "fact_cashflow_events"]
        noncash_hashes_before = {table: _logical_hash(conn, table) for table in noncash_tables}
        cash_hash_before = _logical_hash(conn, "fact_cashflow_events")
        if cash_hash_before != manifest["cash_table_logical_sha256"]:
            raise OrderCashRepairApplyError("cash table logical preimage drift")
        conn.execute("BEGIN IMMEDIATE")
        _insert_events(conn, events)
        applied = _exact_applied_state_conn(conn, manifest)
        if applied is None or int(applied["event_count"]) != expected_insert_count:
            raise OrderCashRepairApplyError("exact inserted event readback failed")
        for item in manifest["reversals"]:
            stale = item["superseded_preimage"]
            reverse = item["event"]
            pair = conn.execute(
                """
                SELECT COUNT(*) AS n, ROUND(SUM(amount_kzt), 2) AS net
                FROM fact_cashflow_events WHERE id=? OR event_hash=?
                """,
                (stale["id"], reverse["event_hash"]),
            ).fetchone()
            if int(pair["n"]) != 2 or abs(float(pair["net"] or 0)) > 0.001:
                raise OrderCashRepairApplyError(f"supersession pair does not net to zero: {stale['id']}")
        entry_total = conn.execute(
            f"SELECT COUNT(*), ROUND(SUM(amount_kzt),2) FROM fact_cashflow_events WHERE event_hash IN ({','.join('?' for _ in manifest['replacements'])})",
            [item["event"]["event_hash"] for item in manifest["replacements"]],
        ).fetchone()
        if int(entry_total[0]) != len(manifest["replacements"]) or abs(float(entry_total[1]) - float(manifest["replacement_total_kzt"])) > 0.001:
            raise OrderCashRepairApplyError("replacement entry cash total mismatch")
        counts_after = _table_counts(conn)
        for table, count in counts_before.items():
            expected = count + expected_insert_count if table == "fact_cashflow_events" else count
            if counts_after.get(table) != expected:
                raise OrderCashRepairApplyError(f"table count mismatch: {table}")
        noncash_hashes_after = {table: _logical_hash(conn, table) for table in noncash_tables}
        if noncash_hashes_after != noncash_hashes_before:
            raise OrderCashRepairApplyError("non-cash table logical drift")
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise OrderCashRepairApplyError(f"post-apply integrity_check failed: {integrity}")
        conn.execute("COMMIT")
    except BaseException as exc:
        transaction_error = exc
        if conn.in_transaction:
            conn.execute("ROLLBACK")
    finally:
        conn.close()
    if transaction_error is not None:
        try:
            restored_sha = _restore_verified_backup(
                target=db_path,
                backup=backup_path,
                expected_sha256=pre_sha,
            )
        except BaseException as restore_exc:
            rollback.update(
                {
                    "status": "RESTORE_FAILED_AFTER_TRANSACTION_FAILURE",
                    "failure": f"{type(transaction_error).__name__}: {transaction_error}",
                    "restore_failure": f"{type(restore_exc).__name__}: {restore_exc}",
                }
            )
            try:
                _write_json_atomic(rollback_path, rollback)
            except Exception:
                pass
            raise OrderCashRepairApplyError(
                "AMBIGUOUS: cash transaction failed and exact restore failed; "
                f"use prepared backup {backup_path}"
            ) from restore_exc
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
        _post_commit_barrier(db_path)
        post_state = _exact_applied_state(db_path, manifest)
        if post_state is None or int(post_state["event_count"]) != expected_insert_count:
            raise OrderCashRepairApplyError(
                "post-commit exact cash event readback failed"
            )
        post_sha = sha256_file(db_path)
        report.update(
            {
                "rows_inserted": expected_insert_count,
                "backup_path": str(backup_path),
                "backup_sha256": pre_sha,
                "post_sha256": post_sha,
                "cash_table_logical_sha256_before": cash_hash_before,
                "cash_table_logical_sha256_after": post_state["cash_table_logical_sha256"],
                "event_hashes": post_state["event_hashes"],
                "table_counts_before": counts_before,
                "table_counts_after": counts_after,
                "noncash_hashes_before": noncash_hashes_before,
                "noncash_hashes_after": noncash_hashes_after,
                "integrity_check": integrity,
                "rollback_path": str(rollback_path),
            }
        )
        rollback.update(
            {
                "status": "READY",
                "target_post_sha256": post_sha,
                "restore_verified": False,
            }
        )
        _write_json_atomic(rollback_path, rollback)
        _write_json_atomic(output_path, report)
        return report
    except BaseException as exc:
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
            raise OrderCashRepairApplyError(
                "AMBIGUOUS: cash post-commit failure and exact restore failed; "
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
        output_path.unlink(missing_ok=True)
        raise OrderCashRepairApplyError(
            "cash post-commit verification or evidence finalization failed; "
            "copied DB restored to exact preimage"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--expected-insert-count", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        report = apply_manifest(
            db_path=args.db,
            manifest_path=args.manifest,
            output_path=args.output,
            backup_dir=args.backup_dir,
            apply=args.apply,
            expected_pre_sha256=args.expected_pre_sha256,
            expected_insert_count=args.expected_insert_count,
        )
    except (OrderCashRepairApplyError, OrderCashRepairManifestError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "rows_inserted": report["rows_inserted"], "idempotent_replay": report["idempotent_replay"], "post_sha256": report.get("post_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
