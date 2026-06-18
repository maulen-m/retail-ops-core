#!/usr/bin/env python3
"""Reset exact pytest pollution in fact_inventory_snapshot_size sqlite_sequence.

Default is dry-run. Production apply requires:
- ENABLE_REPO_GUARD_SNAPSHOT_SEQUENCE_CLEANUP_WRITE=1
- --apply
- --expected-pre-sha256
- --backup-dir
- exact expected/current sequence values

This repairs the 2026-06-16 repo-guard test pollution where
tests/test_inventory_snapshot.py inserted and deleted snapshot rows in
production, leaving only sqlite_sequence advanced.
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
ENV_GATE = "ENABLE_REPO_GUARD_SNAPSHOT_SEQUENCE_CLEANUP_WRITE"
TABLE_NAME = "fact_inventory_snapshot_size"
POLLUTED_TEST_DATE = "2099-12-31"


class SnapshotSequenceCleanupError(RuntimeError):
    """Raised when the sequence cleanup cannot prove exact safety."""


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
    with _connect_readonly(path) as conn:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    return str(row[0] if row else "")


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise SnapshotSequenceCleanupError(f"refusing apply while SQLite sidecars exist: {joined}")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _read_sequence_state(conn: sqlite3.Connection) -> dict[str, int | None]:
    if not _table_exists(conn, TABLE_NAME):
        raise SnapshotSequenceCleanupError(f"missing required table: {TABLE_NAME}")
    if not _table_exists(conn, "sqlite_sequence"):
        raise SnapshotSequenceCleanupError("missing required table: sqlite_sequence")

    seq_row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name=?",
        (TABLE_NAME,),
    ).fetchone()
    if seq_row is None:
        raise SnapshotSequenceCleanupError(f"missing sqlite_sequence row for {TABLE_NAME}")

    max_rowid = conn.execute(f"SELECT MAX(rowid) FROM {TABLE_NAME}").fetchone()[0]
    row_count = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    polluted_date_rows = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE snapshot_date=?",
        (POLLUTED_TEST_DATE,),
    ).fetchone()[0]
    return {
        "current_seq": int(seq_row[0]),
        "max_rowid": int(max_rowid or 0),
        "row_count": int(row_count),
        "polluted_test_date_rows": int(polluted_date_rows),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def repair_snapshot_sequence_pollution(
    *,
    db_path: Path,
    apply: bool,
    expected_pre_sha256: str | None,
    backup_dir: Path | None,
    output: Path | None,
    expected_current_seq: int | None,
    target_seq: int | None,
    expected_gap: int | None,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    pre_sha = _sha256_file(db_path)
    pre_integrity = _sqlite_integrity_check(db_path)
    if pre_integrity.lower() != "ok":
        raise SnapshotSequenceCleanupError(f"pre-write integrity_check failed: {pre_integrity}")

    with _connect_readonly(db_path) as conn:
        state = _read_sequence_state(conn)

    inferred_gap = int(state["current_seq"] or 0) - int(state["max_rowid"] or 0)
    effective_target_seq = target_seq if target_seq is not None else int(state["max_rowid"] or 0)
    summary: dict[str, Any] = {
        "mode": "APPLY" if apply else "DRY_RUN",
        "db_path": str(db_path),
        "table": TABLE_NAME,
        "pre_sha256": pre_sha,
        "pre_integrity_check": pre_integrity,
        "state_before": state,
        "expected_current_seq": expected_current_seq,
        "target_seq": effective_target_seq,
        "expected_gap": expected_gap,
        "inferred_gap": inferred_gap,
        "updated_row_count": 0,
        "backup_path": None,
        "backup_sha256": None,
        "backup_integrity_check": None,
        "post_sha256": pre_sha,
        "post_integrity_check": pre_integrity,
        "state_after": state,
        "rollback": None,
    }

    if not apply:
        if output:
            _write_json(output, summary)
        return summary

    if os.environ.get(ENV_GATE) != "1":
        raise SnapshotSequenceCleanupError(f"{ENV_GATE}=1 is required with --apply")
    if expected_pre_sha256 is None:
        raise SnapshotSequenceCleanupError("--expected-pre-sha256 is required with --apply")
    if expected_pre_sha256 != pre_sha:
        raise SnapshotSequenceCleanupError(
            f"pre-write SHA mismatch: expected {expected_pre_sha256}, got {pre_sha}"
        )
    if backup_dir is None:
        raise SnapshotSequenceCleanupError("--backup-dir is required with --apply")
    if expected_current_seq is None or target_seq is None:
        raise SnapshotSequenceCleanupError("--expected-current-seq and --target-seq are required with --apply")
    if int(state["current_seq"] or 0) != expected_current_seq:
        raise SnapshotSequenceCleanupError(
            f"current seq mismatch: expected {expected_current_seq}, got {state['current_seq']}"
        )
    if int(state["max_rowid"] or 0) != target_seq:
        raise SnapshotSequenceCleanupError(
            f"target seq must equal current max(rowid): target {target_seq}, max(rowid) {state['max_rowid']}"
        )
    if expected_gap is not None and inferred_gap != expected_gap:
        raise SnapshotSequenceCleanupError(
            f"sequence gap mismatch: expected {expected_gap}, got {inferred_gap}"
        )
    if int(state["polluted_test_date_rows"] or 0) != 0:
        raise SnapshotSequenceCleanupError(
            f"refusing cleanup while {POLLUTED_TEST_DATE} rows remain: {state['polluted_test_date_rows']}"
        )

    _fail_on_sqlite_sidecars(db_path)
    backup_path = backup_database(db_path, backup_dir.resolve(), compress=False)
    backup_integrity = _sqlite_integrity_check(backup_path)
    if backup_integrity.lower() != "ok":
        raise SnapshotSequenceCleanupError(f"backup integrity_check failed: {backup_integrity}")

    with _connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE sqlite_sequence SET seq=? WHERE name=?",
            (target_seq, TABLE_NAME),
        )
        conn.commit()
        updated = int(cursor.rowcount or 0)
    if updated != 1:
        raise SnapshotSequenceCleanupError(f"expected to update one sqlite_sequence row, updated {updated}")

    post_sha = _sha256_file(db_path)
    post_integrity = _sqlite_integrity_check(db_path)
    with _connect_readonly(db_path) as conn:
        state_after = _read_sequence_state(conn)

    summary.update(
        {
            "updated_row_count": updated,
            "backup_path": str(backup_path),
            "backup_sha256": _sha256_file(backup_path),
            "backup_integrity_check": backup_integrity,
            "post_sha256": post_sha,
            "post_integrity_check": post_integrity,
            "state_after": state_after,
            "rollback": (
                f"Restore backup DB from {backup_path} or set "
                f"sqlite_sequence seq back to {expected_current_seq} for {TABLE_NAME}."
            ),
        }
    )
    if output:
        _write_json(output, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-current-seq", type=int)
    parser.add_argument("--target-seq", type=int)
    parser.add_argument("--expected-gap", type=int)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = repair_snapshot_sequence_pollution(
            db_path=args.db,
            apply=args.apply,
            expected_pre_sha256=args.expected_pre_sha256,
            backup_dir=args.backup_dir,
            output=args.output,
            expected_current_seq=args.expected_current_seq,
            target_seq=args.target_seq,
            expected_gap=args.expected_gap,
        )
    except SnapshotSequenceCleanupError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"mode={summary['mode']}")
        print(f"current_seq={summary['state_before']['current_seq']}")
        print(f"target_seq={summary['target_seq']}")
        print(f"inferred_gap={summary['inferred_gap']}")
        print(f"updated_row_count={summary['updated_row_count']}")
        print(f"post_sha256={summary['post_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
