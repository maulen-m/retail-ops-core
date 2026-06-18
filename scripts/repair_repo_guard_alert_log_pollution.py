#!/usr/bin/env python3
"""Remove exact pytest alert-log rows accidentally written to production DB.

Default is dry-run. Production apply requires:
- ENABLE_REPO_GUARD_ALERT_LOG_CLEANUP_WRITE=1
- --apply
- --expected-pre-sha256
- --backup-dir

This script intentionally deletes only the six exact fact_alert_log rows that
match the 2026-06-16 repo-guard pytest pollution signature.
"""

from __future__ import annotations

import argparse
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

from scripts.backup_db import backup_database  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
ENV_GATE = "ENABLE_REPO_GUARD_ALERT_LOG_CLEANUP_WRITE"

EXPECTED_ROWS = [
    {
        "id": 858,
        "alert_date": "2026-06-16",
        "alert_time": "2026-06-16 14:22:20",
        "alert_type": "REORDER",
        "channel": "telegram",
        "store_code": "TEST_STORE",
        "sku_key": "RECENT_SKU",
        "message": "test",
        "status": "SENT",
    },
    {
        "id": 859,
        "alert_date": "2026-06-16",
        "alert_time": "2026-06-16 14:22:20",
        "alert_type": "REORDER",
        "channel": "telegram",
        "store_code": "LOG_STORE",
        "sku_key": "LOG_TEST_SKU",
        "message": "Test message",
        "status": "SENT",
    },
    {
        "id": 860,
        "alert_date": "2026-06-16",
        "alert_time": "2026-06-16 14:22:20",
        "alert_type": "REORDER",
        "channel": "telegram",
        "store_code": "STORE",
        "sku_key": "SUPPRESSED_SKU",
        "message": "",
        "status": "SUPPRESSED",
    },
    {
        "id": 861,
        "alert_date": "2026-06-16",
        "alert_time": "2026-06-16 14:49:42",
        "alert_type": "REORDER",
        "channel": "telegram",
        "store_code": "TEST_STORE",
        "sku_key": "RECENT_SKU",
        "message": "test",
        "status": "SENT",
    },
    {
        "id": 862,
        "alert_date": "2026-06-16",
        "alert_time": "2026-06-16 14:49:42",
        "alert_type": "REORDER",
        "channel": "telegram",
        "store_code": "LOG_STORE",
        "sku_key": "LOG_TEST_SKU",
        "message": "Test message",
        "status": "SENT",
    },
    {
        "id": 863,
        "alert_date": "2026-06-16",
        "alert_time": "2026-06-16 14:49:42",
        "alert_type": "REORDER",
        "channel": "telegram",
        "store_code": "STORE",
        "sku_key": "SUPPRESSED_SKU",
        "message": "",
        "status": "SUPPRESSED",
    },
]

MATCH_COLUMNS = [
    "id",
    "alert_date",
    "alert_time",
    "alert_type",
    "channel",
    "store_code",
    "sku_key",
    "message",
    "status",
]


