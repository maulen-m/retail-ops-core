#!/usr/bin/env python3
"""Apply post-restoration returned_to_warehouse flags for RETURNED orders.

This is a narrow G-RET-01 repair. It only sets the pickup-ready flag for
orders that are already in Kaspi/internal RETURNED status inside an explicit
date window. Historical pre-restoration backlog is intentionally left alone.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH  # noqa: E402


ENV_GATE = "ENABLE_RETURNED_TO_WAREHOUSE_FLAG_WRITE"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "returned_to_warehouse_flags"


class ReturnedToWarehouseFlagError(RuntimeError):
    """Raised when the returned_to_warehouse repair is unsafe."""


def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    with _connect(path, readonly=True) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0] if row else "")


def _backup_db(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = _connect(src, readonly=True)
    target = sqlite3.connect(str(dst))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    integrity = _sqlite_integrity_check(dst)
    if integrity.lower() != "ok":
        raise ReturnedToWarehouseFlagError(f"backup integrity_check failed: {integrity}")
    return dst


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [Path(f"{db_path}-wal"), Path(f"{db_path}-shm"), Path(f"{db_path}-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise ReturnedToWarehouseFlagError(f"refusing apply while SQLite sidecars exist: {joined}")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _returned_predicate_sql() -> str:
    return """
        UPPER(COALESCE(kaspi_status_detail, internal_status, kaspi_status, '')) = 'RETURNED'
    """


def _coverage(conn: sqlite3.Connection, *, since: date, until: date) -> dict[str, Any]:
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS returned_rows,
            COUNT(DISTINCT order_id) AS returned_orders,
            SUM(CASE WHEN COALESCE(returned_to_warehouse, 0) = 1 THEN 1 ELSE 0 END) AS flagged_rows,
            COUNT(DISTINCT CASE WHEN COALESCE(returned_to_warehouse, 0) = 1 THEN order_id END) AS flagged_orders
        FROM fact_orders_kaspi
        WHERE {_returned_predicate_sql()}
          AND date(COALESCE(status_updated_at, updated_at, created_at)) BETWEEN ? AND ?
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchone()
    returned_rows = int(row["returned_rows"] or 0)
    returned_orders = int(row["returned_orders"] or 0)
    flagged_rows = int(row["flagged_rows"] or 0)
    flagged_orders = int(row["flagged_orders"] or 0)
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "returned_rows": returned_rows,
        "returned_orders": returned_orders,
        "flagged_rows": flagged_rows,
        "flagged_orders": flagged_orders,
        "unflagged_rows": returned_rows - flagged_rows,
        "unflagged_orders": returned_orders - flagged_orders,
        "coverage_rows_pct": round((flagged_rows / returned_rows) * 100, 2) if returned_rows else 100.0,
        "coverage_orders_pct": round((flagged_orders / returned_orders) * 100, 2) if returned_orders else 100.0,
    }


def _candidate_rows(conn: sqlite3.Connection, *, since: date, until: date) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT
            id,
            order_id,
            store_code,
            sku_id,
            my_size,
            quantity,
            kaspi_status,
            kaspi_status_detail,
            internal_status,
            returned_to_warehouse,
            created_at,
            status_updated_at,
            updated_at,
            date(COALESCE(status_updated_at, updated_at, created_at)) AS predicate_date
        FROM fact_orders_kaspi
        WHERE {_returned_predicate_sql()}
          AND date(COALESCE(status_updated_at, updated_at, created_at)) BETWEEN ? AND ?
          AND COALESCE(returned_to_warehouse, 0) != 1
        ORDER BY predicate_date, store_code, order_id, sku_id, id
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def _apply_flags(conn: sqlite3.Connection, candidate_ids: list[int]) -> int:
    if not candidate_ids:
        return 0
    cursor = conn.executemany(
        """
        UPDATE fact_orders_kaspi
        SET returned_to_warehouse = 1
        WHERE id = ?
          AND COALESCE(returned_to_warehouse, 0) != 1
        """,
        [(row_id,) for row_id in candidate_ids],
    )
    return int(cursor.rowcount or 0)


def apply_returned_to_warehouse_flags(
    *,
    db_path: Path,
    since: date,
    until: date,
    output_root: Path,
    apply: bool = False,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    if since > until:
        raise ReturnedToWarehouseFlagError("since must be <= until")
    output_root.mkdir(parents=True, exist_ok=True)
    pre_sha = _sha256_file(db_path)
    if expected_pre_sha256 and pre_sha != expected_pre_sha256:
        raise ReturnedToWarehouseFlagError(f"pre-sha mismatch: expected {expected_pre_sha256} got {pre_sha}")

    with _connect(db_path, readonly=True) as conn:
        before = _coverage(conn, since=since, until=until)
        candidates = _candidate_rows(conn, since=since, until=until)

    backup_path = ""
    applied_row_count = 0
    if apply:
        if os.environ.get(ENV_GATE) != "1":
            raise ReturnedToWarehouseFlagError(f"{ENV_GATE}=1 is required for --apply")
        _fail_on_sqlite_sidecars(db_path)
        if backup_dir is None:
            raise ReturnedToWarehouseFlagError("--backup-dir is required for --apply")
        backup_name = f"app_before_returned_to_warehouse_flags_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = str(_backup_db(db_path, backup_dir / backup_name))
        candidate_ids = [int(row["id"]) for row in candidates]
        with _connect(db_path, readonly=False) as conn:
            applied_row_count = _apply_flags(conn, candidate_ids)
            conn.commit()

    post_sha = _sha256_file(db_path)
    with _connect(db_path, readonly=True) as conn:
        after = _coverage(conn, since=since, until=until)
        remaining = _candidate_rows(conn, since=since, until=until)
    integrity = _sqlite_integrity_check(db_path)

    candidate_csv = output_root / "candidate_rows.csv"
    remaining_csv = output_root / "remaining_unflagged_rows.csv"
    _write_csv(candidate_csv, candidates)
    _write_csv(remaining_csv, remaining)

    summary = {
        "status": "APPLIED" if apply else "DRY_RUN",
        "db_path": str(db_path),
        "pre_sha256": pre_sha,
        "post_sha256": post_sha,
        "db_sha_changed": pre_sha != post_sha,
        "backup_path": backup_path,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "before": before,
        "after": after,
        "candidate_row_count": len(candidates),
        "candidate_order_count": len({str(row["order_id"]) for row in candidates}),
        "applied_row_count": applied_row_count,
        "remaining_unflagged_row_count": len(remaining),
        "remaining_unflagged_order_count": len({str(row["order_id"]) for row in remaining}),
        "sqlite_integrity_check": integrity,
        "candidate_rows_csv": str(candidate_csv),
        "remaining_unflagged_rows_csv": str(remaining_csv),
        "env_gate": ENV_GATE,
    }
    _write_json(output_root / "summary.json", summary)
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--since", required=True, help="First status-updated date to include, YYYY-MM-DD")
    parser.add_argument("--until", required=True, help="Last status-updated date to include, YYYY-MM-DD")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-pre-sha256", default="")
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = apply_returned_to_warehouse_flags(
        db_path=args.db,
        since=date.fromisoformat(args.since),
        until=date.fromisoformat(args.until),
        output_root=args.output_root,
        apply=bool(args.apply),
        expected_pre_sha256=args.expected_pre_sha256 or None,
        backup_dir=args.backup_dir,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "returned_to_warehouse_flags "
            f"status={summary['status']} "
            f"candidate_rows={summary['candidate_row_count']} "
            f"remaining_rows={summary['remaining_unflagged_row_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