class RepoGuardAlertLogCleanupError(RuntimeError):
    """Raised when the alert-log cleanup cannot prove exact safety."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_integrity_check(path: Path) -> str:
    conn = _connect_readonly(path)
    try:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
        return str(row[0] if row else "")
    finally:
        conn.close()


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise RepoGuardAlertLogCleanupError(f"refusing apply while SQLite sidecars exist: {joined}")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _where_clause(row: dict[str, Any]) -> tuple[str, list[Any]]:
    parts = [f"{column}=?" for column in MATCH_COLUMNS]
    return " AND ".join(parts), [row[column] for column in MATCH_COLUMNS]


def _find_matches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "fact_alert_log"):
        raise RepoGuardAlertLogCleanupError("missing required table: fact_alert_log")

    matches: list[dict[str, Any]] = []
    for expected in EXPECTED_ROWS:
        where_sql, params = _where_clause(expected)
        rows = conn.execute(
            f"""
            SELECT id, alert_date, alert_time, alert_type, channel, store_code,
                   sku_key, message, status, external_id, suppression_reason, created_at
            FROM fact_alert_log
            WHERE {where_sql}
            """,
            params,
        ).fetchall()
        if len(rows) > 1:
            raise RepoGuardAlertLogCleanupError(f"exact pollution predicate matched duplicate id={expected['id']}")
        matches.extend(dict(row) for row in rows)
    return matches


def _delete_matches(conn: sqlite3.Connection) -> int:
    deleted = 0
    for expected in EXPECTED_ROWS:
        where_sql, params = _where_clause(expected)
        cursor = conn.execute(f"DELETE FROM fact_alert_log WHERE {where_sql}", params)
        deleted += int(cursor.rowcount or 0)
    conn.commit()
    return deleted


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def repair_alert_log_pollution(
    *,
    db_path: Path,
    apply: bool,
    expected_pre_sha256: str | None,
    backup_dir: Path | None,
    output: Path | None,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    pre_sha = _sha256_file(db_path)
    pre_integrity = _sqlite_integrity_check(db_path)
    if pre_integrity.lower() != "ok":
        raise RepoGuardAlertLogCleanupError(f"pre-write integrity_check failed: {pre_integrity}")

    conn = _connect_readonly(db_path)
    try:
        pre_matches = _find_matches(conn)
    finally:
        conn.close()

    summary: dict[str, Any] = {
        "mode": "APPLY" if apply else "DRY_RUN",
        "db_path": str(db_path),
        "pre_sha256": pre_sha,
        "pre_integrity_check": pre_integrity,
        "expected_row_count": len(EXPECTED_ROWS),
        "matched_row_count": len(pre_matches),
        "matched_rows": pre_matches,
        "deleted_row_count": 0,
        "backup_path": None,
        "backup_sha256": None,
        "backup_integrity_check": None,
        "post_sha256": pre_sha,
        "post_integrity_check": pre_integrity,
        "remaining_matched_row_count": len(pre_matches),
        "rollback": None,
    }

    if not apply:
        if output:
            _write_json(output, summary)
        return summary

    if os.environ.get(ENV_GATE) != "1":
        raise RepoGuardAlertLogCleanupError(f"{ENV_GATE}=1 is required with --apply")
    if expected_pre_sha256 is None:
        raise RepoGuardAlertLogCleanupError("--expected-pre-sha256 is required with --apply")
    if expected_pre_sha256 != pre_sha:
        raise RepoGuardAlertLogCleanupError(
            f"pre-write SHA mismatch: expected {expected_pre_sha256}, got {pre_sha}"
        )
    if backup_dir is None:
        raise RepoGuardAlertLogCleanupError("--backup-dir is required with --apply")
    if len(pre_matches) != len(EXPECTED_ROWS):
        raise RepoGuardAlertLogCleanupError(
            f"expected {len(EXPECTED_ROWS)} exact rows before apply, found {len(pre_matches)}"
        )

    _fail_on_sqlite_sidecars(db_path)
    backup_path = backup_database(db_path, backup_dir.resolve(), compress=False)
    backup_integrity = _sqlite_integrity_check(backup_path)
    if backup_integrity.lower() != "ok":
        raise RepoGuardAlertLogCleanupError(f"backup integrity_check failed: {backup_integrity}")

    conn = _connect(db_path)
    try:
        deleted = _delete_matches(conn)
    finally:
        conn.close()

    post_integrity = _sqlite_integrity_check(db_path)
    if post_integrity.lower() != "ok":
        raise RepoGuardAlertLogCleanupError(f"post-write integrity_check failed: {post_integrity}")

    conn = _connect_readonly(db_path)
    try:
        remaining = _find_matches(conn)
    finally:
        conn.close()

    summary.update(
        {
            "deleted_row_count": deleted,
            "backup_path": str(backup_path),
            "backup_sha256": _sha256_file(backup_path),
            "backup_integrity_check": backup_integrity,
            "post_sha256": _sha256_file(db_path),
            "post_integrity_check": post_integrity,
            "remaining_matched_row_count": len(remaining),
            "rollback": {
                "restore_command": f"cp {backup_path} {db_path}",
                "backup_path": str(backup_path),
            },
        }
    )

    if deleted != len(EXPECTED_ROWS):
        raise RepoGuardAlertLogCleanupError(
            f"expected to delete {len(EXPECTED_ROWS)} rows, deleted {deleted}"
        )
    if remaining:
        raise RepoGuardAlertLogCleanupError("exact pollution rows remain after cleanup")

    if output:
        _write_json(output, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-pre-sha256", default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = repair_alert_log_pollution(
            db_path=args.db,
            apply=args.apply,
            expected_pre_sha256=args.expected_pre_sha256,
            backup_dir=args.backup_dir,
            output=args.output,
        )
    except RepoGuardAlertLogCleanupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"mode={summary['mode']} matched={summary['matched_row_count']} "
            f"deleted={summary['deleted_row_count']} remaining={summary['remaining_matched_row_count']}"
        )
        if summary["backup_path"]:
            print(f"backup_path={summary['backup_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
